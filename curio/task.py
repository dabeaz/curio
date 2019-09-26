# curio/task.py
#
# Task class and task related functions.

# -- Standard library

import logging
from collections import deque
import linecache
import traceback
import os.path
from functools import partial

log = logging.getLogger(__name__)

# -- Curio

from .errors import *
from .traps import *
from .sched import SchedBarrier
from . import meta

__all__ = [
    'Task', 'TaskGroup', 'sleep', 'wake_at', 'current_task',
    'spawn', 'timeout_after', 'timeout_at',
    'ignore_after', 'ignore_at', 'clock', 'schedule',
    'disable_cancellation', 'check_cancellation', 'set_cancellation'
]

# Internal functions used for debugging/diagnostics
def _get_stack(coro):
    '''
    Extracts a list of stack frames from a chain of generator/coroutine calls
    '''
    frames = []
    while coro:
        if hasattr(coro, 'cr_frame'):
            f = coro.cr_frame
            coro = coro.cr_await
        elif hasattr(coro, 'ag_frame'):
            f = coro.ag_frame
            coro = coro.ag_await
        elif hasattr(coro, 'gi_frame'):
            f = coro.gi_frame
            coro = coro.gi_yieldfrom
        else:
            # Note: Can't proceed further.  Need the ags_gen or agt_gen attribute
            # from an asynchronous generator.  See https://bugs.python.org/issue32810
            f = None
            coro = None

        if f is not None:
            frames.append(f)
    return frames

# Create a stack traceback for a task
def _format_stack(task, complete=False):
    '''
    Formats a traceback from a stack of coroutines/generators
    '''
    dirname = os.path.dirname(__file__)
    extracted_list = []
    checked = set()
    for f in _get_stack(task.coro):
        lineno = f.f_lineno
        co = f.f_code
        filename = co.co_filename
        name = co.co_name
        if not complete and os.path.dirname(filename) == dirname:
            continue
        if filename not in checked:
            checked.add(filename)
            linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        extracted_list.append((filename, lineno, name, line))
    if not extracted_list:
        resp = f'No stack for {task!r}'
    else:
        resp = f'Stack for {task!r} (most recent call last):\n'
        resp += ''.join(traceback.format_list(extracted_list))
    return resp

# Return the (filename, lineno) where a task is currently executing
def _where(task):
    dirname = os.path.dirname(__file__)
    for f in _get_stack(task.coro):
        lineno = f.f_lineno
        co = f.f_code
        filename = co.co_filename
        name = co.co_name
        if os.path.dirname(filename) == dirname:
            continue
        return filename, lineno
    return None, None

