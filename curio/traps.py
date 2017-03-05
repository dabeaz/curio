# traps.py
#
# Coroutines corresponding to the kernel traps.  These functions
# provide the bridge from tasks to the underlying kernel. This is the
# only place where the explicit @coroutine decorator needs to be used.
# All other code in curio and in user-tasks should use async/await
# instead.  Direct use by users is allowed, but if you're working with
# these traps directly, there is probably a higher level interface
# that simplifies the problem you're trying to solve (e.g., Socket,
# File, objects, etc.).
# ----------------------------------------------------------------------

__all__ = [ 
    '_read_wait', '_write_wait', '_future_wait', '_sleep', '_spawn',
    '_join_task', '_cancel_task', '_scheduler_wait',
    '_scheduler_wake', '_sigwatch', '_sigunwatch', '_sigwait',
    '_get_kernel', '_get_current', '_set_timeout', '_unset_timeout',
    '_clock',
    ]

# -- Standard library

from types import coroutine
from selectors import EVENT_READ, EVENT_WRITE
from enum import IntEnum

# -- Curio

from . import errors

class Traps(IntEnum):
    _trap_io = 0
    _trap_future_wait = 1
    _trap_sleep = 2
    _trap_join_task = 3
    _trap_sched_wait = 4
    _trap_sched_wake = 5
    _trap_sigwait = 6
    _trap_cancel_task = 7
    _trap_get_kernel = 8
    _trap_get_current = 9
    _trap_set_timeout = 10
    _trap_unset_timeout = 11
    _trap_clock = 12
    _trap_sigwatch = 13
    _trap_sigunwatch = 14
    _trap_spawn = 15



globals().update((trap.name, trap) for trap in Traps)


@coroutine
def _read_wait(fileobj):
    '''
    Wait until reading can be performed.
    '''
    yield (_trap_io, fileobj, EVENT_READ, 'READ_WAIT')


@coroutine
def _write_wait(fileobj):
    '''
    Wait until writing can be performed.
    '''
    yield (_trap_io, fileobj, EVENT_WRITE, 'WRITE_WAIT')


@coroutine
def _future_wait(future, event=None):
    '''
    Wait for the result of a Future to be ready.
    '''
    yield (_trap_future_wait, future, event)


@coroutine
def _sleep(clock, absolute):
    '''
    Sleep until the monotonic clock reaches the specified clock value.
    If clock is 0, forces the current task to yield to the next task (if any).
    absolute is a boolean flag that indicates whether or not the clock
    period is an absolute time or relative.
    '''
    return (yield (_trap_sleep, clock, absolute))


@coroutine
def _spawn(coro, daemon, taskid=None):
    '''
    Create a new task. Returns the resulting Task object.
    '''
    return (yield _trap_spawn, coro, daemon, taskid)


@coroutine
def _cancel_task(task, exc=errors.TaskCancelled, val=None):
    '''
    Cancel a task. Causes a CancelledError exception to raise in the task.
    '''
    yield (_trap_cancel_task, task, exc, val)


@coroutine
def _join_task(task):
    '''
    Wait for a task to terminate.
    '''
    yield (_trap_join_task, task)


@coroutine
def _scheduler_wait(sched, state):
    '''
    Put the task to sleep on a scheduler primitive.
    '''
    yield (_trap_sched_wait, sched, state)


@coroutine
def _scheduler_wake(sched, n=1):
    '''
    Reschedule one or more tasks waiting on a scheduler primitive.
    '''
    yield (_trap_sched_wake, sched, n)


@coroutine
def _sigwatch(sigset):
    '''
    Start monitoring a signal set
    '''
    yield (_trap_sigwatch, sigset)


@coroutine
def _sigunwatch(sigset):
    '''
    Stop watching a signal set
    '''
    yield (_trap_sigunwatch, sigset)


@coroutine
def _sigwait(sigset):
    '''
    Wait for a signal to arrive.
    '''
    yield (_trap_sigwait, sigset)


@coroutine
def _get_kernel():
    '''
    Get the kernel executing the task.
    '''
    return (yield (_trap_get_kernel,))


@coroutine
def _get_current():
    '''
    Get the currently executing task
    '''
    return (yield (_trap_get_current,))


@coroutine
def _set_timeout(clock):
    '''
    Set a timeout for the current task that occurs at the specified clock value.
    Setting a clock of None clears any previous timeout.
    '''
    return (yield (_trap_set_timeout, clock))


@coroutine
def _unset_timeout(previous):
    '''
    Restore the previous timeout for the current task.
    '''
    yield (_trap_unset_timeout, previous)


@coroutine
def _clock():
    '''
    Return the value of the kernel clock
    '''
    return (yield (_trap_clock,))
