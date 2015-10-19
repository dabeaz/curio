# kernel.py

import socket
import heapq
import time
import os
import sys
import logging
import inspect
import signal

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, defaultdict
from types import coroutine

log = logging.getLogger(__name__)

# kqueue is the datatype used by the kernel for all of its queuing functionality.
# Any time a task queue is needed, use this type instead of directly hard-coding the
# use of a deque.  This will make sure the code continues to work even if the
# queue type is changed later.

kqueue = deque

# --- Curio specific exceptions

class CurioError(Exception):
    pass

class CancelledError(CurioError):
    pass

class TimeoutError(CurioError):
    pass

class TaskError(CurioError):
    pass

# Task class wraps a coroutine, but provides other information about 
# the task itself for the purposes of debugging, scheduling, timeouts, etc.

class Task(object):
    _lastid = 1
    def __init__(self, coro):
        self.id = Task._lastid
        Task._lastid += 1
        self.parent_id = None     # Parent task id
        self.children = set()     # Set of child tasks
        self.coro = coro          # Underlying generator/coroutine
        self.cycles = 0           # Execution cycles completed
        self.state = 'INITIAL'    # Execution state
        self.fileobj = None       # File object waiting on (if any)
        self.future = None        # Future being waited on (if any)
        self.waiting_in = None    # Queue where waiting (if any)
        self.timeout = None       # Pending timeout (if any)
        self.exc_info = None      # Exception info (if any on crash)
        self.next_value = None    # Next value to send on execution
        self.next_exc = None      # Next exception to send on execution
        self.waiting = None       # Optional set of tasks waiting to join with this one
        self.sigset = None        # Signal set waiting on (if any)
        self.terminated = False   # Terminated?

    def __repr__(self):
        return 'Task(id=%r, %r)' % (self.id, self.coro)

    def __str__(self):
        return self.coro.__qualname__

    async def join(self, *, timeout=None):
        '''
        Waits for a task to terminate.  Returns the return value (if any)
        or raises a TaskError if the task crashed with an exception.
        '''
        if not self.terminated:
            await join_task(self, timeout)
            
        if self.exc_info:
            raise TaskError('Task crash') from self.exc_info[1]
        else:
            return self.next_value

    async def cancel(self, *, timeout=None):
        '''
        Cancels a task.  Does not return until the task actually terminates.
        '''
        if not self.terminated:
            for task in list(self.children):
                await cancel_task(task, timeout)

            await cancel_task(self, timeout)

# The SignalSet class represents a set of Unix signals being monitored. 
class SignalSet(object):
    def __init__(self, *signos):
        self.signos = signos             # List of all signal numbers being tracked
        self.pending = deque()           # Pending signals received
        self.waiting = None              # Task waiting for the signals (if any)
        self.watching = False            # Are the signals being watched right now?

    
    async def __aenter__(self):
        assert not self.watching
        await sigwatch(self)
        self.watching = True
        return self

    async def __aexit__(self, *args):
        await sigunwatch(self)
        self.watching = False

    async def wait(self, *, timeout=None):
        if not self.watching:
            async with self:
                return await self.wait(timeout=timeout)

        while True:
            if self.pending:
                return self.pending.popleft()
            await sigwait(self, timeout)

# Underlying kernel that drives everything