class Task(object):
    '''
    The Task class wraps a coroutine and provides some additional attributes
    related to execution state and debugging.  Tasks are not normally 
    instantiated directly. Instead, use spawn().
    '''
    _lastid = 1
    def __init__(self, coro):
        # Informational attributes about the task itself
        self.id = Task._lastid
        Task._lastid += 1
        self.parentid = None          # Parent task id (if any)
        self.coro = coro              # Underlying generator/coroutine
        self.name = getattr(coro, '__qualname__', str(coro))
        self.daemon = False           # Daemonic flag

        # Attributes updated during execution (safe to inspect)
        self.cycles = 0               # Execution cycles completed
        self.state = 'INITIAL'        # Execution state
        self.cancel_func = None       # Cancellation function
        self.future = None            # Pending Future (if any)
        self.sleep = None             # Pending sleep (if any)
        self.timeout = None           # Pending timeout (if any)
        self.joining = SchedBarrier() # Set of tasks waiting to join with this one
        self.cancelled = None         # Has the task been cancelled?
        self.terminated = False       # Has the task actually Terminated?
        self.cancel_pending = None    # Deferred cancellation exception pending (if any)
        self.allow_cancel = True      # Can cancellation exceptions be delivered?
        self.suspend_func = None      # Optional suspension callback (called when task suspends)
        self.taskgroup = None         # Containing task group (if any)
        self.joined = False           # Set if the task has actually been joined or result collected

        # Final result of coroutine execution (use properties to access)
        self._final_result = None     # Final result of execution
        self._final_exc = None        # Final exception of execution

        # Actual execution is wrapped by a supporting coroutine
        self._run_coro = self._task_runner(self.coro)

        # Result of the last trap
        self._trap_result = None 

        # Last I/O operation performed
        self._last_io = None          

        # Bound coroutine methods
        self._send = self._run_coro.send   
        self._throw = self._run_coro.throw
        
        # Timeout deadline stack
        self._deadlines = []

    def __repr__(self):
        return f'Task(id={self.id}, name={self.name!r}, state={self.state!r})'

    def __str__(self):
        filename, lineno = _where(self)
        if filename:
            return f'{self!r} at {filename}:{lineno}'
        else:
            return repr(self)

    def __del__(self):
        self.coro.close()
        if not self.joined and not self.cancelled and not self.daemon:
            if not self.daemon and not self.exception:
                log.warning('%r never joined', self)

    async def _task_runner(self, coro):
        try:
            return await coro
        finally:
            if self.taskgroup:
                await self.taskgroup._task_done(self)
                self.joined = True

    async def join(self):
        '''
        Wait for a task to terminate.  Returns the return value (if any)
        or raises a TaskError if the task crashed with an exception.
        '''
        await self.wait()
        if self.taskgroup:
            self.taskgroup._task_discard(self)
        self.joined = True
        if self.exception:
            raise TaskError('Task crash') from self.exception
        else:
            return self.result

    async def wait(self):
        '''
        Wait for a task to terminate. Does not return any value.
        '''
        if not self.terminated:
            await self.joining.suspend('TASK_JOIN')
        
    @property
    def result(self):
        '''
        Return the result of a task. The task must be terminated already.
        '''
        if not self.terminated:
            raise RuntimeError('Task not terminated')
        self.joined = True
        if self._final_exc:
            raise self._final_exc
        else:
            return self._final_result

    @result.setter
    def result(self, value):
        self._final_result = value
        self._final_exc = None

    @property
    def exception(self):
        '''
        Return any pending exception of a task or None.
        '''
        if not self.terminated:
            raise RuntimeError('Task not terminated')
        return self._final_exc

    @exception.setter
    def exception(self, value):
        self._final_result = None
        self._final_exc = value

    async def cancel(self, *, exc=TaskCancelled, blocking=True):
        '''
        Cancel a task by raising a CancelledError exception.

        If blocking=False, schedules the cancellation and returns
        synchronously.

        If blocking=True (the default), then does not
        return until the task actually terminates.

        Returns True if the task was actually cancelled. False is returned if
        the task was already completed.
        '''
        if self.terminated:
            self.joined = True
            return False
        await _cancel_task(self, exc=exc)
        if blocking:
            await self.wait()

        return True

    def traceback(self):    # pragma: no cover
        '''
        Return a formatted traceback showing where the task is currently executing.
        '''
        return _format_stack(self)

    def where(self):    # pragma: no cover
        '''
        Return a tuple (filename, lineno) where task is executing
        '''
        return _where(self)

    def _switch(self, coro):
        '''
        Switch the underlying coroutine being executed by the task.
        For wizards only--this is used to coordinate some of Curio's
        coroutine-thread interaction.
        '''
        orig_coro = self._run_coro
        self._run_coro = coro
        self._send = coro.send
        self._throw = coro.throw
        return orig_coro

