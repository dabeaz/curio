# curio/monitor.py
#
# Copyright (C) 2015-2016
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# Debugging monitor for curio. To enable the monitor, create a kernel
# with the with_monitor argument:
#
#    k = Kernel(with_monitor=True)
#
# Or run a curio program with the CURIOMONITOR environment variable set
#
#    env CURIOMONITOR=TRUE python3 someprog.py
#
# If you need to change some aspect of the monitor configuration, you
# can do manual setup:
#
#    k = Kernel()
#    Monitor(k, host, port)
#
# Where host and port configure the network address on which the monitor
# operates.
#
# To connect to the monitor, run python3 -m curio.monitor [port]. For example:
#
# Theory of operation:
# --------------------
# The monitor works by opening up a loopback socket on the local machine and
# allowing connections via telnet. By default, it only allows a connection
# originating from the local machine.  Only a single monitor connection is
# allowed at any given time.
#
# There are two parts to the monitor itself: a user interface and an
# internal loop that runs on curio itself.  The user interface part
# runs in a completely separate execution thread.  The reason for this
# is that it allows curio to be monitored even if the curio kernel is
# completely deadlocked, occupied with a large CPU-bound task, or
# otherwise hosed in the some way.  At a minimum, you can connect,
# look at the task table, and see what the tasks are doing.
#
# The internal monitor loop implemented on curio itself is presently
# used to implement external task cancellation.  Manipulating any 
# part of the kernel state or task status is unsafe from an outside thread.
# To make it safe, the user-interface thread of the monitor hands over
# requests requiring the involvement of the kernel to the monitor loop.
# Since this loop runs on curio, it can safely make cancellation requests
# and perform other kernel-related actions. 

import sys
import os
import traceback
import linecache
import signal
import time
import socket
import threading
import queue
import telnetlib
from collections import deque
import logging

# --- Curio
from .task import Task
from .workers import run_in_thread
from .sync import abide

# ---
log = logging.getLogger(__name__)

MONITOR_HOST = '127.0.0.1'
MONITOR_PORT = 48802

def _get_stack(task):
    '''
    Extracts a list of stack frames from a chain of generator/coroutine calls
    '''
    frames = []
    coro = task.coro
    while coro:
        f = coro.cr_frame if hasattr(coro, 'cr_frame') else coro.gi_frame
        if f is not None:
            frames.append(f)
        coro = coro.cr_await if hasattr(coro, 'cr_await') else coro.gi_yieldfrom
    return frames

def _format_stack(task):
    '''
    Formats a traceback from a stack of coroutines/generators
    '''
    extracted_list = []
    checked = set()
    for f in _get_stack(task):
        lineno = f.f_lineno
        co = f.f_code
        filename = co.co_filename
        name = co.co_name
        if filename not in checked:
            checked.add(filename)
            linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        extracted_list.append((filename, lineno, name, line))
    if not extracted_list:
        resp = 'No stack for %r' % task 
    else:
        resp = 'Stack for %r (most recent call last):\n' % task
        resp += ''.join(traceback.format_list(extracted_list))
    return resp