class Kernel(object):
    def __init__(self, selector=None):
        if selector is None:
            selector = DefaultSelector()
        self._selector = selector
        self._ready = kqueue()      # Tasks ready to run
        self._tasks = { }           # Task table
        self._current = None        # Current task
        self._sleeping = []         # Heap of tasks waiting on a timer for any reason
        self._signals = None        # Dict { signo: [ sigsets ] } of watched signals (initialized only if signals used)
        self._default_signals = {}  # Dict of default signal handlers
        self._njobs = 0             # Number of non-daemonic jobs running
        self._running = False       # Kernel running?

        # Create the init task responsible for waking the event loop and processing signals
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self._notify_sock.setblocking(False)
        self.add_task(self._init_task(), daemon=True)

    def __del__(self):
        self._notify_sock.close()
        self._wait_sock.close()

    # Callback that causes the kernel to wake on non-I/O events
    def _wake(self, task=None, value=None, exc=None):
        if task:
            self._reschedule_task(task, value, exc)
        self._notify_sock.send(b'\x00')

    # Internal task that monitors the loopback socket--allowing the kernel to
    # awake for non-I/O events.  Also processes incoming signals
    async def _init_task(self):
        while True:
            await read_wait(self._wait_sock)
            data = self._wait_sock.recv(100)

            # Any non-null bytes received here are assumed to be received signals.
            # See if there are any pending signal sets and unblock if needed 
            if not self._signals:
                continue

            signals = (signal.Signals(n) for n in data if n in self._signals)
            for signo in signals:
                for sigset in self._signals[signo]:
                    sigset.pending.append(signo)
                    if sigset.waiting:
                        self._reschedule_task(sigset.waiting, value=signo)
                        sigset.waiting = None

    # Public task management functions.  These are the only methods safe to use
    # outside of the kernel loop. They must be called when the loop is stopped.

    def add_task(self, coro, daemon=False):
        assert self._current is None
        return self._new_task(coro, daemon).id

    # Internal task management functions. 
    def _new_task(self, coro, daemon=False):
        '''
        Create a new task in the kernel.  If daemon is True, the task is
        created with no parent task.
        '''
        task = Task(coro)
        self._tasks[task.id] = task
        self._reschedule_task(task)
        if not daemon:
            self._njobs += 1
            ptask = self._current if self._current else self._tasks[1]
            task.parent_id = ptask.id
            ptask.children.add(task)
        return task

    def _reschedule_task(self, task, value=None, exc=None):
        '''
        Reschedule a task, putting it back on the ready queue so that it can run.
        value and exc specify a value or exception to send into the underlying 
        coroutine when it is rescheduled.
        '''
        assert task.id in self._tasks, 'Task %r not in the table table' % task
        self._ready.append(task)
        task.next_value = value
        task.next_exc = exc
        task.state = 'READY'
        task.fileobj = task.waiting_in = task.timeout = task.sigset = task.future = None

    def _cancel_task(self, taskid, exc=CancelledError):
        '''
        Cancel a task. This causes a CancelledError exception to raise in the
        underlying coroutine.  The coroutine can elect to catch the exception
        and continue to run to perform cleanup actions.  However, it would 
        normally terminate shortly afterwards.   This method is also used to 
        raise timeouts.
        '''
        
        task = self._tasks[taskid]

        if task == self._current:
            raise CancelledError()

        # Remove the task from whatever it's waiting on right now
        if task.fileobj is not None:
            self._selector.unregister(task.fileobj)
            
        if task.waiting_in:
            task.waiting_in.remove(task)

        if task.future:
            future.cancel()

        if task.sigset:
            task.sigset.waiting = None
            task.sigset = None

        # Reschedule it with a pending exception
        self._reschedule_task(task, exc=exc())

    def _cleanup_task(self, task, value=None, exc=None):
        '''
        Cleanup task.  This is called after the underlying coroutine has
        terminated.  value and exc give the return value or exception of
        the coroutine.  This wakes any tasks waiting to join and removes
        the terminated task from its parent/children.
        '''
        task.next_value = value
        if task.parent_id:
            self._njobs -=1

        if task.waiting:
            for wtask in task.waiting:
                self._reschedule_task(wtask, value=value, exc=exc)
            task.waiting = None
        task.terminated = True
        del self._tasks[task.id]

        # Remove the task from the parent child list
        parent = self._tasks.get(task.parent_id)
        if parent:
            parent.children.remove(task)

        # Reassign all remaining children to init task
        init = self._tasks[1]
        init.children.update(task.children)
        for ctask in task.children:
            ctask.parent_id = 1
        task.children = set()

    def _set_timeout(self, seconds, sleep_type='timeout'):
        '''
        Set a timeout value on the task.  Returns a tuple (endtime, task, sleep_type)
        suitable for using the sleeping priority queue.
        '''
        self._current.timeout = time.monotonic() + seconds
        item = (self._current.timeout, self._current, sleep_type)
        heapq.heappush(self._sleeping, item)
        return item

    # I/O 
    def _poll_for_io(self):
        if self._sleeping:
            timeout = self._sleeping[0][0] - time.monotonic()
        else:
            timeout = None

        events = self._selector.select(timeout)
        for key, mask in events:
            task = key.data
            self._selector.unregister(key.fileobj)
            self._reschedule_task(task)

        # Process sleeping tasks
        current = time.monotonic()
        while self._sleeping and self._sleeping[0][0] <= current:
            tm, task, sleep_type = heapq.heappop(self._sleeping)
            # When a task wakes, verify that the timeout value matches that stored
            # on the task. If it differs, it means that the task completed its
            # operation, was cancelled, or is no longer concerned with this
            # sleep operation.  In that case, we do nothing
            if tm == task.timeout:
                if sleep_type == 'sleep':
                    self._reschedule_task(task)
                elif sleep_type == 'timeout':
                    self._cancel_task(task.id, exc=TimeoutError)

    # Kernel central loop
    def run(self, pdb=False):
        '''
        Run the kernel until no more non-daemonic tasks remain.
        '''
        self._running = True
        while self._njobs > 0 and self._running:
            self._current = None

            # Poll for I/O as long as there is nothing to run
            while not self._ready:
                self._poll_for_io()

            # Run everything that's ready
            while self._ready:
                self._current = self._ready.popleft()
                assert self._current.id in self._tasks
                try:
                    self._current.state = 'RUNNING'
                    self._current.cycles += 1
                    if self._current.next_exc is None:
                        op, *args = self._current.coro.send(self._current.next_value)
                    else:
                        op, *args = self._current.coro.throw(self._current.next_exc)

                    # Execute a trap. Trap functions are defined by methods below
                    trap = getattr(self, op, None)
                    assert trap, "Unknown trap: %s" % op
                    trap(*args)

                except (StopIteration, CancelledError) as e:
                    self._cleanup_task(self._current, value = e.value if isinstance(e, StopIteration) else None)

                except Exception as e:
                    self._current.exc_info = sys.exc_info()
                    self._current.state = 'CRASHED'
                    exc = TaskError('Task Crashed')
                    exc.__cause__ = e
                    self._cleanup_task(self._current, exc=exc)
                    log.error('Curio: Task Crash: %s' % self._current, exc_info=True)
                    if pdb:
                        import pdb as _pdb
                        _pdb.post_mortem(self._current.exc_info[2])

        self._current = None

    def stop(self):
        '''
        Stop the kernel loop.
        '''
        self._running = False

    # Traps.  These implement the low-level functionality that is triggered by coroutines.
    # You shouldn't invoke these directly. Instead, coroutines use a statement such as
    #   
    #   yield '_trap_read_wait', sock, timeout
    #
    # To execute these methods.

    def _trap_read_wait(self, fileobj, timeout=None):
        self._selector.register(fileobj, EVENT_READ, self._current)
        self._current.state = 'READ_WAIT'
        self._current.fileobj = fileobj
        if timeout is not None:
            self._set_timeout(timeout)

    def _trap_write_wait(self, fileobj, timeout=None):
        self._selector.register(fileobj, EVENT_WRITE, self._current)
        self._current.state = 'WRITE_WAIT'
        self._current.fileobj = fileobj
        if timeout is not None:
            self._set_timeout(timeout)

    def _trap_future_wait(self, future, timeout=None):
        future.add_done_callback(lambda fut, task=self._current: self._wake(task))
        self._current.state = 'FUTURE_WAIT'
        self._current.future = future
        if timeout is not None:
            self._set_timeout(timeout)

    def _trap_new_task(self, coro, daemon=False):
        task = self._new_task(coro, daemon)
        self._reschedule_task(self._current, value=task)

    def _trap_reschedule_tasks(self, queue, n=1, value=None, exc=None):
        while n > 0:
            self._reschedule_task(queue.popleft(), value=value, exc=exc)
            n -= 1
        self._reschedule_task(self._current)

    def _trap_join_task(self, task, timeout=None):
        if task.waiting is None:
            task.waiting = kqueue()
        self._trap_wait_queue(task.waiting, 'TASK_JOIN', timeout)

    def _trap_cancel_task(self, task, timeout=None):
        self._cancel_task(task.id)
        self._trap_join_task(task, timeout)

    def _trap_wait_queue(self, queue, state, timeout=None):
        queue.append(self._current)
        self._current.state = state
        self._current.waiting_in = queue
        if timeout is not None:
            self._set_timeout(timeout)
        
    def _trap_sleep(self, seconds):
        item = self._set_timeout(seconds, 'sleep')
        self._current.state = 'TIME_SLEEP'

    def _trap_sigwatch(self, sigset):
        # Initialize the signal handling part of the kernel if not done already
        # Note: This only works if running in the main thread
        if self._signals is None:
            self._signals = defaultdict(list)
            signal.set_wakeup_fd(self._notify_sock.fileno())     
            
        for signo in sigset.signos:
            if not self._signals[signo]:
                self._default_signals[signo] = signal.signal(signo, lambda signo, frame:None)
            self._signals[signo].append(sigset)

        self._reschedule_task(self._current)
        
    def _trap_sigunwatch(self, sigset):
        for signo in sigset.signos:
            if sigset in self._signals[signo]:
                self._signals[signo].remove(sigset)

            # If there are no active watchers for a signal, revert it back to default behavior
            if not self._signals[signo]:
                signal.signal(signo, self._default_signals[signo])
                del self._signals[signo]
        self._reschedule_task(self._current)

    def _trap_sigwait(self, sigset, timeout):
        sigset.waiting = self._current
        self._current.sigset = sigset
        self._current.state = 'SIGNAL_WAIT'
        if timeout is not None:
            self._set_timeout(timeout)

    # Debugging
    def ps(self):
        headers = ('Task ID', 'State', 'Cycles', 'Timeout', 'Task')
        widths = (11, 12, 10, 7, 50)
        for h, w in zip(headers, widths):
            print('%-*s' % (w, h), end=' ')
        print()
        print(' '.join(w*'-' for w in widths))
        timestamp = time.monotonic()
        for taskid in sorted(self._tasks):
            task = self._tasks[taskid]
            remaining = format((task.timeout - timestamp), '0.6f')[:7] if task.timeout else 'None'
            print('%-*d %-*s %-*d %-*s %-*s' % (widths[0], taskid, 
                                                widths[1], task.state,
                                                widths[2], task.cycles,
                                                widths[3], remaining,
                                                widths[4], task))

