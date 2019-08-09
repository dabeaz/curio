# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'AWAIT', 'async_thread', 'spawn_thread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine, isgenerator
from contextlib import contextmanager
from types import coroutine
import sys
import logging

log = logging.getLogger(__name__)

# -- Curio

from . import sync
from . import queue
from .task import spawn, disable_cancellation, check_cancellation, set_cancellation, current_task
from .traps import _future_wait, _scheduler_wait, _scheduler_wake
from . import errors
from . import io
from . import sched
from . import meta

_locals = threading.local()

# Class that allows functions to be registered to thread-exit.
# Note: This requires at most only one reference to be held in _locals above
class ThreadAtExit(object):
    def __init__(self):
        self.callables = []

    def atexit(self, callable):
        self.callables.append(callable)

    def __del__(self):
        for func in self.callables:
            try:
                func()
            except Exception as e:
                log.warning('Exception in thread_exit handler ignored', exc_info=e)

class AsyncThread(object):

    def __init__(self, target, args=(), kwargs={}, daemon=False):
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.daemon = daemon
        self.terminated = False
        self.cancelled = False
        self._taskgroup = None

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
        self._joined = False

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

        if self._taskgroup:
            await self._taskgroup._task_done(self)
            self._joined = True

    def _func_runner(self):
        _locals.thread = self
        _locals.thread_exit = ThreadAtExit()
        try:
            self._coro_result = self.target(*self.args, **self.kwargs)
            self._coro_exc = None
            # self.next_result = (self.target(*self.args, **self.kwargs), None)
            # self.next_value = self.target(*self.args, **self.kwargs)
            #self.next_exc = None
        except BaseException as e:
            self._coro_result = None
            self._coro_exc = e

            #self.next_value = None
            #self.next_exc = e
            if not isinstance(e, errors.CancelledError):
                log.warning("Unexpected exception in cancelled async thread", exc_info=True)
                
        finally:
            self._request.set_result(None)
            self._terminate_evt.set()

    async def start(self):
        self._task = await spawn(self._coro_runner, daemon=True)
        self._thread = threading.Thread(target=self._func_runner) # , daemon=True)
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
        self._joined = True

        if self._taskgroup:
            self._taskgroup._task_discard(self)

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



def _check_async_thread_block(code, offset, _cache={}):
    '''
    Analyze a given async_thread() context manager block to make sure it doesn't
    contain any await operations
    '''
    if (code, offset) in _cache:
        return _cache[code, offset]

    import dis
    instr = dis.get_instructions(code)
    level = 0
    result = True
    for op in instr:
        if op.offset < offset:
            continue
        if op.opname == 'SETUP_ASYNC_WITH':
            level += 1
        if op.opname in { 'YIELD_FROM', 'YIELD_VALUE' } and level > 0:
            result = False
            break
        if op.opname == 'WITH_CLEANUP_START':
            level -= 1
            if level == 0:
                break
            
    _cache[code, offset] = result
    return result

@coroutine
def _async_thread_exit():
    yield _AsyncContextManager

