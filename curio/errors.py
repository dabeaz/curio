# curio/errors.py
#
# Curio specific exceptions

__all__ = [
    'CurioError', 'CancelledError', 'TaskTimeout', 'TaskError',
    'TaskInterrupted', 'TaskGroupError', 'SyncIOError', 'TaskExit',
    'KernelExit', 'ResourceBusy', 'ReadResourceBusy',
    'WriteResourceBusy', 'GroupExit', 'TimeoutCancellationError',
    'UncaughtTimeoutError', 'TaskCancelled', 'AsyncOnlyError',
]


class CurioError(Exception):
    '''
    Base class for all Curio-related exceptions
    '''


class CancelledError(CurioError):
    '''
    Base class for all task-cancellation related exceptions
    '''


class TaskCancelled(CancelledError):
    '''
    Exception raised from task being directly cancelled.
    '''


class GroupExit(TaskCancelled):
    '''
    Exception that can be raised by a task to directly cancel
    all tasks in its task group.
    '''

class TaskExit(TaskCancelled):
    '''
    Exception that can be raised to directly cancel itself.
    '''

class TimeoutCancellationError(CancelledError):
    '''
    Exception raised if task is being cancelled due to a timeout, but
    not the inner-most timeout in effect. 
    '''


class TaskTimeout(CancelledError):
    '''
    Exception raised if task is cancelled due to timeout.
    '''

class TaskInterrupted(CancelledError):
    '''
    Raised if the current operation is interrupted for some
    reason. It's implied that the task would catch this and
    retry the operation.
    '''

class UncaughtTimeoutError(CurioError):
    '''
    Raised if a TaskTimeout exception escapes a timeout handling
    block and is unexpectedly caught by an outer timeout handler.
    '''


class TaskError(CurioError):
    '''
    Raised if a task launched via spawn() or similar function 
    terminated due to an exception.  This is a chained exception.
    The __cause__ attribute contains the actual exception that
    occurred in the task.
    '''

class TaskGroupError(CurioError):
    '''
    Raised if one or more tasks in a task group raised an error.
    The .failed attribute contains a list of all tasks that died.
    The .errors attribute contains a set of all exceptions raised.
    '''
    def __init__(self, failed):
        self.args = (failed,)
        self.failed = failed
        self.errors = { type(task.next_exc) for task in failed }

    def __str__(self):
        return 'TaskGroupError(%s)' % ', '.join(err.__name__ for err in self.errors)

    def __iter__(self):
        return self.failed.__iter__()

class SyncIOError(CurioError):
    '''
    Raised if a task attempts to perform a synchronous I/O operation
    on an object that only supports asynchronous I/O.
    '''


class AsyncOnlyError(CurioError):
    '''
    Raised by the AWAIT() function if its applied to code not 
    properly running in an async-thread.
    '''


class ResourceBusy(CurioError):
    '''
    Raised by I/O related functions if an operation is requested,
    but the resource is already busy performing the same operation
    on behalf of another task.
    '''

class ReadResourceBusy(ResourceBusy):
    pass

class WriteResourceBusy(ResourceBusy):
    pass

class KernelExit(BaseException):
    '''
    Exception that can be raised by user-code to force the entire
    Curio kernel to exit.
    '''
