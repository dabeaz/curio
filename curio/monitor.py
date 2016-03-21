# curio/monitor.py
#
# Copyright (C) 2015
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# Debugging monitor for curio.   At the moment, this is overly simplistic.
# It could be expanded to do a lot of other stuff later.

import sys
import os
import traceback
import linecache
import signal
import time
import atexit
import socket
import threading

from .io import Stream
from .kernel import _kernel_reference, SignalSet, CancelledError, get_kernel

def _get_stack(task):
    frames = []
    coro = task.coro
    while coro:
        f = coro.cr_frame if hasattr(coro, 'cr_frame') else coro.gi_frame
        if f is not None:
            frames.append(f)
        coro = coro.cr_await if hasattr(coro, 'cr_await') else coro.gi_yieldfrom
    return frames

def _print_stack(task):
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
            print('No stack for %r' % task)
        else:
            print('Stack for %r (most recent call last):' % task)
        traceback.print_list(extracted_list)

def _format_stack(task):
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
    def __init__(self, kernel, sin, sout):
        self.kernel = kernel
        self.sin = sin
        self.sout = sout

    def loop(self):
        self.sout.write('\nCurio Monitor: %d tasks running\n' % len(self.kernel._tasks))
        self.sout.write('Type help for commands\n')
        while True:
            self.sout.write('curio > ')
            self.sout.flush()
            resp = self.sin.readline()
            try:
                if not resp or resp.startswith('q'):
                    self.sout.write('Leaving monitor\n')
                    return

                elif resp.startswith('p'):
                    self.command_ps()

                elif resp.startswith('exit'):
                    self.command_exit()

                elif resp.startswith('cancel'):
                    _, taskid_s = resp.split()
                    self.command_cancel(int(taskid_s))

                elif resp.startswith('signal'):
                    _, signame = resp.split()
                    self.command_signal(signame)

                elif resp.startswith('w'):
                    _, taskid_s = resp.split()
                    self.command_where(int(taskid_s))

                elif resp.startswith('h'):
                    self.command_help()

                else:
                    self.sout.write('Unknown command. Type help.\n')
            except Exception as e:
                self.sout.write('Bad command. %s\n' % e)

    def command_help(self):
        self.sout.write(
     '''Commands:
         ps               : Show task table
         where taskid     : Show stack frames for a task
         cancel taskid    : Cancel a task
         signal signame   : Send a Unix signal
         exit             : Raise SystemExit and terminate
         quit             : Leave the monitor
     ''')

    def command_ps(self):
        headers = ('Task', 'State', 'Cycles', 'Timeout', 'Task')
        widths = (6, 12, 10, 7, 50)
        for h, w in zip(headers, widths):
            self.sout.write('%-*s ' % (w, h))
        self.sout.write('\n')
        self.sout.write(' '.join(w*'-' for w in widths))
        self.sout.write('\n')
        timestamp = time.monotonic()
        for taskid in sorted(self.kernel._tasks):
            task = self.kernel._tasks.get(taskid)
            if task:
                remaining = format((task.timeout - timestamp), '0.6f')[:7] if task.timeout else 'None'
                self.sout.write('%-*d %-*s %-*d %-*s %-*s\n' % (widths[0], taskid, 
                                                                widths[1], task.state,
                                                                widths[2], task.cycles,
                                                                widths[3], remaining,
                                                                widths[4], task))

    def command_where(self, taskid):
        task = self.kernel._tasks.get(taskid)
        if task:
            stack = _format_stack(task)
            self.sout.write(stack+'\n')
        else:
            self.sout.write('No task %d\n' % taskid)
        
    def command_exit(self):
        pass

    def command_cancel(self, taskid):
        pass

    def command_signal(self, signame):
        if hasattr(signal, signame):
            os.kill(os.getpid(), getattr(signal, signame))

