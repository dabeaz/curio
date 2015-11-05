# kernel.py
# 
# Copyright (C) 2015
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# This is the core of curio.   Definitions for tasks, signal sets, and the kernel
# are here.

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
from contextlib import contextmanager

# Logger where uncaught exceptions from crashed tasks are logged
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

class TaskError(CurioError):
    pass

class _CancelRetry(Exception):
    pass

# Task class wraps a coroutine, but provides other information about 
# the task itself for the purposes of debugging, scheduling, timeouts, etc.

class Task(object):
    __slots__ = ('id', 'parent_id', 'children', 'coro', 'cycles', 'state',
                 'cancel_func', 'future', 'timeout', 'exc_info', 'next_value',
                 'next_exc', 'joining', 'terminated', '__weakref__')
    _lastid = 1
    def __init__(self, coro):
        self.id = Task._lastid
        Task._lastid += 1
        self.parent_id = None     # Parent task id
        self.children = set()     # Set of child tasks
        self.coro = coro          # Underlying generator/coroutine
        self.cycles = 0           # Execution cycles completed
        self.state = 'INITIAL'    # Execution state
        self.cancel_func = None   # Cancellation function
        self.future = None        # Pending Future (if any)
        self.timeout = None       # Pending timeout (if any)
        self.exc_info = None      # Exception info (if any on crash)
        self.next_value = None    # Next value to send on execution
        self.next_exc = None      # Next exception to send on execution
        self.joining = None       # Optional set of tasks waiting to join with this one
        self.terminated = False   # Terminated?

    def __repr__(self):
        return 'Task(id=%r, %r, state=%r)' % (self.id, self.coro, self.state)

    def __str__(self):
        return self.coro.__qualname__

    async def join(self, *, timeout=None):
        '''
        Waits for a task to terminate.  Returns the return value (if any)
        or raises a TaskError if the task crashed with an exception.
        '''
        await _join_task(self, timeout)
        if self.exc_info:
            raise TaskError('Task crash') from self.exc_info[1]
        else:
            return self.next_value

    async def cancel(self, *, exc=CancelledError, timeout=None):
        '''
        Cancels a task.  Does not return until the task actually terminates.
        '''
        await _cancel_task(self, exc, timeout)

    async def cancel_children(self, *, exc=CancelledError, timeout=None):
        '''
        Cancels all of the children of this task.
        '''
        for task in list(self.children):
            await _cancel_task(task, exc, timeout=timeout)

# The SignalSet class represents a set of Unix signals being monitored. 
class SignalSet(object):
    def __init__(self, *signos):
        self.signos = signos             # List of all signal numbers being tracked
        self.pending = deque()           # Pending signals received
        self.waiting = None              # Task waiting for the signals (if any)
        self.watching = False            # Are the signals being watched right now?

    
    async def __aenter__(self):
        assert not self.watching
        await _sigwatch(self)
        self.watching = True
        return self

    async def __aexit__(self, *args):
        await _sigunwatch(self)
        self.watching = False

    async def wait(self, *, timeout=None):
        '''
        Wait for a single signal from the signal set to arrive.
        '''
        if not self.watching:
            async with self:
                return await self.wait(timeout=timeout)

        while True:
            if self.pending:
                return self.pending.popleft()
            await _sigwait(self, timeout)

    @contextmanager
    def ignore(self):
        '''
        Context manager. Temporarily ignores all signals in the signal set. 
        '''
        try:
            orig_signals = [ (signo, signal.signal(signo, signal.SIG_IGN)) for signo in self.signos ]
            yield
        finally:
            for signo, handler in orig_signals:
                signal.signal(signo, handler)

# Underlying kernel that drives everything