class Monitor(object):
    '''
    Task monitor that runs concurrently to the curio kernel in a 
    separate thread. This can watch the kernel and provide debugging.
    '''
    def __init__(self, kern, host=MONITOR_HOST, port=MONITOR_PORT):
        self.kernel = kern
        self.address = (host, port)
        self.monitor_queue = queue.Queue()

        log.info('Starting Curio monitor at %s:%d', host, port)

        # The monitor launches both a separate thread and helper task
        # that runs inside curio itself to manage cancellation events
        threading.Thread(target=self.server, daemon=True).start()
        monitor_task = Task(self.monitor_task(), daemon=True)
        kern._ready.append(monitor_task)
        kern._tasks[monitor_task.id] = monitor_task

    async def monitor_task(self):
        '''
        Asynchronous task loop for carrying out task cancellation.
        '''
        while True:
            task = await abide(self.monitor_queue.get)
            await task.cancel()
            await abide(self.monitor_queue.task_done)

    def server(self):
        '''
        Synchronous kernel for the monitor.  This runs in a separate thread
        from curio itself.
        '''
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        sock.bind(self.address)
        sock.listen(1)
        while True:
            client, addr = sock.accept()
            sout = client.makefile('w', encoding='utf-8')
            sin = client.makefile('r', encoding='utf-8')
            self.interactive_loop(sout, sin)
            client.close()
                
    def interactive_loop(self, sout, sin):
        '''
        Main interactive loop of the monitor
        '''
        sout.write('\nCurio Monitor: %d tasks running\n' % len(self.kernel._tasks))
        sout.write('Type help for commands\n')
        while True:
            sout.write('curio > ')
            sout.flush()
            resp = sin.readline()
            try:
                if not resp or resp.startswith('q'):
                    sout.write('Leaving monitor\n')
                    return

                elif resp.startswith('p'):
                    self.command_ps(sout)

                elif resp.startswith('exit'):
                    self.command_exit(sout)

                elif resp.startswith('cancel'):
                    _, taskid_s = resp.split()
                    self.command_cancel(sout, int(taskid_s))

                elif resp.startswith('signal'):
                    _, signame = resp.split()
                    self.command_signal(sout, signame)

                elif resp.startswith('w'):
                    _, taskid_s = resp.split()
                    self.command_where(sout, int(taskid_s))

                elif resp.startswith('h'):
                    self.command_help(sout)
                else:
                    sout.write('Unknown command. Type help.\n')
            except Exception as e:
                sout.write('Bad command. %s\n' % e)

    def command_help(self, sout):
        sout.write(
     '''Commands:
         ps               : Show task table
         where taskid     : Show stack frames for a task
         cancel taskid    : Cancel an indicated task
         signal signame   : Send a Unix signal
         quit             : Leave the monitor
''')

    def command_ps(self, sout):
        headers = ('Task', 'State', 'Cycles', 'Timeout', 'Task')
        widths = (6, 12, 10, 7, 50)
        for h, w in zip(headers, widths):
            sout.write('%-*s ' % (w, h))
        sout.write('\n')
        sout.write(' '.join(w*'-' for w in widths))
        sout.write('\n')
        timestamp = time.monotonic()
        for taskid in sorted(self.kernel._tasks):
            task = self.kernel._tasks.get(taskid)
            if task:
                remaining = format((task.timeout - timestamp), '0.6f')[:7] if task.timeout else 'None'
                sout.write('%-*d %-*s %-*d %-*s %-*s\n' % (widths[0], taskid, 
                                                                widths[1], task.state,
                                                                widths[2], task.cycles,
                                                                widths[3], remaining,
                                                                widths[4], task))

    def command_where(self, sout, taskid):
        task = self.kernel._tasks.get(taskid)
        if task:
            stack = _format_stack(task)
            sout.write(stack+'\n')
        else:
            sout.write('No task %d\n' % taskid)

    def command_signal(self, sout, signame):
        if hasattr(signal, signame):
            os.kill(os.getpid(), getattr(signal, signame))
        else:
            sout.write('Unknown signal %s\n' % signame)

    def command_cancel(self, sout, taskid):
        task = self.kernel._tasks.get(taskid)
        if task:
            sout.write('Cancelling task %d\n' % taskid)
            self.monitor_queue.put(task)
            self.monitor_queue.join()
            
    def command_exit(self, sout):
        pass

def monitor_client(host, port):
    '''
    Client to connect to the monitor via "telnet"
    '''
    tn = telnetlib.Telnet()
    tn.open(host, port, timeout=0.5)
    tn.interact()
    tn.close()

if __name__ == '__main__':
    if sys.argv[1:]:
        port = int(sys.argv[1])
    else:
        port = MONITOR_PORT
    monitor_client(MONITOR_HOST, port)