# Coroutines corresponding to the kernel traps.  These functions provide the bridge from
# tasks to the underlying kernel. This is the only place with the explicit @coroutine
# decorator needs to be used.  All other code in curio and in user-tasks should use
# async/await instead.   Direct use by users is allowed, but if you're working with
# these traps directly, there is probably a higher level interface that simplifies
# the problem you're trying to solve (e.g., Socket, File, objects, etc.)

@coroutine
def read_wait(fileobj, timeout=None):
    '''
    Wait until reading can be performed.
    '''
    yield '_trap_read_wait', fileobj, timeout

@coroutine
def write_wait(fileobj, timeout=None):
    '''
    Wait until writing can be performed.
    '''
    yield '_trap_write_wait', fileobj, timeout

@coroutine
def future_wait(future, timeout=None):
    '''
    Wait for the future of a Future to be computed.
    '''
    yield '_trap_future_wait', future, timeout

@coroutine
def sleep(seconds):
    '''
    Sleep for a specified number of seconds.
    '''
    yield '_trap_sleep', seconds

@coroutine
def new_task(coro, *, daemon=False):
    '''
    Create a new task in the kernel.
    '''
    return (yield '_trap_new_task', coro, daemon)

@coroutine
def cancel_task(task, timeout=None):
    '''
    Cancel a task.  Causes a CancelledError exception to raise in the task.
    '''
    yield '_trap_cancel_task', task, timeout

