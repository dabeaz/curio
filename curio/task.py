# curio/task.py
#
# Task class and task related functions.

__all__ = [ 'Task', 'sleep', 'wake_at', 'current_task', 'spawn', 'gather', 
            'timeout_after', 'timeout_at', 'ignore_after', 'ignore_at',
            'wait', 'clock' , 'defer_cancellation', 'allow_cancellation',
            'schedule']

from time import monotonic
from .errors import TaskTimeout, TaskError, TimeoutCancellationError, UncaughtTimeoutError
from .traps import *

class Task(object):
    '''
    The Task class wraps a coroutine and provides some additional attributes
    related to execution state and debugging.
    '''
    __slots__ = (
        'id', 'daemon', 'coro', '_send', '_throw', 'cycles', 'state',
        'cancel_func', 'future', 'sleep', 'timeout', 'exc_info', 'next_value',
        'next_exc', 'joining', 'cancelled', 'terminated', 'cancel_pending',
        'cancel_allowed_stack', '_last_io', '_deadlines',
        'task_local_storage', '__weakref__',
        )
    _lastid = 1

    def __init__(self, coro, daemon=False, taskid=None):
        if taskid is None:
            taskid = Task._lastid
            Task._lastid += 1
        self.id = taskid
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
        self.cancelled = False     # Cancelled?
        self.terminated = False    # Terminated?
        self.cancel_pending = False  # Deferred cancellation pending?
        # Last entry says whether cancellations are currently allowed
        self.cancel_allowed_stack = [True]
        self.task_local_storage = {} # Task local storage
        self._last_io = None       # Last I/O operation performed
        self._send = coro.send     # Bound coroutine methods
        self._throw = coro.throw
        self._deadlines = []       # Timeout deadlines

    def __repr__(self):
        return 'Task(id=%r, %r, state=%r)' % (self.id, self.coro, self.state)

    def __str__(self):
        return self.coro.__qualname__

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

async def spawn(coro, *, daemon=False):
    '''
    Create a new task.  Use the daemon=True option if the task runs
    forever as a background task.
    '''
    return await _spawn(coro, daemon)

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

    async def __aiter__(self):
        return self

    async def __anext__(self):
        next = await self.next_done()
        if next is None:
            raise StopAsyncIteration
        return next

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

class _CancellationManager:
    def __init__(self, state):
        self._state = state

    async def __aenter__(self):
        try:
            await _cancel_allowed_stack_push(self._state)
        except Exception:
            await _cancel_allowed_stack_pop(self._state)
            raise

    async def __aexit__(self, ty, val, tb):
        await _cancel_allowed_stack_pop(self._state)

defer_cancellation = _CancellationManager(False)
allow_cancellation = _CancellationManager(True)

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
