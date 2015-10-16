# kernel.py

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, namedtuple
import socket
from types import coroutine
import heapq
import time
import threading
import os
import sys
import logging
import inspect

log = logging.getLogger(__name__)

class CurioError(Exception):
    pass

class CancelledError(CurioError):
    pass

class TimeoutError(CurioError):
    pass

class Task(object):
    def __init__(self, coro):
        self.coro = coro          # Underlying generator/coroutine
        self.cycles = 0           # Execution cycles completed
        self.state = 'INITIAL'    # Execution state
        self.fileobj = None       # File object waiting on (if any)
        self.waiting_in = None    # Queue where waiting (if any)
        self.timeout = None       # Pending timeout (if any)
        self.exc_info = None      # Exception info (if any)
        self.next_value = None    # Next value to send on execution
        self.next_exc = None      # Next exception to send on execution
        self.waiting = None       # Optional set of tasks waiting to join with this one

    def __repr__(self):
        return 'Task(%r)' % self.coro

    def __str__(self):
        return self.coro.__qualname__

class Kernel(object):
    def __init__(self, selector=None):
        if selector is None:
            selector = DefaultSelector()
        self._selector = selector
        self._ready = deque()       # Tasks ready to run
        self._tasks = { }           # Task table
        self._current = None        # Current task
        self._sleeping = []         # Heap of tasks waiting on timer
        self.njobs = 0

        # Create task responsible for waiting the event loop
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self.add_task(self._wait_task(), daemon=True)

    # Callback that causes the kernel to wake on non-I/O events
    def _wake(self, task, value=None, exc=None):
        # If the task no longer exists in the task table, perhaps it was cancelled
        # or killed for some reason. In that case, there's no point in rescheduling it.
        # If the task is in the task table, but has exception information set,
        # it means it crashed.   Either way, we don't reschedule. Oh well.
        if id(task) in self._tasks and not task.exc_info:
            self.reschedule_task(task, value, exc)
            self._notify_sock.send(b'x')

    # Internal task that monitors the loopback socket--allowing the kernel to
    # awake for non-I/O events.
    @coroutine
    def _wait_task(self):
        while True:
            yield 'trap_read_wait', self._wait_sock
            data = self._wait_sock.recv(100)

    # Traps.  These implement low-level functionality.  Do not invoke directly.
    def trap_read_wait(self, resource, timeout=None):
        self._selector.register(resource, EVENT_READ, self._current)
        self._current.state = 'READ_WAIT'
        self._current.fileobj = resource
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_write_wait(self, resource, timeout=None):
        self._selector.register(resource, EVENT_WRITE, self._current)
        self._current.state = 'WRITE_WAIT'
        self._current.fileobj = resource
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_future_wait(self, future, timeout=None):
        future.add_done_callback(lambda fut, task=self._current: self._wake(task))
        self._current.state = 'FUTURE_WAIT'
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_wait(self, queue, state, timeout=None):
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
                    self.cancel_task(id(task), exc=TimeoutError)

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
                taskid = id(self._current)
                assert taskid in self._tasks
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
                    # Reschedule any waiting jobs 
                    if self._current.waiting:
                        for task in self._current.waiting:
                            self.reschedule_task(task, 
                                                 value = e.value if isinstance(e, StopIteration) else None,
                                                 exc = e if isinstance(e, CancelledError) else None)
                        self._current.waiting = None
                    del self._tasks[taskid]
                    self.njobs -= 1

                except Exception as e:
                    self._current.exc_info = sys.exc_info()
                    self._current.state = 'CRASHED'
                    log.error('Curio: Task Crash: %s' % self._current, exc_info=True)

    # Task management
    def reschedule_task(self, task, value=None, exc=None):
        # Note: If the task is not in the task list, it means that it was cancelled.
        # In that case, we ignore requests to reschedule.   This can happen with
        # cancellations of timeouts
        if id(task) in self._tasks and not task.exc_info:
            self._ready.append(task)
            task.next_value = value
            task.next_exc = exc
            task.state = 'READY'
            task.fileobj = task.waiting_in = task.timeout = None

    def add_task(self, coro, daemon=False):
        task = Task(coro)
        self._tasks[id(task)] = task
        self.reschedule_task(task)
        if not daemon:
            self.njobs += 1
        return id(task)

    def cancel_task(self, taskid, exc=CancelledError):
        task = self._tasks[taskid]
        if task == self._current:
            raise CancelledError()

        # Remove the task from whatever it's waiting on right now
        if task.fileobj is not None:
            self._selector.unregister(task.fileobj)
            
        if task.waiting_in:
            task.waiting_in.remove(task)

        # Reschedule it with a pending exception
        self.reschedule_task(task, exc=exc())

    async def join(self, taskid, *, timeout=None):
        task = self._tasks[taskid]
        if task.waiting is None:
            task.waiting = []
        result = await self.wait_on(task.waiting, 'TASK_JOIN', timeout=timeout)
        return result

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

    # System calls
    @coroutine
    def wait_on(self, queue, state, timeout=None):
        '''
        Wait on a queue-like object.  Optionally set a timeout.
        '''
        return (yield 'trap_wait', queue, state, timeout)
        
    @coroutine
    def run_in_executor(self, exc, callable, *args):
        future = exc.submit(callable, *args)
        yield 'trap_future_wait', future
        return future.result()

@coroutine
def sleep(seconds):
    yield 'trap_sleep', seconds

_default_kernel = None
def get_kernel():
    '''
    Return the default kernel.
    '''
    global _default_kernel
    if _default_kernel is None:
        _default_kernel = Kernel()
    return _default_kernel

__all__ = [ 'Kernel', 'get_kernel', 'sleep', 
            'CancelledError', 'TimeoutError', ]
            
        
