# curio/monitor.py
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

from .file import File
from .kernel import _kernel_reference, SignalSet, CancelledError

def get_stack(task):
    frames = []
    try:
        # 'async def' coroutines
        f = task.coro.cr_frame
    except AttributeError:
        f = task.coro.gi_frame
    if f is not None:
        while f is not None:
            frames.append(f)
            f = f.f_back
        frames.reverse()
    return frames

def get_stack(task):
    frames = []
    coro = task.coro
    while coro:
        f = coro.cr_frame if hasattr(coro, 'cr_frame') else coro.gi_frame
        if f is not None:
            frames.append(f)
        coro = coro.cr_await if hasattr(coro, 'cr_await') else coro.gi_yieldfrom
    return frames

def print_stack(task):
        extracted_list = []
        checked = set()
        for f in get_stack(task):
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
    stdin = File(sys.stdin.buffer.raw)
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
              elif resp.startswith(b'w'):
                   try:
                        _, taskid_s = resp.split()
                        taskid = int(taskid_s)
                        if taskid in kernel._tasks:
                             print_stack(kernel._tasks[taskid])
                             print()
                   except Exception as e:
                        print('Bad command', e)
                             
              elif resp.startswith(b'h'):
                   print(
     '''Commands:
         ps               : Show task table
         where taskid     : Show stack frames for a task
         cancel taskid    : Cancel a task
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