@coroutine
def join_task(task, timeout=None):
    '''
    Wait for a task to terminate.
    '''
    yield '_trap_join_task', task, timeout

    
@coroutine
def wait_on_queue(queue, state, timeout=None):
    '''
    Put the task to sleep on a kernel queue.
    '''
    yield '_trap_wait_queue', queue, state, timeout

@coroutine
def reschedule_tasks(queue, n=1, value=None, exc=None):
    '''
    Reschedule one or more tasks waiting on a kernel queue.
    '''
    yield '_trap_reschedule_tasks', queue, n, value, exc

@coroutine
def sigwatch(sigset):
    '''
    Start monitoring a signal set
    '''
    yield '_trap_sigwatch', sigset

@coroutine
def sigunwatch(sigset):
    '''
    Stop watching a signal set
    '''
    yield '_trap_sigunwatch', sigset

@coroutine
def sigwait(sigset, timeout=None):
    '''
    Wait for a signal to arrive.
    '''
    yield '_trap_sigwait', sigset, timeout
    
_default_kernel = None
def get_kernel():
    '''
    Return the default kernel.
    '''
    global _default_kernel
    if _default_kernel is None:
        _default_kernel = Kernel()
    return _default_kernel

__all__ = [ 'Kernel', 'get_kernel', 'sleep', 'new_task', 'wait_on_queue', 'reschedule_tasks', 'kqueue', 
            'SignalSet', 'CancelledError', 'TimeoutError', ]
            
        
