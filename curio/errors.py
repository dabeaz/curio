# curio/errors.py
#
# Curio specific exceptions

__all__ = [
    'CurioError', 'CancelledError', 'TaskTimeout', 'TaskError', 'SyncIOError',
    'TaskExit', 'KernelExit', 'TimeoutCancellationError', 'UncaughtTimeoutError',
    'TaskCancelled', 'AsyncOnlyError', 'ResultUnavailable',
]


class CurioError(Exception):
    pass


class CancelledError(CurioError):
    pass


class TaskCancelled(CancelledError):
    pass


class TimeoutCancellationError(CancelledError):
    pass


class TaskTimeout(CancelledError):
    pass


class UncaughtTimeoutError(CurioError):
    pass


class TaskError(CurioError):
    pass


class SyncIOError(CurioError):
    pass


class AsyncOnlyError(CurioError):
    pass


class TaskExit(BaseException):
    pass


class KernelExit(BaseException):
    pass


class ResultUnavailable(CurioError):
    pass