class TaskGroup(object):
    '''
    A TaskGroup represents a collection of managed tasks.  A group can
    be used to ensure that all tasks terminate together, to monitor
    tasks as they finish, and to manage error handling.  

    A TaskGroup can be created from existing tasks.  For example:

        t1 = await spawn(coro1)
        t2 = await spawn(coro2)
        t3 = await spawn(coro3)

        async with TaskGroup([t1,t2,t3]) as g:
            ...

    Alternatively, tasks can be spawned into a task group.

        async with TaskGroup() as g:
            await g.spawn(coro1)
            await g.spawn(coro2)
            await g.spawn(coro3)

    When used as a context manager, a TaskGroup will wait until
    all contained tasks successfully exit before moving on.

    If cancelled, all tasks within a TaskGroup are also cancelled.

    If any task exits with an error, all remaining tasks are cancelled
    and a TaskGroupError exception is raised.  This exception contains
    more specific information about what happened.  The .errors
    attribute is a set of all exception types. It may contain multiple
    values if if multiple failures. The .failed attribute is a list of
    all tasks that failed.  Here's what exception handling might look
    like:

        try:
            async with TaskGroup() as g:
                ...
        except TaskGroupError as e:
            for task in e.failed:
                # Look at failed task
                print('FAILED', task, task.exception)

    If tasks are computing results you want to use, you can
    write this:

        async with TaskGroup() as g:
            t1 = await g.spawn(coro1)
            t2 = await g.spawn(coro2)
            t3 = await g.spawn(coro3)

        # Get results---tasks are guaranteed to be done
        result1 = t1.result
        result2 = t2.result
        result3 = t3.result

    To obtain tasks in the order that they complete, use iteration:
  
        async with TaskGroup() as g:
            await g.spawn(coro1)
            await g.spawn(coro2)
            await g.spawn(coro3)

            async for done in g:
                print('Task done', done, done.result)

    The cancel_remaining() method can be used to cancel all
    remaining tasks early.  The add_task() method can be
    used to add an already existing task to a group.  Calling
    .join() on a task removes it from a group. For example:

         async with TaskGroup() as g:
             t1 = await g.spawn(coro1)
             ...
             await t1.join()        # removes t1 from the group

    Normally, a task group is used as a context manager.  This 
    doesn't have to be the case.  You could write code like this:

        g = TaskGroup()
        try:
            await g.spawn(coro1)
            await g.spawn(coro2)
            ...
        finally:
            await g.join()
 
    This might be more useful for more persistent or long-lived 
    task groups.
    '''
    def __init__(self, tasks=(), *, wait=all):
        self._running = set()
        self._finished = deque()
        self._closed = False
        self._wait = wait
        self.completed = None    # First completed task

        for task in tasks:
            assert not task.taskgroup
            task.taskgroup = self
            if task.terminated:
                self._finished.append(task)
            else:
                self._running.add(task)

        self._sema = sync.Semaphore(len(self._finished))

    # Triggered on task completion. 
    async def _task_done(self, task):
        self._running.discard(task)
        self._finished.append(task)
        await self._sema.release()

    # Discards a task from the TaskGroup.  Called implicitly if
    # if a task is joined while under supervision.
    def _task_discard(self, task):
        try:
            self._finished.remove(task)
        except ValueError:
            pass
        task.taskgroup = None
        if task == self.completed:
            self.completed = None

    async def add_task(self, task):
        '''
        Add an already existing task to the group.
        '''
        if task.taskgroup:
            raise RuntimeError('Task is already part of a group')

        if self._closed:
            raise RuntimeError('Task group is closed')
        task.taskgroup = self
        if task.terminated:
            await self._task_done(task)
        else:
            self._running.add(task)

    async def spawn(self, coro, *args):
        '''
        Spawn a new task into the task group.
        '''
        if self._closed:
            raise RuntimeError('Task group is closed')

        task = await spawn(coro, *args)
        await self.add_task(task)
        return task

    async def next_done(self):
        '''
        Wait for the next task to finish.
        '''
        while not self._finished and self._running:
            await self._sema.acquire()

        if self._finished:
            task = self._finished.popleft()
            await task.wait()
            task.taskgroup = None
        else:
            task = None

        return task

    async def next_result(self):
        '''
        Return the result of the next task that finishes. Note: if task
        terminated via exception, that exception is raised here.
        '''
        task = await self.next_done()
        if task:
            return task.result
        else:
            raise RuntimeError('No task available')

    async def cancel_remaining(self):
        '''
        Cancel all remaining running tasks. Tasks are removed
        from the task group when cancelled.
        '''
        self._closed = True
        running = list(self._running)
        for task in running:
            await task.cancel(blocking=False)
        for task in running:
            await task.wait()
            self._task_discard(task)

            
    async def join(self):
        '''
        Wait for tasks in a task group to terminate according to the
        wait policy set for the group.  If the join() operation itself
        is cancelled, all remaining tasks are cancelled and the
        cancellation exception is reraised.
        '''

        # If there are any currently finished tasks, find the ones in error
        for task in self._finished:
            await task.wait()
            if self.completed is None and not task.exception:
                if self._wait is object:
                    self.completed = task if (task.result is not None) else None
                else:
                    self.completed = task
        
        # Find all currently finished tasks to collect the ones in error
        exceptional = [ task for task in self._finished if task.exception ]

        # If there are any tasks in error, or the wait policy dictates
        # cancellation of remaining tasks, cancel them
        if exceptional or (self._wait is None) or (self._wait in (any, object) and self.completed):
            while self._running:
                task = self._running.pop()
                await task.cancel()

        self._finished.clear()

        # Spin while things are still running and collect results
        while self._running:
            try:
                await self._sema.acquire()
            except CancelledError:
                # If we got cancelled ourselves, we cancel everything remaining.
                # Must bail out by re-raising the CancelledError exception (oh well)
                while self._running:
                    task = self._running.pop()
                    await task.cancel()
                    task.taskgroup = None
                raise

            # If we're here and nothing finished, it means that some task
            # called its join() method.  We're not concerned about that task anymore.  Carry on.
            if not self._finished:
                continue

            # Collect any finished tasks
            while self._finished:
                task = self._finished.popleft()
                await task.wait()
                task.taskgroup = None
                cancel_remaining = False

                # Check if we're still waiting for the result of the first task
                if self.completed is None and not task.exception:
                    if self._wait is object:
                        self.completed = task if (task.result is not None) else None
                    else:
                        self.completed = task

                # If the task is in error state and nothing else is. Cancel everything else
                if task.exception:
                    if not exceptional:
                        cancel_remaining = True
                    exceptional.append(task)
                elif (self._wait in (any, object)) and task == self.completed:
                    cancel_remaining = True

                if cancel_remaining:
                    while self._running:
                        ctask = self._running.pop()
                        await ctask.cancel()

        self._closed = True

        # We remove any task that was directly cancelled
        exceptional = [task for task in exceptional if not isinstance(task.exception, TaskCancelled) ]

        # If there are exceptions on any task, we raise a TaskGroupError
        if exceptional:
            raise TaskGroupError(exceptional)

    async def __aenter__(self):
        return self

    async def __aexit__(self, ty, val, tb):
        if ty:
            await self.cancel_remaining()
        else:
            await self.join()

    def __aiter__(self):
        return self

    async def __anext__(self):
        next = await self.next_done()
        if next is None:
            raise StopAsyncIteration
        return next

    # -- Support for use in async threads
    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

    def __iter__(self):
        return thread.AWAIT(self.__aiter__())

    def __next__(self):
        try:
            return thread.AWAIT(self.__anext__())
        except StopAsyncIteration:
            raise StopIteration