class _AsyncContextManager:
    async def __aenter__(self):
        frame = sys._getframe(1)
        if not _check_async_thread_block(frame.f_code, frame.f_lasti):
            raise RuntimeError("async/await not allowed inside an async_thread context block")


        # Check if we've been cancelled prior to launching any thread
        await check_cancellation()

        # We need to arrange a handoff of execution to a separate
        # thread. It's a bit tricky, by the gist of the idea is that
        # an AsyncThread is launched and made to wait for an event.
        # The current task suspends itself on a throwaway scheduling
        # barrier and arranges for the event to be set on suspension.
        # The thread will then take over and drive the task through a
        # single execution cycle on the thread.

        self.task = await current_task()
        self.start = sync.UniversalEvent()
        self.thread = AsyncThread(target=self._runner)
        self.barrier = sched.SchedBarrier()
        await self.thread.start()
        self.task.suspend_func = lambda: self.start.set()
        await _scheduler_wait(self.barrier, 'ASYNC_CONTEXT_ENTER')

    async def __aexit__(self, ty, val, tb):
        # This method is not executed by Curio proper.  Instead, the _runner()
        # method below drives the coroutine into here.   The await statement that
        # follows causes the coroutine to stop at this point.  _runner() will 
        # arrange to have the task resume normal execution in its original thread
        await _async_thread_exit()

    def _runner(self):
        # Wait for the task to be suspended
        self.start.wait()

        # This coroutine stands in for the original task.  The primary purpose
        # of this is to make cancellation/timeout requests work properly.  We'll
        # wait for the _runner() thread to terminate.  If it gets cancelled,
        # we cancel the associated thread.  
        async def _waiter():
            try:
                await self.thread.join()
            except errors.CancelledError as e:
                await self.thread.cancel(exc=e)

            # The original task needs to come back
            self.task._switch(orig_coro)
            self.task.cancel_pending = self.thread._task.cancel_pending

            # This never returns... the task resumes immediately, but it's back
            # in its original coroutine.
            await current_task()

        # Context-switch the Task to run a different coroutine momentarily
        orig_coro = self.task._switch(_waiter())
        self.task._trap_result = None

        # Reawaken the task.  It's going to wake up in the _waiter()  coroutine above. 
        AWAIT(_scheduler_wake(self.barrier, 1))

        # Run the code through a *single* send() cycle. It should end up on the
        # await _async_thread_exit() operation above.  It is critically important that
        # no bare await/async operations occur in this process.  The code should have
        # been validated previously.  It *IS* okay for AWAIT() operations to be used.
        result = orig_coro.send((None,None))

        # If the result is not the result of _async_thread_exit() above, then
        # some kind of very bizarre runtime problem has been encountered.
        if result is not _AsyncContextManager:
            self.task._throw(RuntimeError('yielding not allowed in AsyncThread. Got %r' % result))

        # At this point, the body of the context manager is done.  We simply
        # fall off the end of the function.  The _waiter() coroutine will
        # awaken and switch back to the original coroutine.

def spawn_thread(func=None, *args, daemon=False):
    '''
    Launch an async thread.  This mimicks the way a task is normally spawned. For
    example:

         t = await spawn_thread(func, arg1, arg2)
         ...
         await t.join()

    It can also be used as a context manager to launch a code block into a thread:

         async with spawn_thread():
             sync_op ...
             sync_op ...
    '''
    if func is None:
        return _AsyncContextManager()
    else:
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

# Experimental.  Functions that allow an already existing thread to start communicating
# with Curio as if it were an AsyncThread.  The main requirements of this is that
# Curio already needs to be running somewhere. A support task (_coro_runner) needs to
# be running in Curio to respond to requests from the thread and handle them. 

_request_queue = None

def TAWAIT(coro, *args, **kwargs):
    '''
    Ensure that the caller is an async thread (promoting if necessary),
    then await for a coroutine
    '''
    if not is_async_thread():
        enable_async()
    return AWAIT(coro, *args, **kwargs)

def thread_atexit(callable):
    _locals.thread_exit.atexit(callable)

def enable_async():
    '''
    Enable asynchronous operations in an existing thread.  This only
    shuts down once the thread exits.
    '''
    if hasattr(_locals, 'thread'):
        return

    if _request_queue is None:
        raise RuntimeError('Curio: enable_threads not used')

    fut = Future()
    _request_queue.put(('start', threading.current_thread(), fut))
    _locals.thread = fut.result()
    _locals.thread_exit = ThreadAtExit()
    
    def shutdown(thread=_locals.thread, rq=_request_queue):
        fut = Future()
        rq.put(('stop', thread, fut))
        fut.result()
    _locals.thread_exit.atexit(shutdown)

async def thread_handler():
    '''
    Special handler function that allows Curio to respond to
    threads that want to access async functions.   This handler
    must be spawned manually in code that wants to allow normal
    threads to promote to Curio async threads.
    '''
    global _request_queue
    assert _request_queue is None, "thread_handler already running"
    _request_queue = queue.UniversalQueue()

    try:
        while True:
            request, thr, fut = await _request_queue.get()
            if request == 'start':
                athread = AsyncThread(None)
                athread._task = await spawn(athread._coro_runner, daemon=True)
                athread._thread = thr
                fut.set_result(athread)
            elif request == 'stop':
                thr._request.set_result(None)
                await thr._task.join()
                fut.set_result(None)
    finally:
        _request_queue = None
    
