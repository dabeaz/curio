# curio/task.py
#
# Task class and task related functions.

__all__ = ['Task', 'sleep', 'wake_at', 'current_task', 'spawn', 'gather',
           'timeout_after', 'timeout_at', 'ignore_after', 'ignore_at',
           'wait', 'clock', 'enable_cancellation', 'disable_cancellation',
           'check_cancellation', 'set_cancellation', 'schedule', 'aside']

from time import monotonic
from .errors import TaskTimeout, TaskError, TimeoutCancellationError, UncaughtTimeoutError, CancelledError
from .traps import *


class Task(object):
    '''
    The Task class wraps a coroutine and provides some additional attributes
    related to execution state and debugging.
    '''
    __slots__ = (
        'id', 'parentid', 'daemon', 'coro', '_send', '_throw', 'cycles', 'state',
        'cancel_func', 'future', 'sleep', 'timeout', 'exc_info', 'next_value',
        'next_exc', 'joining', 'cancelled', 'terminated', 'cancel_pending',
        '_last_io', '_deadlines', 'task_local_storage', 'allow_cancel', 
        '__weakref__',
    )
    _lastid = 1

    def __init__(self, coro, daemon=False, taskid=None):
        if taskid is None:
            taskid = Task._lastid
            Task._lastid += 1
        self.id = taskid
        self.parentid = None       # Parent task id (if any)
        self.coro = coro           # Underlying generator/coroutine
        self.daemon = daemon       # Daemonic flag
        self.cycles = 0            # Execution cycles completed
        self.state = 'INITIAL'     # Execution state
        self.cancel_func = None    # Cancellation function
        self.future = None         # Pending Future (if any)
        self.sleep = None          # Pending sleep (if any)
        self.timeout = None        # Pending timeout (if any)
        self.exc_info = None       # Exception info (if any on crash)
        self.next_value = None     # Next value to send on execution
        self.next_exc = None       # Next exception to send on execution
        self.joining = None        # Optional set of tasks waiting to join with this one
        self.cancelled = None      # Has the task been cancelled?
        self.terminated = False    # Has the task actually Terminated?
        self.cancel_pending = None # Deferred cancellation exception pending (if any)
        self.allow_cancel = True   # Can cancellation exceptions be delivered?

        self.task_local_storage = {}  # Task local storage
        self._last_io = None       # Last I/O operation performed
        self._send = coro.send     # Bound coroutine methods
        self._throw = coro.throw
        self._deadlines = []       # Timeout deadlines

    def __repr__(self):
        return 'Task(id=%r, %r, state=%r)' % (self.id, self.coro, self.state)

    def __str__(self):
        return getattr(self.coro, '__qualname__', str(self.coro))

    def __del__(self):
        self.coro.close()

    async def join(self):
        '''
        Wait for a task to terminate.  Returns the return value (if any)
        or raises a TaskError if the task crashed with an exception.
        '''
        await _join_task(self)
        if self.exc_info:
            raise TaskError('Task crash') from self.exc_info[1]
        else:
            return self.next_value

    async def cancel(self, blocking=True):
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
            if blocking:
                await _sleep(0, False)
            return False
        await _cancel_task(self)
        if blocking:
            await _join_task(self)
        return True

    def pdb(self):
        '''
        Run a pdb post-mortem on any pending exception information
        '''
        import pdb
        if self.exc_info:
            pdb.post_mortem(self.exc_info[2])

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

async def spawn(coro, *, daemon=False, allow_cancel=True):
    '''
    Create a new task.  Use the daemon=True option if the task runs
    forever as a background task.  If allow_cancel=False is
    specified, the task disables the delivery of cancellation related
    exceptions (including timeouts).
    '''
    task = await _spawn(coro, daemon)
    task.allow_cancel = allow_cancel
    return task

async def gather(tasks, *, return_exceptions=False):
    '''
    Wait for and gather results from a collection of tasks.
    '''
    results = []
    for task in tasks:
        try:
            results.append(await task.join())
        except Exception as e:
            if return_exceptions:
                results.append(e)
            else:
                raise
    return results


