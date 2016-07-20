# curio/errors.py
#
# Curio specific exceptions

__all__ = [
    'CurioError', 'CancelledError', 'TaskTimeout', 'TaskError', 'SyncIOError',
    ]

class CurioError(Exception):
    pass

class CancelledError(CurioError):
    pass

class TaskTimeout(CurioError):
    pass

class TaskError(CurioError):
    pass

class SyncIOError(CurioError):
    pass

class _CancelRetry(Exception):
    pass