# ----------------------------------------------------------------------
# Public-facing task-related functions.  Some of these functions are
# merely a layer over a low-level trap using async/await.  One reason
# for doing this is that the user will get a more proper warning message
# if they use the function without using the required 'await' keyword.
# -----------------------------------------------------------------------

async def current_task():
    '''
    Returns a reference to the current task
    '''
    return await _get_current()

async def sleep(seconds):
    '''
    Sleep for a specified number of seconds.  Sleeping for 0 seconds
    makes a task immediately switch to the next ready task (if any).
    '''
    return await _sleep(seconds, False)

async def wake_at(clock):
    '''
    Sleep until the kernel clock reaches the value of clock.
    Returns the value of the monotonic clock when awakened.
    '''
    return await _sleep(clock, True)

async def clock():
    '''
    Return the current value of the kernel clock. Does not
    preempt the current task.
    '''
    return await _clock()

async def schedule():
    '''
    Preempt the calling task.  Forces the scheduling of other tasks.
    '''
    await sleep(0)

async def spawn(corofunc, *args, daemon=False):
    '''
    Create a new task, running corofunc(*args). Use the daemon=True
    option if the task runs forever as a background task. 
    '''
    coro = meta.instantiate_coroutine(corofunc, *args)
    task = await _spawn(coro)
    task.daemon = daemon
    return task