class Kernel(object):
    __slots__ = ('_selector', '_ready', '_tasks', '_current', '_sleeping',
                 '_signals', '_default_signals', '_njobs', '_running',
                 '_notify_sock', '_wait_sock')

    def __init__(self, selector=None, with_monitor=False):
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

        if with_monitor and sys.stdin.isatty():
            from .monitor import monitor
            self.add_task(monitor(), daemon=True)

    def __del__(self):
        self._notify_sock.close()
        self._wait_sock.close()

    # Force the kernel to wake.  Used on non-I/O events such as completion of futures
    def _wake(self, task=None, value=None, exc=None):
        if task:
            self._reschedule_task(task, value, exc)
        self._notify_sock.send(b'\x00')

    # Internal task that monitors the loopback socket--allowing the kernel to
    # awake for non-I/O events.  Also processes incoming signals.
    async def _init_task(self):
        while True:
            await _read_wait(self._wait_sock)
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
        return self._new_task(coro, daemon)

    # Internal task management functions. 
    def _new_task(self, coro, daemon=False):
        # Create a new task in the kernel.  If daemon is True, the task is
        # created with no parent task.

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
        # Reschedule a task, putting it back on the ready queue so that it can run.
        # value and exc specify a value or exception to send into the underlying 
        # coroutine when it is rescheduled.

        assert task.id in self._tasks, 'Task %r not in the task table' % task
        self._ready.append(task)
        task.next_value = value
        task.next_exc = exc
        task.state = 'READY'
        task.timeout = task.cancel_func = task.future = None

    def _cancel_task(self, task, exc=CancelledError):
        # Cancel a task. This causes a CancelledError exception to raise in the
        # underlying coroutine.  The coroutine can elect to catch the exception
        # and continue to run to perform cleanup actions.  However, it would 
        # normally terminate shortly afterwards.   This method is also used to 
        # raise timeouts.

        assert task != self._current, "A task can't cancel itself (%r, %r)" % (task, self._current)
        
        if task.terminated:
            return True

        if not task.cancel_func:
            # If there is no cancellation function set. It means that
            # the task finished whatever it might have been working on
            # and it's sitting in the ready queue ready to run.  This
            # presents a rather tricky corner case of
            # cancellation. First of all, it means that the task
            # successfully completed whatever it was waiting to do,
            # but it has not communicated the result back.  This could
            # be something critical like acquiring a lock.  Because of
            # that, can't just arbitrarily nuke the task.  Instead, we
            # have to let it be rescheduled and properly process the result of the
            # successfully completed operation.   The return of False
            # here means that cancellation failed and that it should be retried.
            return False

        # Detach the task from where it might be waiting at this moment
        task.cancel_func()
        
        assert task not in self._ready
        # Reschedule it with a pending exception
        self._reschedule_task(task, exc=exc())
        return True

    def _cleanup_task(self, task, value=None, exc=None):
        # Cleanup task.  This is called after the underlying coroutine has
        # terminated.  value and exc give the return value or exception of
        # the coroutine.  This wakes any tasks waiting to join and removes
        # the terminated task from its parent/children.

        task.next_value = value
        if task.parent_id:
            self._njobs -=1

        if task.joining:
            for wtask in task.joining:
                self._reschedule_task(wtask, value=value, exc=exc)
            task.joining = None
        task.terminated = True
        del self._tasks[task.id]

        # Remove the task from the parent child list
        parent = self._tasks.get(task.parent_id)
        if parent:
            parent.children.remove(task)

        # Reassign all remaining children to the parent task
        init = self._tasks[1]
        init.children.update(task.children)
        for ctask in task.children:
            ctask.parent_id = 1
        task.children = set()

    def _set_timeout(self, task, seconds, sleep_type='timeout'):
        task.timeout = time.monotonic() + seconds
        item = (task.timeout, task, sleep_type)
        heapq.heappush(self._sleeping, item)

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

        # Process sleeping tasks (if any)
        if self._sleeping:
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
                        self._cancel_task(task, exc=TimeoutError)

    # Kernel central loop
    def run(self, coro=None, *, pdb=False, log_errors=True):
        '''
        Run the kernel until no more non-daemonic tasks remain.
        '''

        # If a coroutine was given, add it as the first task
        if coro:
            self.add_task(coro)

        self._running = True

        while self._njobs > 0 and self._running:
            self._current = None

            # Poll for I/O as long as there is nothing to run
            while not self._ready:
                self._poll_for_io()

            # Run everything that's ready
            while self._ready:
                current = self._current = self._ready.popleft()
                assert current.id in self._tasks
                try:
                    current.state = 'RUNNING'
                    current.cycles += 1
                    if current.next_exc is None:
                        op, *args = current.coro.send(current.next_value)
                    else:
                        op, *args = current.coro.throw(current.next_exc)

                    # Execute the trap
                    getattr(self, op)(current, *args)

                except (StopIteration, CancelledError) as e:
                    self._cleanup_task(current, value = e.value if isinstance(e, StopIteration) else None)

                except Exception as e:
                    current.exc_info = sys.exc_info()
                    current.state = 'CRASHED'
                    exc = TaskError('Task Crashed')
                    exc.__cause__ = e
                    self._cleanup_task(current, exc=exc)
                    if log_errors:
                        log.error('Curio: Task Crash: %s' % current, exc_info=True)
                    if pdb:
                        import pdb as _pdb
                        _pdb.post_mortem(current.exc_info[2])

                except SystemExit:
                    self._cleanup_task(current)
                    raise


        self._current = None

    def stop(self):
        '''
        Stop the kernel loop.
        '''
        self._running = False

    def shutdown(self):
        '''
        Cleanly shut down the kernel.  All remaining tasks are cancelled.  Using the
        function is highly recommended prior to terminating any program.
        '''
        self._current = None
        for task in sorted(self._tasks.values(), key=lambda t: t.id, reverse=True):
            if task.id == 1:
                continue
            # If the task is daemonic, force it to non-daemon status and cancel it
            if not task.parent_id:
                self._njobs += 1
                task.parent_id = -1

            assert self._cancel_task(task)

        self.run()

    # Traps.  These implement the low-level functionality that is triggered by coroutines.
    # You shouldn't invoke these directly. Instead, coroutines use a statement such as
    #   
    #   yield ('_trap_io', sock, EVENT_READ, 'READ_WAIT', timeout)
    #
    # To execute these methods.

    def _trap_io(self, current, fileobj, event, state, timeout):
        self._selector.register(fileobj, event, current)
        current.state = state
        current.cancel_func = lambda: self._selector.unregister(fileobj)
        if timeout:
            self._set_timeout(current, timeout)

    def _trap_future_wait(self, current, future, timeout=None):
        current.state = 'FUTURE_WAIT'
        current.cancel_func = lambda: future.cancel()
        current.future = future
        future.add_done_callback(lambda fut, task=current: self._wake(task) if task.future == fut else None)
        if timeout:
            self._set_timeout(current, timeout)

    def _trap_new_task(self, current, coro, daemon=False):
        task = self._new_task(coro, daemon)
        self._reschedule_task(current, value=task)

    def _trap_reschedule_tasks(self, current, queue, n=1, value=None, exc=None):
        while n > 0:
            self._reschedule_task(queue.popleft(), value=value, exc=exc)
            n -= 1
        self._reschedule_task(current)

    def _trap_join_task(self, current, task, timeout=None):
        if task.terminated:
            self._reschedule_task(current)
        else:
            if task.joining is None:
                task.joining = kqueue()
            self._trap_wait_queue(current, task.joining, 'TASK_JOIN', timeout)

    def _trap_cancel_task(self, current, task, exc, timeout=None):
        if self._cancel_task(task, exc):
            self._trap_join_task(current, task, timeout)
        else:
            # Fail with a _CancelRetry exception to indicate that the cancel
            # request should be attempted again.  This happens in the case
            # that a cancellation request is issued against a task that
            # ready to run in the ready queue.
            self._reschedule_task(current, exc=_CancelRetry())

    def _trap_wait_queue(self, current, queue, state, timeout=None):
        queue.append(current)
        current.state = state
        current.cancel_func = lambda: queue.remove(current)
        if timeout:
            self._set_timeout(current, timeout)
        
    def _trap_sleep(self, current, seconds):
        if seconds > 0:
            self._set_timeout(current, seconds, 'sleep')
            current.state = 'TIME_SLEEP'
            current.cancel_func = lambda: None
        else:
            self._reschedule_task(current)

    def _trap_sigwatch(self, current, sigset):
        # Initialize the signal handling part of the kernel if not done already
        # Note: This only works if running in the main thread
        if self._signals is None:
            self._signals = defaultdict(list)
            signal.set_wakeup_fd(self._notify_sock.fileno())     
            
        for signo in sigset.signos:
            if not self._signals[signo]:
                self._default_signals[signo] = signal.signal(signo, lambda signo, frame:None)
            self._signals[signo].append(sigset)

        self._reschedule_task(current)
        
    def _trap_sigunwatch(self, current, sigset):
        for signo in sigset.signos:
            if sigset in self._signals[signo]:
                self._signals[signo].remove(sigset)

            # If there are no active watchers for a signal, revert it back to default behavior
            if not self._signals[signo]:
                signal.signal(signo, self._default_signals[signo])
                del self._signals[signo]
        self._reschedule_task(current)

    def _trap_sigwait(self, current, sigset, timeout):
        sigset.waiting = current
        current.state = 'SIGNAL_WAIT'
        current.cancel_func = lambda: setattr(sigset, 'waiting', None)
        if timeout:
            self._set_timeout(current, timeout)

    def _trap_kernel(self, current):
        self._reschedule_task(current, value=self)

