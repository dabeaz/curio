# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'AWAIT', 'async_thread', 'AsyncThread', 'is_async_thread', 'spawn_thread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine, isgenerator
from contextlib import contextmanager
from types import coroutine
import sys

# -- Curio

from . import sync
from .task import spawn, disable_cancellation, current_task
from .traps import _future_wait, _scheduler_wait, _scheduler_wake
from . import errors
from . import io
from . import sched
from . import meta

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
                self._result_value = await coro
                self._result_exc = None

            except BaseException as e:
                self._result_value = None
                self._result_exc = e

            # Hand it back to the thread
            coro = None
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

    async def wait(self):
        await self._terminate_evt.wait()
        self._joined = True

    @property
    def result(self):
        if not self._terminated_evt.is_set():
            raise RuntimeError('Thread not terminated')
        if self._result_exc:
            raise self._result_exc
        else:
            return self._result_value

    async def cancel(self, *, exc=errors.TaskCancelled):
        await self._task.cancel(exc=exc)
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
        # we cancel the associated thread.   There is some critical synchronization
        # requirements--namely, it's not safe to proceed with the _runner() function
        # until the _waiter() coroutine has started and suspended itself.
        _waiter_evt = threading.Event()
        async def _waiter():
            try:
                self.task.suspend_func = _waiter_evt.set
                await self.thread.join()
            except errors.CancelledError as e:
                await self.thread.cancel(exc=e)
                # This never returns... the task will be waiting for the
                # thread to terminate.  However, the thread switches back to
                # original coroutine at that point.  We are properly closed however.

        # Context-switch the Task to run a different coroutine momentarily
        orig_coro = self.task._switch(_waiter())
        try:
            # Reawaken the task.  It's going to wake up in the _waiter() 
            # coroutine above. 
            AWAIT(_scheduler_wake(self.barrier, 1))
            _waiter_evt.wait()

            # Run the code through a *single* send() cycle. It should end up on the
            # await _async_thread_exit() operation above.  It is critically important that
            # no bare await/async operations occur in this process.  The code should have
            # been validated previously.  It *IS* okay for AWAIT() operations to be used.
            result = orig_coro.send(None)

            # If the result is not the result of _async_thread_exit() above, then
            # some kind of very bizarre runtime problem has been
            # encountered.
            if result is not _AsyncContextManager:
                self.task._throw(RuntimeError('yielding not allowed in AsyncThread. Got %r' % result))
        finally:
            # No matter what has happened, the "Task" is sitting on a
            # termination event right now.  This is happening in the
            # _waiter() coroutine above in either the
            # self.thread.join() or self.thread.wait() method.  We're
            # going to manually remove the task from whatever it's
            # waiting on and arrange to have it reawake upon
            # termination of the coroutine runner task instead.

            if self.task.cancel_func:
                self.task.cancel_func()
                self.task.cancel_func = None

            # Dispense with the _waiter coro and switch back to the original coroutine
            self.task._run_coro.close()   
            self.task._switch(orig_coro)

            # Wait on the joining barrier of the coroutine runner
            self.task.cancel_func = self.thread._task.joining.add(self.task)

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
                t = AsyncThread(func, args=args, kwargs=kwargs, daemon=daemon)
                await t.start()
                try:
                    return await t.join()
                except errors.CancelledError as e:
                    await t.cancel(exc=e)
                    if t._result_exc:
                        raise t._result_exc from None
                    else:
                        return t._result_value
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

class ThreadProxy(object):
    '''
    Wrapper around an instance that turns all of its methods into async
    methods
    '''
    def __init__(self, obj):
        self._obj = obj

    def __getattr__(self, name):
        value = getattr(self._obj, name)
        if callable(value):
            return async_thread(value)
        else:
            return value

# Highly experimental.   These classes allow synchronous code running in an
# async thread to manipulate an async socket as if it were a normal socket.
# Seriously, don't use these.  It's something I'm fooling around with right now.
# -Dave

