# curio/monitor.py
#
# Debugging monitor for curio. To enable the monitor, create a kernel
# and then attach a monitor to it, like this:
#
#    k = Kernel()
#    mon = Monitor(k)
#    k.run(mon.start)
#
# If using the run() function, you can do this:
#
#    run(coro, with_monitor=True)
#
# run() also looks for the CURIOMONITOR environment variable
#
#    env CURIOMONITOR=TRUE python3 someprog.py
#
# If you need to change some aspect of the monitor configuration, you
# can do manual setup:
#
#    k = Kernel()
#    mon = Monitor(k, host, port)
#    k.run(mon.start)
#
# Where host and port configure the network address on which the monitor
# operates.
#
# To connect to the monitor, run python3 -m curio.monitor -H [host] -p [port]. 
#
# Theory of operation:
# --------------------
# The monitor works by opening up a loopback socket on the local
# machine and allowing connections via a tool like telnet or nc.  By
# default, it only allows a connection originating from the local
# machine.  Only a single monitor connection is allowed at any given
# time.
#
# The monitor is implemented externally to Curio using threads.  The
# reason for this is that it allows curio to be monitored even if the
# curio kernel is completely deadlocked, occupied with a large
# CPU-bound task, or otherwise hosed in the some way.  At a minimum,
# you can connect, look at the task table, and see what the tasks are
# doing.

import os
import signal
import time
import socket
import threading
import argparse
import logging
import sys

# --- Curio
from .task import spawn
from . import meta
from . import queue

# ---
log = logging.getLogger(__name__)

MONITOR_HOST = '127.0.0.1'
MONITOR_PORT = 48802

# Implementation of the 'ps' command
def ps(kernel=None, out=sys.stdout):
    if kernel is None:
        kernel = meta._locals.kernel
    headers = ('Task', 'State', 'Cycles', 'Timeout', 'Sleep', 'Task')
    widths = (6, 12, 10, 7, 7, 50)
    sout = ''
    for h, w in zip(headers, widths):
        sout += '%-*s ' % (w, h)
    sout += '\n'
    sout += ' '.join(w * '-' for w in widths)
    sout += '\n'
    timestamp = time.monotonic()
    for taskid in sorted(kernel._tasks):
        task = kernel._tasks.get(taskid)
        if task:
            timeout_remaining = format(
                (task.timeout - timestamp),
                '0.6f')[:7] if task.timeout else 'None'
            sleep_remaining = format(
                (task.sleep - timestamp),
                '0.6f')[:7] if task.sleep else 'None'

            sout += '%-*d %-*s %-*d %-*s %-*s %-*s\n' % (widths[0], taskid,
                                                         widths[1], task.state,
                                                         widths[2], task.cycles,
                                                         widths[3], timeout_remaining,
                                                         widths[4], sleep_remaining,
                                                         widths[5], task.name)
    out.write(sout)

# Implementation of the 'where' command
def where(taskid, kernel=None, out=sys.stdout):
    if kernel is None:
        kernel = meta._locals.kernel
    task = kernel._tasks.get(taskid)
    if task:
        out.write(task.traceback() + '\n')
    else:
        out.write('No task %d\n' % taskid)
    
class Monitor(object):
    '''
    Task monitor that runs concurrently to the curio kernel in a
    separate thread. This can watch the kernel and provide debugging.
    '''

    def __init__(self, kern, host=MONITOR_HOST, port=MONITOR_PORT):
        self.kernel = kern
        self.address = (host, port)
        self._closing = None
        self._ui_thread = None

    def close(self):
        if self._closing:
            self._closing.set()
        if self._ui_thread:
            self._ui_thread.join()

    def start(self):
        '''
        Function to start the monitor
        '''
        log.info('Starting Curio monitor at %s', self.address)
        self._closing = threading.Event()        
        self._ui_thread = threading.Thread(target=self.server, args=(), daemon=True)
        self._ui_thread.start()

    def server(self):
        '''
        Synchronous kernel for the monitor.  This runs in a separate thread
        from curio itself.
        '''
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        # set the timeout to prevent the server loop from
        # blocking indefinitaly on sock.accept()
        sock.settimeout(0.5)
        sock.bind(self.address)
        sock.listen(1)
        with sock:
            while not self._closing.is_set():
                try:
                    client, addr = sock.accept()
                    with client:
                        client.settimeout(0.5)
                        # This bit of magic is for reading lines of input while still allowing timeouts
                        # and the ability for the monitor to die when curio exits.  See Issue #108.
                        def readlines():
                            buffer = bytearray()
                            while not self._closing.is_set():
                                index = buffer.find(b'\n')
                                if index >= 0:
                                    line = buffer[:index + 1].decode('latin-1')
                                    del buffer[:index + 1]
                                    yield line
                                try:
                                    chunk = client.recv(1000)
                                    if not chunk:
                                        break
                                    buffer.extend(chunk)
                                except socket.timeout:
                                    pass

                        sout = client.makefile('w', encoding='latin-1')
                        self.interactive_loop(sout, readlines())
                        sout.close()
                except socket.timeout:
                    continue

    def interactive_loop(self, sout, input_lines):
        '''
        Main interactive loop of the monitor
        '''
        sout.write('\nCurio Monitor: %d tasks running\n' % len(self.kernel._tasks))
        sout.write('Type help for commands\n')
        while True:
            sout.write('curio > ')
            sout.flush()
            resp = next(input_lines, None)
            if not resp:
                return
            try:
                if resp.startswith('q'):
                    self.command_exit(sout)
                    return

                elif resp.startswith('pa'):
                    _, taskid_s = resp.split()
                    self.command_parents(sout, int(taskid_s))

                elif resp.startswith('p'):
                    self.command_ps(sout)

                elif resp.startswith('exit'):
                    self.command_exit(sout)
                    return

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
         parents taskid   : List task parents
         quit             : Leave the monitor
''')

    def command_ps(self, sout):
        ps(self.kernel, sout)

    def command_where(self, sout, taskid):
        where(taskid, self.kernel, sout)

    def command_parents(self, sout, taskid):
        while taskid:
            task = self.kernel._tasks.get(taskid)
            if task:
                sout.write('%-6d %12s %s\n' % (task.id, task.state, task.name))
                taskid = task.parentid
            else:
                break

    def command_exit(self, sout):
        sout.write('Leaving monitor.\n')
        sout.flush()

def monitor_client(host, port):
    '''
    Client to connect to the monitor via a socket
    '''
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    def display(sock):
        while (chunk := sock.recv(1000)):
            sys.stdout.write(chunk.decode('utf-8'))
            sys.stdout.flush()
        os._exit(0)
    threading.Thread(target=display, args=[sock], daemon=True).start()
    while True:
        line = sys.stdin.readline()
        sock.sendall(line.encode('utf-8'))
    sock.close()

def main():
    parser = argparse.ArgumentParser("usage: python -m curio.monitor [options]")
    parser.add_argument("-H", "--host", dest="monitor_host",
                        default=MONITOR_HOST, type=str,
                        help="monitor host ip")

    parser.add_argument("-p", "--port", dest="monitor_port",
                        default=MONITOR_PORT, type=int,
                        help="monitor port number")
    args = parser.parse_args()
    monitor_client(args.monitor_host, args.monitor_port)


if __name__ == '__main__':
    main()