class wait(object):
    '''
    Wait for one or more tasks to complete, possibly with cancellation.
    Suppose you have created some tasks:

         task1 = await spawn(coro())
         task2 = await spawn(coro())
         task3 = await spawn(coro())

    wait() allows you to obtain tasks as they complete.  For example:

         w = wait([task1, task2, task3])

    Obtain the next completed task:

         task = await w.next_done()
         result = await task.join()

    Get all of the completed tasks in completion order:

         async for task in w:
             result = await task.join()

    All unfinished tasks will be cancelled if you use the result of wait()
    as a context manager. For example:

         async with wait([task1, task2, task3]) as w:
             task = await w.next_done()
             result = await task.join()
         # All remaining tasks cancelled

    All remaining tasks can also be cancelled using await w.cancel_remaining().

    wait() only returns the complete Task instances, not the results of those
    tasks.  To get the results, you still call task.join() as before.  wait()
    ensures that when you call join(), the result is immediately available.
    '''

    def __init__(self, tasks):
        self._initial_tasks = tasks
        self._queue = queue.Queue()
        self._tasks = None

    async def __aenter__(self):
        await self._init()
        return self

    async def __aexit__(self, ty, val, tb):
        await self.cancel_remaining()

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

    def __aiter__(self):
        return self

    async def __anext__(self):
        next = await self.next_done()
        if next is None:
            raise StopAsyncIteration
        return next

    def __iter__(self):
        return thread.AWAIT(self.__aiter__())

    def __next__(self):
        try:
            return thread.AWAIT(self.__anext__())
        except StopAsyncIteration:
            raise StopIteration

    async def _init(self):
        async def wait_runner(task):
            try:
                result = await task.join()
            except Exception:
                pass
            await self._queue.put(task)

        self._tasks = []
        for task in self._initial_tasks:
            await spawn(wait_runner(task))
            self._tasks.append(task)

    async def next_done(self):
        if self._tasks is None:
            await self._init()
        if not self._tasks:
            return None

        task = await self._queue.get()
        self._tasks.remove(task)
        return task

    async def cancel_remaining(self):
        if self._tasks is None:
            await self._init()

        for task in self._tasks:
            await task.cancel()

        self._tasks = []

# Utility functions for controlling cancellation
class _CancellationManager(object):

    def __init__(self, allow_cancel):
        self.allow_cancel = allow_cancel
        self.cancel_pending = None

    async def __aenter__(self):
        self.task = await current_task()
        if self.task.allow_cancel and self.allow_cancel:
            raise RuntimeError('enable_cancellation() may not be used in a context where cancellation is already allowed')
        self._last_allow_cancel = self.task.allow_cancel
        self.task.allow_cancel = self.allow_cancel
        return self

    async def __aexit__(self, ty, val, tb):
        self.task.allow_cancel = self._last_allow_cancel

        # If a CancelledError is raised on exit from a block, the
        # following rules are in play:
        #
        # 1. If the block did not allow cancellation in the first place,
        #    a RuntimeError occurs.  It illegal for CancelledError to
        #    be raised in any form when cancellation is disabled.
        #
        # 2. If cancellation is not allowed in the outer block,
        #    the CancelledError is transformed back into a pending
        #    exception.  The outer block can certainly check for
        #    this if it wants, but it can also just defer the 
        #    cancellation to a point where cancellation is allowed again.
        #
        if isinstance(val, CancelledError):
            if not self.allow_cancel:
                raise RuntimeError('%s must not be raised in a disable_cancellation block' % 
                                   ty.__name__)
            if not self.task.allow_cancel:
                self.cancel_pending = self.task.cancel_pending = val
                return True
        else:
            self.cancel_pending = self.task.cancel_pending
            return False

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))


def enable_cancellation(coro=None):
    if coro is None:
        return _CancellationManager(True)
    else:
        async def run():
            async with _CancellationManager(True):
                return await coro
        return run()

def disable_cancellation(coro=None):
    if coro is None:
        return _CancellationManager(False)
    else:
        async def run():
            async with _CancellationManager(False):
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
        await _unset_timeout(self._prior)

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
                    if self._ignore:
                        return True
                    else:
                        if ty is TimeoutCancellationError:
                            raise TaskTimeout(val.args[0]).with_traceback(tb) from None
                        else:
                            return False
        finally:
            self._deadlines.pop()

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