# Coroutines corresponding to the kernel traps.  These functions provide the bridge from
# tasks to the underlying kernel. This is the only place with the explicit @coroutine
# decorator needs to be used.  All other code in curio and in user-tasks should use
# async/await instead.   Direct use by users is allowed, but if you're working with
# these traps directly, there is probably a higher level interface that simplifies
# the problem you're trying to solve (e.g., Socket, File, objects, etc.)

@coroutine
def _read_wait(fileobj, timeout=None):
    '''
    Wait until reading can be performed.
    '''
    yield ('_trap_io', fileobj, EVENT_READ, 'READ_WAIT', timeout)

@coroutine
def _write_wait(fileobj, timeout=None):
    '''
    Wait until writing can be performed.
    '''
    yield ('_trap_io', fileobj, EVENT_WRITE, 'WRITE_WAIT', timeout)

@coroutine
def _future_wait(future, timeout=None):
    '''
    Wait for the future of a Future to be computed.
    '''
    yield ('_trap_future_wait', future, timeout)

@coroutine
def _sleep(seconds):
    '''
    Sleep for a given number of seconds
    '''
    yield ('_trap_sleep', seconds)

@coroutine
def _new_task(coro, daemon):
    '''
    Create a new task
    '''
    return (yield '_trap_new_task', coro, daemon)

