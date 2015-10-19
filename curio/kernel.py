# kernel.py

import socket
import heapq
import time
import threading
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

class SignalSet(object):
    def __init__(self, *signos):
        self.signos = signos             # List of all signal numbers being tracked
        self.pending = deque()           # Pending signals received
        self.waiting = None              # Waiting task (if any)
        self.watching = False

    
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

class Kernel(object):
    def __init__(self, selector=None):
        if selector is None:
            selector = DefaultSelector()
        self._selector = selector
        self._ready = kqueue()      # Tasks ready to run
        self._tasks = { }           # Task table
        self._current = None        # Current task
        self._sleeping = []         # Heap of tasks waiting on a timer for any reason
        self._signals = None        # Dict of watched signals (initialized if signals used)
        self._default_signals = {}  # Dict of default signal handlers
        self.njobs = 0

        # Create task responsible for waiting the event loop
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self._notify_sock.setblocking(False)
        # signal.set_wakeup_fd(self._notify_sock.fileno())     
        self.add_task(self._wait_task(), daemon=True)

    def __del__(self):
        self._notify_sock.close()
        self._wait_sock.close()

    # Callback that causes the kernel to wake on non-I/O events
    def _wake(self, task=None, value=None, exc=None):
        if task:
            self.reschedule_task(task, value, exc)
        self._notify_sock.send(b'\x00')

    # Internal task that monitors the loopback socket--allowing the kernel to
    # awake for non-I/O events.
    @coroutine
    def _wait_task(self):
        while True:
            yield 'trap_read_wait', self._wait_sock
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
                        self.reschedule_task(sigset.waiting, value=signo)
                        sigset.waiting = None

    # Traps.  These implement the low-level functionality that is triggered by coroutines.
    # You shouldn't invoke these directly. Instead, coroutines use a statement such as
    #   
    #   yield 'trap_read_wait', sock, timeout
    #
    # To execute these methods.

    def trap_read_wait(self, fileobj, timeout=None):
        self._selector.register(fileobj, EVENT_READ, self._current)
        self._current.state = 'READ_WAIT'
        self._current.fileobj = fileobj
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_write_wait(self, fileobj, timeout=None):
        self._selector.register(fileobj, EVENT_WRITE, self._current)
        self._current.state = 'WRITE_WAIT'
        self._current.fileobj = fileobj
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_future_wait(self, future, timeout=None):
        future.add_done_callback(lambda fut, task=self._current: self._wake(task))
        self._current.state = 'FUTURE_WAIT'
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_new_task(self, coro, daemon=False):
        task = Task(coro)

        self._tasks[task.id] = task
        self.reschedule_task(task)
        if not daemon:
            self.njobs += 1
            ptask = self._current if self._current else self._tasks[1]
            task.parent_id = ptask.id
            ptask.children.add(task)
            
        if self._current:
            self.reschedule_task(self._current, value=task)
        return task.id

    def trap_reschedule_tasks(self, queue, n=1, value=None, exc=None):
        while n > 0:
            self.reschedule_task(queue.popleft(), value=value, exc=exc)
            n -= 1
        self.reschedule_task(self._current)

    def trap_join_task(self, task, timeout=None):
        if task.waiting is None:
            task.waiting = kqueue()
        self.trap_wait_queue(task.waiting, 'TASK_JOIN', timeout)

    def trap_cancel_task(self, task, timeout=None):
        self.cancel_task(task.id)
        self.trap_join_task(task, timeout)

    def trap_wait_queue(self, queue, state, timeout=None):
        queue.append(self._current)
        self._current.state = state
        self._current.waiting_in = queue
        if timeout is not None:
            self._set_timeout(timeout)

    def _set_timeout(self, seconds, sleep_type='timeout'):
        self._current.timeout = time.monotonic() + seconds
        item = (self._current.timeout, self._current, sleep_type)
        heapq.heappush(self._sleeping, item)
        return item
        
    def trap_sleep(self, seconds):
        item = self._set_timeout(seconds, 'sleep')
        self._current.state = 'TIME_SLEEP'

    def trap_sigwatch(self, sigset):
        # Initial the signal handling part of the kernel
        if self._signals is None:
            self._signals = defaultdict(list)
            signal.set_wakeup_fd(self._notify_sock.fileno())     
            
        for signo in sigset.signos:
            if not self._signals[signo]:
                self._default_signals[signo] = signal.signal(signo, lambda signo, frame:None)
            self._signals[signo].append(sigset)

        self.reschedule_task(self._current)
        
    def trap_sigunwatch(self, sigset):
        for signo in sigset.signos:
            if sigset in self._signals[signo]:
                self._signals[signo].remove(sigset)

            # If there are no active watchers for a signal remaining, revert to default behavior
            if not self._signals[signo]:
                signal.signal(signo, self._default_signals[signo])
                del self._signals[signo]
        self.reschedule_task(self._current)

    def trap_sigwait(self, sigset, timeout):
        sigset.waiting = self._current
        self._current.sigset = sigset
        self._current.state = 'SIGNAL_WAIT'
        if timeout is not None:
            self._set_timeout(timeout)

    # I/O 
    def poll_for_io(self):
        if self._sleeping:
            timeout = self._sleeping[0][0] - time.monotonic()
        else:
            timeout = None

        events = self._selector.select(timeout)
        for key, mask in events:
            task = key.data
            self._selector.unregister(key.fileobj)
            self.reschedule_task(task)

        # Process sleeping tasks
        current = time.monotonic()
        while self._sleeping and self._sleeping[0][0] <= current:
            tm, task, sleep_type = heapq.heappop(self._sleeping)
            if sleep_type == 'sleep':
                self.reschedule_task(task)
            elif sleep_type == 'timeout':
                # If a timeout occurs, verify that the task still exists and that
                # its locally set timeout value matches the time value.  If not,
                # the timeout is ignored (it means that the task was already
                # cancelled or that the previous operation involving a timeout
                # already ran to completion).
                
                if task.timeout == tm:
                    self.cancel_task(task.id, exc=TimeoutError)

    # Kernel central loop
    def run(self, detached=False):
        if detached:
            threading.Thread(target=self.run).start()
            return

        while self.njobs > 0:
            self._current = None

            # Poll for I/O as long as there is nothing to run
            while not self._ready:
                self.poll_for_io()

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
                    trap = getattr(self, op, None)
                    assert trap, "Unknown trap: %s" % op
                    trap(*args)

                except (StopIteration, CancelledError) as e:
                    self._terminate_current(value = e.value if isinstance(e, StopIteration) else None)

                except Exception as e:
                    self._current.exc_info = sys.exc_info()
                    self._current.state = 'CRASHED'
                    exc = TaskError('Task Crashed')
                    exc.__cause__ = e
                    self._terminate_current(exc=exc)
                    log.error('Curio: Task Crash: %s' % self._current, exc_info=True)

        self._current = None

    def _terminate_current(self, value=None, exc=None):
        self._current.next_value = value
        if self._current.parent_id:
            self.njobs -=1

        if self._current.waiting:
            for task in self._current.waiting:
                self.reschedule_task(task, value=value, exc=exc)
            self._current.waiting = None
        self._current.terminated = True
        del self._tasks[self._current.id]

        # Remove the task from the parent child list
        parent = self._tasks.get(self._current.parent_id)
        if parent:
            parent.children.remove(self._current)

        # Reassign all children to init task
        init = self._tasks[1]
        init.children.update(self._current.children)
        for task in self._current.children:
            task.parent_id = 1
        self._current.children = set()

        self._current = None

    # Task management
    def reschedule_task(self, task, value=None, exc=None):
        # Note: If the task is not in the task list, it means that it was cancelled.
        # In that case, we ignore the request to reschedule. This can happen with
        # cancellations of timeouts.  If the task has an error set, it's also
        # not rescheduled.
        if task.id in self._tasks and not task.exc_info:
            self._ready.append(task)
            task.next_value = value
            task.next_exc = exc
            task.state = 'READY'
            task.fileobj = task.waiting_in = task.timeout = task.sigset = None
        else:
            log.debug('Task %r not rescheduled.', task)

    def add_task(self, coro, daemon=False):
        assert self._current is None
        return self.trap_new_task(coro, daemon)

    def cancel_task(self, taskid, exc=CancelledError):
        task = self._tasks[taskid]

        if task == self._current:
            raise CancelledError()

        # Remove the task from whatever it's waiting on right now
        if task.fileobj is not None:
            self._selector.unregister(task.fileobj)
            
        if task.waiting_in:
            task.waiting_in.remove(task)

        if task.sigset:
            task.sigset.waiting = None
            task.sigset = None

        # Reschedule it with a pending exception
        self.reschedule_task(task, exc=exc())

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

