# curio/thread.py
#
# Support for threads implemented on top of the Curio kernel

__all__ = [ 'AWAIT', 'async_thread', 'spawn_thread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine, isgenerator
from contextlib import contextmanager
import sys
import logging

log = logging.getLogger(__name__)

# -- Curio

from . import sync
from . import queue
from .task import spawn, disable_cancellation, check_cancellation, set_cancellation
from .traps import _future_wait
from . import errors
from . import meta

_locals = threading.local()

class AsyncThread(object):

    def __init__(self, target, args=(), kwargs={}, daemon=False):
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.daemon = daemon
        self.terminated = False
        self.cancelled = False
        self.taskgroup = None

        self._request = Future()
        self._done_evt = threading.Event()
        self._terminate_evt = sync.UniversalEvent()

        self._coro = None
        self._coro_result = None
        self._coro_exc = None

        self._final_value = None
        self._final_exc = None

        self._thread = None
        self._task = None
        self.joined = False

    async def _coro_runner(self):
        while True:
            # Wait for a hand-off
            await disable_cancellation(_future_wait(self._request))
            coro = self._request.result()
            self._request = Future()

            # If no coroutine, we're shutting down
            if not coro:
                break

            # Run the the coroutine
            try:
                self._coro_result = await coro
                self._coro_exc = None
            except BaseException as e:
                self._coro_result = None
                self._coro_exc = e

            # Hand it back to the thread
            coro = None
            self._done_evt.set()

        if self.taskgroup:
            await self.taskgroup._task_done(self)
            self.joined = True

    def _func_runner(self):
        _locals.thread = self
        try:
            self._coro_result = self.target(*self.args, **self.kwargs)
            self._coro_exc = None
        except BaseException as e:
            self._coro_result = None
            self._coro_exc = e
            if not isinstance(e, errors.CancelledError):
                log.warning("Unexpected exception in cancelled async thread", exc_info=True)
                
        finally:
            self._request.set_result(None)
            self._terminate_evt.set()

    async def start(self):
        self._task = await spawn(self._coro_runner, daemon=True)
        self._thread = threading.Thread(target=self._func_runner)
        self._thread.start()

    def AWAIT(self, coro):
        self._request.set_result(coro)
        self._done_evt.wait()
        self._done_evt.clear()

        if self._coro_exc:
            raise self._coro_exc
        else:
            return self._coro_result

    async def join(self):
        await self.wait()
        self.joined = True

        if self.taskgroup:
            self.taskgroup._task_discard(self)

        if self._coro_exc:
            raise errors.TaskError() from self._coro_exc
        else:
            return self._coro_result

    async def wait(self):
        await self._terminate_evt.wait()
        self.terminated = True

    @property
    def result(self):
        if not self._terminate_evt.is_set():
            raise RuntimeError('Thread not terminated')
        if self._coro_exc:
            raise self._coro_exc
        else:
            return self._coro_result

    @property
    def exception(self):
        if not self._terminate_evt.is_set():
            raise RuntimeError('Thread not terminated')
        return self._coro_exc

    async def cancel(self, *, exc=errors.TaskCancelled, blocking=True):
        self.cancelled = True
        await self._task.cancel(exc=exc, blocking=blocking)
        if blocking:
            await self.wait()


def AWAIT(coro, *args, **kwargs):
    '''
    Await for a coroutine in an asynchronous thread.  If coro is
    not a proper coroutine, this function acts a no-op, returning coro.
    '''
    # If the coro is a callable and it's identifiable as a coroutine function,
    # wrap it inside a coroutine and pass that.
    if callable(coro):
        if meta.iscoroutinefunction(coro) and hasattr(_locals, 'thread'):
            async def _coro(coro):
                return await coro(*args, **kwargs)
            coro = _coro(coro)
        else:
            coro = coro(*args, **kwargs)


    if iscoroutine(coro) or isgenerator(coro):
        if hasattr(_locals, 'thread'):
            return _locals.thread.AWAIT(coro)
        else:
            # Thought: Do we try to promote the calling thread into an "async" thread automatically?
            # Would require a running kernel. Would require a task dedicated to spawning the coro
            # runner.   Would require shutdown.  Maybe a context manager?
            raise errors.AsyncOnlyError('Must be used as async')
    else:
        return coro

def spawn_thread(func, *args, daemon=False):
    '''
    Launch an async thread.  This mimicks the way a task is normally spawned. For
    example:

         t = await spawn_thread(func, arg1, arg2)
         ...
         await t.join()
    '''
    if iscoroutine(func) or meta.iscoroutinefunction(func):
          raise TypeError("spawn_thread() can't be used on coroutines")

    async def runner(args, daemon):
        t = AsyncThread(func, args=args, daemon=daemon)
        await t.start()
        return t

    return runner(args, daemon)

def async_thread(func=None, *, daemon=False):
    '''
    Decorator that is used to mark a callable as running in an asynchronous thread
    '''
    if func is None:
        return lambda func: async_thread(func, daemon=daemon)

    if meta.iscoroutinefunction(func):
        raise TypeError("async_thread can't be applied to coroutines.")
        
    @wraps(func)
    def wrapper(*args, **kwargs):
        if meta._from_coroutine() and not is_async_thread():
            async def runner(*args, **kwargs):
                # Launching async threads could result in a situation where 
                # synchronous code gets executed,  but there is no opportunity
                # for Curio to properly check for cancellation.  This next
                # call is a sanity check--if there's pending cancellation, don't
                # even bother to launch the associated thread.
                await check_cancellation()
                t = AsyncThread(func, args=args, kwargs=kwargs, daemon=daemon)
                await t.start()
                try:
                    return await t.join()
                except errors.CancelledError as e:
                    await t.cancel(exc=e)
                    await set_cancellation(t._task.cancel_pending)
                    if t._coro_exc:
                        raise t._coro_exc from None
                    else:
                        return t._coro_result
                except errors.TaskError as e:
                    raise e.__cause__ from None
            return runner(*args, **kwargs)
        else:
            return func(*args, **kwargs)
    wrapper._async_thread = True
    return wrapper

def is_async_thread():
    '''
    Returns True if current thread is an async thread.
    '''
    return hasattr(_locals, 'thread')