# Context manager for supervising cancellation masking
class _CancellationManager(object):

    async def __aenter__(self):
        self.task = await current_task()
        self._last_allow_cancel = self.task.allow_cancel
        self.task.allow_cancel = False
        return self

    async def __aexit__(self, ty, val, tb):
        # Restore previous cancellation flag
        self.task.allow_cancel = self._last_allow_cancel

        # If a CancelledError is being raised on exit from a block, it
        # becomes pending in the task if cancellation is not allowed
        # in the outer context.  Curio should never have delivered 
        # such an exception on its own--it could be manually raised however.
        if isinstance(val, CancelledError) and not self.task.allow_cancel:
            self.task.cancel_pending = val
            return True
        else:
            return False

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

def disable_cancellation(coro=None, *args):
    if coro is None:
        return _CancellationManager()
    else:
        coro = meta.instantiate_coroutine(coro, *args)
        async def run():
            async with _CancellationManager():
                return await coro
        return run()

async def check_cancellation(exc_type=None):
    '''
    Check if there is any kind of pending cancellation. If cancellations
    are currently allowed, and there is a pending exception, it raises the
    exception.  If cancellations are not allowed, it returns the pending
    exception object.

    If exc_type is specified, the function checks the type of the specified
    exception against the given type.  If there is a match, the exception
    is returned and cleared.
    '''
    task = await current_task()

    if exc_type and not isinstance(task.cancel_pending, exc_type):
        return None

    if task.cancel_pending and task.allow_cancel:
        try:
            raise task.cancel_pending
        finally:
            task.cancel_pending = None
    else:
        try:
            return task.cancel_pending
        finally:
            if exc_type:
                task.cancel_pending = None

async def set_cancellation(exc):
    '''
    Set a new pending cancellation exception. Returns the old exception.
    '''
    task = await current_task()
    result = task.cancel_pending
    task.cancel_pending = exc
    return result

# Helper class for running timeouts as a context manager

class _TimeoutAfter(object):

    def __init__(self, clock, absolute, ignore=False, timeout_result=None):
        self._clock = clock
        self._absolute = absolute
        self._ignore = ignore
        self._timeout_result = timeout_result
        self.expired = False
        self.result = True

    async def __aenter__(self):
        task = await current_task()
        if not self._absolute and self._clock:
            self._clock += await _clock()
            self._absolute = False
        self._deadlines = task._deadlines
        self._deadlines.append(self._clock)
        self._prior = await _set_timeout(self._clock)
        return self

    async def __aexit__(self, ty, val, tb):
        current_clock = await _unset_timeout(self._prior)

        # Discussion.  If a timeout has occurred, it will either
        # present itself here as a TaskTimeout or TimeoutCancellationError
        # exception.  The value of this exception is set to the current
        # kernel clock which can be compared against our own deadline.
        # What happens next is driven by these rules:
        #
        # 1.  If we are the outer-most context where the timeout
        #     period has expired, then a TaskTimeout is raised.
        #
        # 2.  If the deadline has expired for at least one outer
        #     context, (but not us), a TimeoutCancellationError is
        #     raised.  This means that time has expired elsewhere.
        #     We're being cancelled because of that, but the reason
        #     for the cancellation wasn't due to a timeout on our
        #     part.
        #
        # 3.  If the timeout period has not expired on ANY remaining
        #     timeout context, it means that a timeout has escaped
        #     some inner timeout context where it should have been
        #     caught. This is an operational error.  We raise
        #     UncaughtTimeoutError.

        try:
            if ty in (TaskTimeout, TimeoutCancellationError):
                timeout_clock = val.args[0]
                # Find the outer most deadline that has expired
                for n, deadline in enumerate(self._deadlines):
                    if deadline <= timeout_clock:
                        break
                else:
                    # No remaining context has expired. An operational error
                    raise UncaughtTimeoutError('Uncaught timeout received')

                if n < len(self._deadlines) - 1:
                    if ty is TaskTimeout:
                        raise TimeoutCancellationError(val.args[0]).with_traceback(tb) from None
                    else:
                        return False
                else:
                    # The timeout is us.  Make sure it's a TaskTimeout (unless ignored)
                    self.result = self._timeout_result
                    self.expired = True
                    if self._ignore:
                        return True
                    else:
                        if ty is TimeoutCancellationError:
                            raise TaskTimeout(val.args[0]).with_traceback(tb) from None
                        else:
                            return False
            elif ty is None:
                if current_clock > self._deadlines[-1]:
                    # Further discussion.  In the presence of threads and blocking
                    # operations, it's possible that a timeout has expired, but 
                    # there was simply no opportunity to catch it because there was
                    # no suspension point.  
                    badness = current_clock - self._deadlines[-1]
                    log.warning('%r. Operation completed successfully, '
                                'but it took longer than an enclosing timeout. Badness delta=%r.', 
                                await current_task(), badness)

        finally:
            self._deadlines.pop()

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