async def monrun(kernel):
    stdin = Stream(sys.stdin.buffer.raw)
    try:
         print('\nCurio Monitor:  %d tasks running' % len(kernel._tasks))
         print('Type help for commands')

         while True:
              print('curio > ', end='', flush=True)
              resp = await stdin.readline()
              if not resp or resp.startswith(b'q'):
                   print('Leaving monitor')
                   return
              elif resp.startswith(b'p'):
                   ps(kernel)
              elif resp.startswith(b'exit'):
                   raise SystemExit()
              elif resp.startswith(b'cancel'):
                   try:
                        _, taskid_s = resp.split()
                        taskid = int(taskid_s)
                        if taskid in kernel._tasks:
                             print('Cancelling task', taskid)
                             await kernel._tasks[taskid].cancel()
                        else:
                             print('Bad task id')
                   except Exception as e:
                        print('Bad command')
              elif resp.startswith(b'signal'):
                  try:
                      _, signame = resp.split()
                      signame = signame.decode('ascii').strip()
                      if hasattr(signal, signame):
                          os.kill(os.getpid(), getattr(signal, signame))
                  except Exception as e:
                      print('Bad command',e )

              elif resp.startswith(b'w'):
                   try:
                        _, taskid_s = resp.split()
                        taskid = int(taskid_s)
                        if taskid in kernel._tasks:
                             _print_stack(kernel._tasks[taskid])
                             print()
                   except Exception as e:
                        print('Bad command', e)
                             
              elif resp.startswith(b'h'):
                   print(
     '''Commands:
         ps               : Show task table
         where taskid     : Show stack frames for a task
         cancel taskid    : Cancel a task
         signal signame   : Send a Unix signal
         exit             : Raise SystemExit and terminate
         quit             : Leave the monitor
     ''')
              elif resp == b'\n':
                   pass
              else:
                   print('Unknown command. Type help.')

    finally:
         os.set_blocking(stdin.fileno(), True)



    # Debugging
def ps(kernel):
    headers = ('Task', 'State', 'Cycles', 'Timeout', 'Task')
    widths = (6, 12, 10, 7, 50)
    for h, w in zip(headers, widths):
        print('%-*s' % (w, h), end=' ')
    print()
    print(' '.join(w*'-' for w in widths))
    timestamp = time.monotonic()
    for taskid in sorted(kernel._tasks):
        task = kernel._tasks[taskid]
        remaining = format((task.timeout - timestamp), '0.6f')[:7] if task.timeout else 'None'
        print('%-*d %-*s %-*d %-*s %-*s' % (widths[0], taskid, 
                                            widths[1], task.state,
                                            widths[2], task.cycles,
                                            widths[3], remaining,
                                            widths[4], task))

async def monrun(kernel):
    stdin = Stream(sys.stdin.buffer.raw)
    try:
         print('\nCurio Monitor:  %d tasks running' % len(kernel._tasks))
         print('Type help for commands')

         while True:
              print('curio > ', end='', flush=True)
              resp = await stdin.readline()
              if not resp or resp.startswith(b'q'):
                   print('Leaving monitor')
                   return
              elif resp.startswith(b'p'):
                   ps(kernel)
              elif resp.startswith(b'exit'):
                   raise SystemExit()
              elif resp.startswith(b'cancel'):
                   try:
                        _, taskid_s = resp.split()
                        taskid = int(taskid_s)
                        if taskid in kernel._tasks:
                             print('Cancelling task', taskid)
                             await kernel._tasks[taskid].cancel()
                        else:
                             print('Bad task id')
                   except Exception as e:
                        print('Bad command')
              elif resp.startswith(b'signal'):
                  try:
                      _, signame = resp.split()
                      signame = signame.decode('ascii').strip()
                      if hasattr(signal, signame):
                          os.kill(os.getpid(), getattr(signal, signame))
                  except Exception as e:
                      print('Bad command',e )

              elif resp.startswith(b'w'):
                   try:
                        _, taskid_s = resp.split()
                        taskid = int(taskid_s)
                        if taskid in kernel._tasks:
                             _print_stack(kernel._tasks[taskid])
                             print()
                   except Exception as e:
                        print('Bad command', e)
                             
              elif resp.startswith(b'h'):
                   print(
     '''Commands:
         ps               : Show task table
         where taskid     : Show stack frames for a task
         cancel taskid    : Cancel a task
         signal signame   : Send a Unix signal
         exit             : Raise SystemExit and terminate
         quit             : Leave the monitor
''')
              elif resp == b'\n':
                   pass
              else:
                   print('Unknown command. Type help.')

    finally:
         os.set_blocking(stdin.fileno(), True)

async def monitor():
    kernel = await _kernel_reference()
    # If the kernel monitor is being used, it's critical that it be shutdown cleanly at exit
    atexit.register(kernel.shutdown)

    sigset = SignalSet(signal.SIGINT)
    while True:
        await sigset.wait()
        with sigset.ignore():
            await monrun(kernel)
    

def _sync_monitor(kernel, host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
    sock.bind((host, port))
    sock.listen(1)
    while True:
        client, addr = sock.accept()
        sin = client.makefile('r', encoding='utf-8')
        sout = client.makefile('w', encoding='utf-8')
        mon = Monitor(kernel, sin, sout)
        mon.loop()
        sin.close()
        sout.close()
        client.close()

def sync_monitor(kernel, host='0.0.0.0', port=9000):
    threading.Thread(target=_sync_monitor, args=(kernel, host, port), daemon=True).start()
