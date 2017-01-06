# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'await', 'async_thread', 'async_context', 'async_iter', 'AsyncThread' ] 

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine

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
        self._terminate_evt = sync.Event()

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
        self._task = await spawn(self._coro_runner())
        self._thread = threading.Thread(target=self._func_runner)
        self._thread.start()

    def await(self, coro):
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
            raise self._result_exc
        else:
            return self._result_value

    async def cancel(self):
        await self._task.cancel()


def await(coro):
    '''
    Await for a coroutine in an asynchronous thread.  If coro is
    not a proper coroutine, this function acts a no-op, returning coro.
    '''
    if not iscoroutine(coro):
        return coro

    if hasattr(_locals, 'thread'):
        return _locals.thread.await(coro)
    else:
        raise errors.AsyncOnlyError('Must be used as async')

class _AContextRunner(object):
    def __init__(self, acontext):
        self.acontext = acontext

    def __enter__(self):
        return await(self.acontext.__aenter__())

    def __exit__(self, ty, val, tb):
        return await(self.acontext.__aexit__(ty, val, tb))

def async_context(acontext):
    '''
    Run an asynchronous context-manager in an asynchronous thread.
    '''
    return _AContextRunner(acontext)

class _AIterRunner(object):
    def __init__(self, aiter):
        self.aiter = aiter

    def __iter__(self):
        return _AIterRunner(await(self.aiter.__aiter__()))

    def __next__(self):
        try:
            return await(self.aiter.__anext__())

        except StopAsyncIteration as e:
            raise StopIteration from None

def async_iter(aiter):
    '''
    Run an asynchronous iterator in an asynchronous thread.
    '''
    return _AIterRunner(aiter)


def async_thread(func):
    @wraps(func)
    async def runner(*args, **kwargs):
        t = AsyncThread(func, args=args, kwargs=kwargs)
        await t.start()
        try:
            return await t.join()
        except errors.CancelledError as e:
            await t.cancel()
            raise
    return runner


