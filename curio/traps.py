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
    '_cancel_task', '_cancel_allowed_stack_push', '_cancel_allowed_stack_pop',
    '_join_task',
    '_wait_on_queue', '_reschedule_tasks', '_queue_reschedule_function',
    '_sigwatch', '_sigunwatch', '_sigwait', '_get_kernel', '_get_current',
    '_get_child_tasks','_set_timeout', '_unset_timeout', '_clock',
    ]

from types import coroutine
from selectors import EVENT_READ, EVENT_WRITE
from enum import IntEnum

from .errors import _CancelRetry

class BlockingTraps(IntEnum):
    _blocking_trap_io = 0
    _blocking_trap_future_wait = 1
    _blocking_trap_sleep = 2
    _blocking_trap_join_task = 3
    _blocking_trap_wait_queue = 4
    _blocking_trap_sigwait = 5

class SyncTraps(IntEnum):
    _sync_trap_cancel_task = 0
    _sync_trap_get_kernel = 1
    _sync_trap_get_current = 2
    _sync_trap_set_timeout = 3
    _sync_trap_unset_timeout = 4
    _sync_trap_queue_reschedule_function = 5
    _sync_trap_clock = 6
    _sync_trap_sigwatch = 7
    _sync_trap_sigunwatch = 8
    _sync_trap_spawn = 9
    _sync_trap_reschedule_tasks = 10
    _sync_trap_cancel_allowed_stack_push = 11
    _sync_trap_cancel_allowed_stack_pop = 12
    _sync_trap_get_child_tasks = 13


globals().update((trap.name, trap) for trap in BlockingTraps)
globals().update((trap.name, trap) for trap in SyncTraps)

@coroutine
def _read_wait(fileobj):
    '''
    Wait until reading can be performed.
    '''
    yield (_blocking_trap_io, fileobj, EVENT_READ, 'READ_WAIT')

@coroutine
def _write_wait(fileobj):
    '''
    Wait until writing can be performed.
    '''
    yield (_blocking_trap_io, fileobj, EVENT_WRITE, 'WRITE_WAIT')

@coroutine
def _future_wait(future, event=None):
    '''
    Wait for the result of a Future to be ready.
    '''
    yield (_blocking_trap_future_wait, future, event)

@coroutine
def _sleep(clock, absolute):
    '''
    Sleep until the monotonic clock reaches the specified clock value.
    If clock is 0, forces the current task to yield to the next task (if any).
    absolute is a boolean flag that indicates whether or not the clock
    period is an absolute time or relative.
    '''
    return (yield (_blocking_trap_sleep, clock, absolute))

@coroutine
def _spawn(coro, daemon):
    '''
    Create a new task. Returns the resulting Task object.
    '''
    return (yield _sync_trap_spawn, coro, daemon)

@coroutine
def _cancel_task(task):
    '''
    Cancel a task. Causes a CancelledError exception to raise in the task.
    '''
    yield (_sync_trap_cancel_task, task)

@coroutine
def _cancel_allowed_stack_push(state):
    '''
    Set whether cancellation is allowed in this task.
    '''
    yield (_sync_trap_cancel_allowed_stack_push, n)

@coroutine
def _cancel_allowed_stack_pop(state):
    '''
    Undo the previous call to _cancel_allowed_stack_push
    '''
    yield (_sync_trap_cancel_allowed_stack_pop, state)

@coroutine
def _cancel_allowed_stack_push(state):
    '''
    Set the current
    '''
    yield (_sync_trap_cancel_allowed_stack_push, state)

@coroutine
def _join_task(task):
    '''
    Wait for a task to terminate.
    '''
    yield (_blocking_trap_join_task, task)

@coroutine
def _wait_on_queue(queue, state):
    '''
    Put the task to sleep on a queue.
    '''
    yield (_blocking_trap_wait_queue, queue, state)

@coroutine
def _reschedule_tasks(queue, n=1):
    '''
    Reschedule one or more tasks waiting on a kernel queue.
    '''
    yield (_sync_trap_reschedule_tasks, queue, n)

@coroutine
def _sigwatch(sigset):
    '''
    Start monitoring a signal set
    '''
    yield (_sync_trap_sigwatch, sigset)

@coroutine
def _sigunwatch(sigset):
    '''
    Stop watching a signal set
    '''
    yield (_sync_trap_sigunwatch, sigset)

@coroutine
def _sigwait(sigset):
    '''
    Wait for a signal to arrive.
    '''
    yield (_blocking_trap_sigwait, sigset)

@coroutine
def _get_kernel():
    '''
    Get the kernel executing the task.
    '''
    return (yield (_sync_trap_get_kernel,))

@coroutine
def _get_current():
    '''
    Get the currently executing task
    '''
    return (yield (_sync_trap_get_current,))

@coroutine
def _set_timeout(clock):
    '''
    Set a timeout for the current task that occurs at the specified clock value.
    Setting a clock of None clears any previous timeout. 
    '''
    return (yield (_sync_trap_set_timeout, clock))

@coroutine
def _unset_timeout(previous):
    '''
    Restore the previous timeout for the current task.
    '''
    yield (_sync_trap_unset_timeout, previous)

@coroutine
def _queue_reschedule_function(queue):
    '''
    Return a function that allows tasks to be rescheduled from a queue without
    the use of await.   Can be used in synchronous code as long as it runs
    in the same thread as the Curio kernel.
    '''
    return (yield (_sync_trap_queue_reschedule_function, queue))

@coroutine
def _clock():
    '''
    Return the value of the kernel clock
    '''
    return (yield (_sync_trap_clock,))

@coroutine
def _get_child_tasks(task):
    return (yield (_sync_trap_get_child_tasks, task))
