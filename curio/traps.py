# traps.py
#
# Curio programs execute under the supervision of a kernel. Communication
# with the kernel takes place via a "trap" involving the yield statement.
# Traps encode an internel kernel procedure name as well as its arguments.
# Direct use of the functions defined here is allowed when making new
# kinds of Curio primitives, but if you're trying to solve a higher
# level problem, there is probably a higher-level interface that is
# easier to use (e.g., Socket, File, Queue, etc.).
# ----------------------------------------------------------------------

__all__ = [ 
    '_read_wait', '_write_wait', '_future_wait', '_sleep', '_spawn',
    '_cancel_task', '_scheduler_wait', '_scheduler_wake',
    '_get_kernel', '_get_current', '_set_timeout', '_unset_timeout',
    '_clock', '_io_waiting',
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
    _trap_sched_wait = 3
    _trap_sched_wake = 4
    _trap_cancel_task = 5
    _trap_get_kernel = 6
    _trap_get_current = 7
    _trap_set_timeout = 8
    _trap_unset_timeout = 9
    _trap_clock = 10
    _trap_spawn = 11
    _trap_io_waiting = 12


globals().update((trap.name, trap) for trap in Traps)

# This is the only entry point to the Curio kernel and the
# only place where the @types.coroutine decorator is used. 
@coroutine
def _kernel_trap(*request):
    return (yield request)

# Higher-level trap functions that make use of async/await
async def _read_wait(fileobj):
    '''
    Wait until reading can be performed.  If another task is waiting
    on the same file, a ResourceBusy exception is raised. 
    '''
    return await _kernel_trap(_trap_io, fileobj, EVENT_READ, 'READ_WAIT')

async def _write_wait(fileobj):
    '''
    Wait until writing can be performed. If another task is waiting
    to write on the same file, a ResourceBusy exception is raised.
    '''
    return await _kernel_trap(_trap_io, fileobj, EVENT_WRITE, 'WRITE_WAIT')

async def _io_waiting(fileobj):
    '''
    Return a tuple (rtask, wtask) of tasks currently blocked waiting
    for I/O on fileobj.
    '''
    return await _kernel_trap(_trap_io_waiting, fileobj)

async def _future_wait(future, event=None):
    '''
    Wait for the result of a Future to be ready.
    '''
    return await _kernel_trap(_trap_future_wait, future, event)

async def _sleep(clock, absolute):
    '''
    Sleep until the monotonic clock reaches the specified clock value.
    If clock is 0, forces the current task to yield to the next task (if any).
    absolute is a boolean flag that indicates whether or not the clock
    period is an absolute time or relative.
    '''
    return await _kernel_trap(_trap_sleep, clock, absolute)


async def _spawn(coro):
    '''
    Create a new task. Returns the resulting Task object.
    '''
    return await _kernel_trap(_trap_spawn, coro)


async def _cancel_task(task, exc=errors.TaskCancelled, val=None):
    '''
    Cancel a task. Causes a CancelledError exception to raise in the task.
    Set the exc and val arguments to change the exception.
    '''
    return await _kernel_trap(_trap_cancel_task, task, exc, val)


async def _scheduler_wait(sched, state):
    '''
    Put the task to sleep on a scheduler primitive.
    '''
    return await _kernel_trap(_trap_sched_wait, sched, state)


async def _scheduler_wake(sched, n=1):
    '''
    Reschedule one or more tasks waiting on a scheduler primitive.
    '''
    return await _kernel_trap(_trap_sched_wake, sched, n)


async def _get_kernel():
    '''
    Get the kernel executing the task.
    '''
    return await _kernel_trap(_trap_get_kernel)


async def _get_current():
    '''
    Get the currently executing task
    '''
    return await _kernel_trap(_trap_get_current)

async def _set_timeout(clock):
    '''
    Set a timeout for the current task that occurs at the specified clock value.
    Setting a clock of None clears any previous timeout.
    '''
    return await _kernel_trap(_trap_set_timeout, clock)


async def _unset_timeout(previous):
    '''
    Restore the previous timeout for the current task.
    '''
    return await _kernel_trap(_trap_unset_timeout, previous)

async def _clock():
    '''
    Return the value of the kernel clock
    '''
    return await _kernel_trap(_trap_clock)