# ----- Public functions corresponding to the kernel traps

@coroutine
def read_wait(fileobj, timeout=None):
    yield 'trap_read_wait', fileobj, timeout

@coroutine
def write_wait(fileobj, timeout=None):
    yield 'trap_write_wait', fileobj, timeout

@coroutine
def future_wait(future, timeout=None):
    yield 'trap_future_wait', future, timeout

@coroutine
def sleep(seconds):
    yield 'trap_sleep', seconds

@coroutine
def new_task(coro, *, daemon=False):
    return (yield 'trap_new_task', coro, daemon)

@coroutine
def cancel_task(task, timeout=None):
    yield 'trap_cancel_task', task, timeout

@coroutine
def join_task(task, timeout=None):
    yield 'trap_join_task', task, timeout

@coroutine
def reschedule_tasks(queue, n=1, value=None, exc=None):
    yield 'trap_reschedule_tasks', queue, n, value, exc
    
@coroutine
def wait_on_queue(queue, state, timeout=None):
    '''
    Wait on a queue-like object.  Optionally set a timeout.
    '''
    yield 'trap_wait_queue', queue, state, timeout

@coroutine
def sigwatch(sigset):
    yield 'trap_sigwatch', sigset

@coroutine
def sigunwatch(sigset):
    yield 'trap_sigunwatch', sigset

@coroutine
def sigwait(sigset, timeout=None):
    yield 'trap_sigwait', sigset, timeout

async def run_in_executor(exc, callable, *args):
    future = exc.submit(callable, *args)
    await future_wait(future)
    return future.result()
    
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
            
        
