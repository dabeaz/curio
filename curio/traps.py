# traps.py
#
# Coroutines corresponding to the kernel traps.  These functions
# provide the bridge from tasks to the underlying kernel. This is the
# only place where the explicit @coroutine decorator needs to be used.
# All other code in curio and in user-tasks should use async/await
# instead.  Direct use by users is allowed, but if you're working with
# these traps directly, there is probably a higher level interface
# that simplifies the problem you're trying to solve (e.g., Socket,
# File, objects, etc.)
# ----------------------------------------------------------------------

__all__ = [
    '_read_wait', '_write_wait', '_future_wait', '_sleep',
    '_spawn', '_cancel_task', '_join_task', '_wait_on_queue',
    '_reschedule_tasks', '_sigwatch', '_sigunwatch', '_sigwait',
    '_get_kernel', '_get_current', '_set_timeout', '_unset_timeout'
    ]

from types import coroutine
from selectors import EVENT_READ, EVENT_WRITE

from .errors import _CancelRetry, CancelledError

@coroutine
def _read_wait(fileobj):
    '''
    Wait until reading can be performed.
    '''
    yield ('_trap_io', fileobj, EVENT_READ, 'READ_WAIT')

@coroutine
def _write_wait(fileobj):
    '''
    Wait until writing can be performed.
    '''
    yield ('_trap_io', fileobj, EVENT_WRITE, 'WRITE_WAIT')

@coroutine
def _future_wait(future, event=None):
    '''
    Wait for the result of a Future to be ready.
    '''
    yield ('_trap_future_wait', future, event)

@coroutine
def _sleep(seconds):
    '''
    Sleep for a given number of seconds. Sleeping for 0 seconds
    forces the current task to yield to the next task (if any).
    '''
    yield ('_trap_sleep', seconds)

@coroutine
def _spawn(coro, daemon):
    '''
    Create a new task. Returns the resulting Task object.
    '''
    return (yield '_trap_spawn', coro, daemon)

@coroutine
def _cancel_task(task, exc=CancelledError):
    '''
    Cancel a task. Causes a CancelledError exception to raise in the task.
    The exception can be changed by specifying exc. 
    '''
    while True:
        try:
            yield ('_trap_cancel_task', task, exc)
            return
        except _CancelRetry:
            pass

@coroutine
def _join_task(task):
    '''
    Wait for a task to terminate.
    '''
    yield ('_trap_join_task', task)

@coroutine
def _wait_on_queue(queue, state):
    '''
    Put the task to sleep on a queue.
    '''
    yield ('_trap_wait_queue', queue, state)

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
def _sigwait(sigset):
    '''
    Wait for a signal to arrive.
    '''
    yield ('_trap_sigwait', sigset)

@coroutine
def _get_kernel():
    '''
    Get the kernel executing the task.
    '''
    result = yield ('_trap_get_kernel',)
    return result

@coroutine
def _get_current():
    '''
    Get the currently executing task
    '''
    result = yield ('_trap_get_current',)
    return result

@coroutine
def _set_timeout(seconds):
    '''
    Set a timeout for the current task.  
    '''
    result = yield ('_trap_set_timeout', seconds)
    return result

@coroutine
def _unset_timeout(previous):
    '''
    Restore the previous timeout for the current task.
    '''
    yield ('_trap_unset_timeout', previous)
