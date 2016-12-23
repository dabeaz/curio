# curio/errors.py
#
# Curio specific exceptions

__all__ = [
    'CurioError', 'CancelledError', 'TaskTimeout', 'TaskError', 'SyncIOError',
    'TaskExit', 'KernelExit', 'TimeoutCancellationError', 'UncaughtTimeoutError',
]


class CurioError(Exception):
    pass


class CancelledError(CurioError):
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


class TaskExit(CurioError):
    pass


class KernelExit(BaseException):
    pass