async def _timeout_after_func(clock, absolute, coro, args, ignore=False, timeout_result=None):
    coro = meta.instantiate_coroutine(coro, *args)
    async with _TimeoutAfter(clock, absolute, ignore=ignore, timeout_result=timeout_result):
        return await coro

def timeout_at(clock, coro=None, *args):
    '''
    Raise a TaskTimeout exception in the calling task after the clock
    reaches the specified value. Usage is the same as for timeout_after().
    '''
    if coro is None:
        return _TimeoutAfter(clock, True)
    else:
        return _timeout_after_func(clock, True, coro, args)


def timeout_after(seconds, coro=None, *args):
    '''
    Raise a TaskTimeout exception in the calling task after seconds
    have elapsed.  This function may be used in two ways. You can
    apply it to the execution of a single coroutine:

         await timeout_after(seconds, coro(args))

    or you can use it as an asynchronous context manager to apply
    a timeout to a block of statements:

         async with timeout_after(seconds):
             await coro1(args)
             await coro2(args)
             ...
    '''
    if coro is None:
        return _TimeoutAfter(seconds, False)
    else:
        return _timeout_after_func(seconds, False, coro, args)


def ignore_at(clock, coro=None, *args, timeout_result=None):
    '''
    Stop the enclosed task or block of code at an absolute
    clock value. Same usage as ignore_after().
    '''
    if coro is None:
        return _TimeoutAfter(clock, True, ignore=True, timeout_result=timeout_result)
    else:
        return _timeout_after_func(clock, True, coro, args, ignore=True, timeout_result=timeout_result)


def ignore_after(seconds, coro=None, *args, timeout_result=None):
    '''
    Stop the enclosed task or block of code after seconds have
    elapsed.  No exception is raised when time expires. Instead, None
    is returned.  This is often more convenient that catching an
    exception.  You can apply the function to a single coroutine:

        if await ignore_after(5, coro(args)) is None:
            # A timeout occurred
            ...

    Alternatively, you can use this function as an async context
    manager on a block of statements like this:

        async with ignore_after(5) as r:
            await coro1(args)
            await coro2(args)
            ...
        if r.result is None:
            # A timeout occurred

    When used as a context manager, the return manager object has
    a result attribute that will be set to None if the time
    period expires (or True otherwise).

    You can change the return result to a different value using
    the timeout_result keyword argument.
    '''
    if coro is None:
        return _TimeoutAfter(seconds, False, ignore=True, timeout_result=timeout_result)
    else:
        return _timeout_after_func(seconds, False, coro, args, ignore=True, timeout_result=timeout_result)


# Here to avoid circular import issues
from . import queue
from . import thread
from . import sync


