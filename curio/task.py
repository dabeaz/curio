# curio/task.py
#
# Task class and task related functions.

__all__ = [ 'sleep', 'current_task', 'spawn', 'gather', 'timeout_after', 'ignore_after' ]

from .errors import CancelledError, TaskTimeout, TaskError
from .traps import *

class Task(object):
    '''
    The Task class wraps a coroutine and provides some additional attributes
    related to execution state and debugging.
    '''
    __slots__ = (
        'id', 'daemon',  'coro', '_send', '_throw', 'cycles', 'state',
        'cancel_func', 'future', 'sleep', 'timeout', 'exc_info', 'next_value',
        'next_exc', 'joining', 'cancelled', 'terminated', '_last_io', '__weakref__',
        )
    _lastid = 1
    def __init__(self, coro, daemon=False):
        self.id = Task._lastid   
        Task._lastid += 1
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
        self._last_io = None       # Last I/O operation performed
        self._send = coro.send     # Bound coroutine methods
        self._throw = coro.throw

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

    async def cancel(self, *, exc=CancelledError):
        '''
        Cancel a task by raising a CancelledError exception.  Does not
        return until the task actually terminates.  Returns True if
        the task was actually cancelled. False is returned if the task
        was already completed.  Change the exception raised in the task
        by specifying a different exception with the exc argument.
        '''
        if self.terminated:
            return False
        else:
            await _cancel_task(self, exc)
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
    await _sleep(seconds)

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

# Helper class for running timeouts as a context manager
class _TimeoutAfter(object):
    def __init__(self, seconds, ignore=False, timeout_result=None):
        self._seconds = seconds
        self._ignore = ignore
        self._timeout_result = timeout_result
        self.result = True

    async def __aenter__(self):
        self._prior = await _set_timeout(self._seconds)
        return self

    async def __aexit__(self, ty, val, tb):
        await _unset_timeout(self._prior)
        if ty == TaskTimeout:
            self.result = self._timeout_result
            if self._ignore:
                return True

async def _timeout_after_func(seconds, coro, ignore=False, timeout_result=None):
    prior = await _set_timeout(seconds)
    try:
        return await coro
    except TaskTimeout:
        if not ignore:
            raise
        return timeout_result
    finally:
        await _unset_timeout(prior)

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
        return _TimeoutAfter(seconds)
    else:
        return _timeout_after_func(seconds, coro)

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
        return _TimeoutAfter(seconds, ignore=True, timeout_result=timeout_result)
    else:
        return _timeout_after_func(seconds, coro, ignore=True, timeout_result=timeout_result)
