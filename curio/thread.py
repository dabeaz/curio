# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'AWAIT', 'async_thread', 'AsyncThread', 'is_async_thread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine

# -- Curio

from . import sync
from .task import spawn, disable_cancellation
from .traps import _future_wait
from . import errors

_locals = threading.local()

class AsyncThread(object):

    def __init__(self, target, args=(), kwargs={}, daemon=False):
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.daemon = daemon

        self._request = Future()
        self._done_evt = threading.Event()
        self._terminate_evt = sync.UniversalEvent()

        self._coro = None
        self._result_value = None
        self._result_exc = None
        self._thread = None
        self._task = None

    async def _coro_runner(self):
        while True:
            # Wait for a hand-off
            await disable_cancellation(_future_wait(self._request))
            self._coro = self._request.result()
            self._request = Future()

            # If no coroutine, we're shutting down
            if not self._coro:
                break

            # Run the the coroutine
            try:
                self._result_value = await self._coro
                self._result_exc = None

            except BaseException as e:
                self._result_value = None
                self._result_exc = e

            # Hand it back to the thread
            self._done_evt.set()

        await self._terminate_evt.set()

    def _func_runner(self):
        _locals.thread = self
        try:
            self._result_value = self.target(*self.args, **self.kwargs)
            self._result_exc = None
        except BaseException as e:
            self._result_value = None
            self._result_exc = e

        self._request.set_result(None)
        self._terminate_evt.set()

    async def start(self):
        self._task = await spawn(self._coro_runner, daemon=True)
        self._thread = threading.Thread(target=self._func_runner, daemon=True)
        self._thread.start()

    def AWAIT(self, coro):
        self._request.set_result(coro)
        self._done_evt.wait()
        self._done_evt.clear()

        if self._result_exc:
            raise self._result_exc
        else:
            return self._result_value

    async def join(self):
        await self._terminate_evt.wait()
        if self._result_exc:
            raise errors.TaskError() from self._result_exc
        else:
            return self._result_value

    async def cancel(self):
        await self._task.cancel()


def AWAIT(coro):
    '''
    Await for a coroutine in an asynchronous thread.  If coro is
    not a proper coroutine, this function acts a no-op, returning coro.
    '''
    if not iscoroutine(coro):
        return coro

    if hasattr(_locals, 'thread'):
        return _locals.thread.AWAIT(coro)
    else:
        raise errors.AsyncOnlyError('Must be used as async')

def async_thread(func=None, *, daemon=False):
    if func is None:
        return lambda func: async_thread(func, daemon=daemon)

    @wraps(func)
    async def runner(*args, **kwargs):
        t = AsyncThread(func, args=args, kwargs=kwargs, daemon=daemon)
        await t.start()
        try:
            return await t.join()
        except errors.CancelledError as e:
            await t.cancel()
            raise
        except errors.TaskError as e:
            raise e.__cause__ from None
    return runner

def is_async_thread():
    return hasattr(_locals, 'thread')