@coroutine
def _cancel_task(task, exc=CancelledError, timeout=None):
    '''
    Cancel a task.  Causes a CancelledError exception to raise in the task.
    '''
    while True:
        try:
            yield ('_trap_cancel_task', task, exc, timeout)
            return
        except _CancelRetry:
            pass

@coroutine
def _join_task(task, timeout=None):
    '''
    Wait for a task to terminate.
    '''
    yield ('_trap_join_task', task, timeout)

@coroutine
def _wait_on_queue(queue, state, timeout=None):
    '''
    Put the task to sleep on a kernel queue.
    '''
    yield ('_trap_wait_queue', queue, state, timeout)

@coroutine
def _reschedule_tasks(queue, n=1, value=None, exc=None):
    '''
    Reschedule one or more tasks waiting on a kernel queue.
    '''
    yield ('_trap_reschedule_tasks', queue, n, value, exc)

@coroutine
def _sigwatch(sigset):
    '''
    Start monitoring a signal set
    '''
    yield ('_trap_sigwatch', sigset)

@coroutine
def _sigunwatch(sigset):
    '''
    Stop watching a signal set
    '''
    yield ('_trap_sigunwatch', sigset)

@coroutine
def _sigwait(sigset, timeout=None):
    '''
    Wait for a signal to arrive.
    '''
    yield ('_trap_sigwait', sigset, timeout)

@coroutine
def _kernel_reference():
    '''
    Get a reference to the running kernel
    '''
    result = yield ('_trap_kernel',)
    return result

# Public-facing syscalls.  These coroutines wrap a low-level coroutine
# with an extra layer involving an async/await function.  The main
# reason for doing this is that the user will get proper warning
# messages if they forget to use the required 'await' keyword.

async def sleep(seconds):
    '''
    Sleep for a specified number of seconds.
    '''
    await _sleep(seconds)

async def new_task(coro, *, daemon=False):
    '''
    Create a new task.
    '''
    return await _new_task(coro, daemon)

_default_kernel = None
def get_kernel():
    '''
    Return the default kernel.
    '''
    global _default_kernel
    if _default_kernel is None:
        _default_kernel = Kernel()
    return _default_kernel

__all__ = [ 'Kernel', 'get_kernel', 'sleep', 'new_task', 'SignalSet', 'TaskError', 'CancelledError' ]
            
        