async def _timeout_after_func(clock, absolute, coro, ignore=False, timeout_result=None):
    task = await current_task()
    if not absolute and clock:
        clock += await _clock()
    prior = await _set_timeout(clock)
    task._deadlines.append(clock)
    try:
        return await coro
    except (TaskTimeout, TimeoutCancellationError) as e:
        timeout_clock = e.args[0]
        for n, deadline in enumerate(task._deadlines):
            if deadline <= timeout_clock:
                break
        else:
            raise UncaughtTimeoutError('Uncaught timeout received')

        if n < len(task._deadlines) - 1:
            if isinstance(e, TaskTimeout):
                raise TimeoutCancellationError(e.args[0]).with_traceback(e.__traceback__) from None
            else:
                raise

        # We're getting the timeout
        if not ignore:
            if isinstance(e, TimeoutCancellationError):
                raise TaskTimeout(e.args[0]).with_traceback(e.__traceback__) from None
            else:
                raise
        return timeout_result

    finally:
        task._deadlines.pop()
        await _unset_timeout(prior)


def timeout_at(clock, coro=None):
    '''
    Raise a TaskTimeout exception in the calling task after the clock
    reaches the specified value. Usage is the same as for timeout_after().
    '''
    if coro is None:
        return _TimeoutAfter(clock, True)
    else:
        return _timeout_after_func(clock, True, coro)


def timeout_after(seconds, coro=None):
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
        return _timeout_after_func(seconds, False, coro)


def ignore_at(clock, coro=None, *, timeout_result=None):
    '''
    Stop the enclosed task or block of code at an absolute
    clock value. Same usage as ignore_after().
    '''
    if coro is None:
        return _TimeoutAfter(clock, True, ignore=True, timeout_result=timeout_result)
    else:
        return _timeout_after_func(clock, True, coro, ignore=True, timeout_result=timeout_result)


def ignore_after(seconds, coro=None, *, timeout_result=None):
    '''
    Stop the enclosed task or block of code after seconds have
    elapsed.  No exception is raised when time expires. Instead, None
    is returned.  This is often more convenient that catching an
    exception.  You can apply the function to a single coroutine:

        if ignore_after(5, coro(args)) is None:
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
        return _timeout_after_func(seconds, False, coro, ignore=True, timeout_result=timeout_result)

from . import queue
from . import thread

# Highly experimental.  Launches a curio task in a completely isolated
# subprocess.  As for the name, well, yeah. "async", "await", "abide",
# "aside", etc. Work with me here!

async def aside(corofunc, *args, **kwargs):
    '''
    Spawn a new task, but run it aside in a newly created process.
    Returns a Task instance corresponding to a small supervisor task
    in the caller.  The return value of task.join() is the exit code of
    the subprocess.  Cancelling the task causes a SIGTERM signal to be
    sent to the child.  This will be raised as a CancelledError in 
    the child (which is given an opportunity to clean up if it wants).

    The newly created task shares no state with the caller. It is not
    a process fork.  It is launched in a completely fresh Python
    interpreter.

    This function also establishes no I/O communication mechanism to
    the newly created task.  It's not a pipe.  If you need
    communication, use sockets or create a Channel object.

    Arguments to the called coroutine are pickled and transmitted via
    a command line arguments.  You should probably only pass small
    data structures or metadata.  If you need to pass bulk data,
    set up an I/O channel separately.  
    '''
    import base64
    import pickle
    import sys
    from . import subprocess

    async def _aside_supervisor():
        p = subprocess.Popen([sys.executable, '-m', 'curio.side', filename,
                              base64.b64encode(pickle.dumps((corofunc, args, kwargs)))])
        try:
            return await p.wait()
        except CancelledError as e:
            p.terminate()
            await p.wait()
            raise

    if corofunc.__module__ == '__main__':
        filename = sys.modules['__main__'].__file__
    else:
        filename = ''

    return await spawn(_aside_supervisor())