class ThreadSocket(object):
    '''
    You were warned.
    '''
    def __init__(self, asyncsock):
        self._asyncsock = asyncsock

    def __getattr__(self, name):
        return getattr(self._asyncsock, name)

    def dup(self):
        raise RuntimeError()

    def makefile(self, mode, buffering=0, *, encoding=None, errors=None, newline=None):
        return ThreadFile(self._asyncsock.makefile(mode, buffering, encoding=encoding, errors=errors, newline=newline))

    def settimeout(self, *args):
        pass

    def as_stream(self):
        return ThreadFile(self._asyncsock.as_stream())

    def recv(self, maxsize, flags=0):
        return AWAIT(self._asyncsock.recv(maxsize, flags))

    def recv_into(self, buffer, nbytes=0, flags=0):
        return AWAIT(self._asyncsock.recv_into(buffer, nbytes, flags))

    def send(self, data, flags=0):
        return AWAIT(self._asyncsock.send(data, flags))

    def sendall(self, data, flags=0):
        return AWAIT(self._asyncsock.sendall(data, flags))

    def accept(self):
        client, addr = AWAIT(self._asyncsock.accept())
        return (type(self)(client), addr)

    def connect_ex(self, address):
        return AWAIT(self._asyncsock.connect_ex(address))

    def connect(self, address):
        return AWAIT(self._asyncsock.connect(address))

    def recvfrom(self, buffersize, flags=0):
        return AWAIT(self._asyncsock.recvfrom(buffersize, flags))

    def recvfrom_into(self, buffer, bytes=0, flags=0):
        return AWAIT(self._asyncsock.recvfrom_into(buffer, bytes, flags))

    def sendto(self, bytes, flags_or_address, address=None):
        return AWAIT(self._asyncsock.sendto(bytes, flags_or_address, address))

    def recvmsg(self, bufsize, ancbufsize=0, flags=0):
        return AWAIT(self._asyncsock.recvmsg(bufsize, ancbufsize,flags))

    def recvmsg_into(self, buffers, ancbufsize=0, flags=0):
        return AWAIT(self._asyncsock.recvmsg_into(buffers, ancbufsize, flags))

    def sendmsg(self, buffers, ancdata=(), flags=0, address=None):
        return AWAIT(self._asyncsock.sendmsg(buffers, ancdata, flags, address))

    def do_handshake(self):
        return AWAIT(self._asyncsock.do_handshake())

    def close(self):
        return AWAIT(self._asyncsock.close())

    def shutdown(self, how):
        return AWAIT(self._asyncsock.shutdown(how))

    def __enter__(self):
        return self._asyncsock.__enter__()

    def __exit__(self, *args):
        return self._asyncsock.__exit__(*args)


class ThreadFile(object):
    '''
    You were repeatedly warned.
    '''
    def __init__(self, asyncfileobj):
        self._asyncfile = asyncfileobj

    def write(self, data):
        return AWAIT(self._asyncfile.write(data))

    # ---- General I/O methods for streams
    def read(self, maxbytes=-1):
        return AWAIT(self._asyncfile.read(maxbytes))

    def readall(self):
        return AWAIT(self._asyncfile.readall())

    def read_exactly(self, nbytes):
        return AWAIT(self._asyncfile.read_exactly(nbytes))

    def readinto(self, buf):
        return AWAIT(self._asyncfile.readinto(buf))

    def readline(self, maxbytes=-1):
        return AWAIT(self._asyncfile.readline())

    def readlines(self):
        return AWAIT(self._asyncfile.readlines())

    def writelines(self, lines):
        return AWAIT(self._asyncfile.writelines(lines))

    def flush(self):
        return AWAIT(self._asyncfile.flush())

    def close(self):
        return AWAIT(self._asyncfile.close())

    def __iter__(self):
        return self._asyncfile.__iter__()

    def __enter__(self):
        return self._asyncfile.__enter__()

    def __exit__(self, *args):
        return self._asyncfile.__exit__(*args)


@contextmanager
def more_magic():
    '''
    A vantage point from where you can see "highly experimental" down below if you squint.
    '''
    from socket import socket as socketcls
    socketcls_new = socketcls.__new__

    # Patch socket.socket()
    def __new__(cls, *args, **kwargs):
        sock = socketcls_new(cls, *args, **kwargs)
        if not is_async_thread():
            return sock

        sock.__init__(*args, **kwargs)
        self = ThreadSocket(io.Socket(sock))
        return self
    socketcls.__new__ = __new__

    try:
        yield
    finally:
        socketcls.__new__ = socketcls_new
    
