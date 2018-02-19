# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'AWAIT', 'async_thread', 'AsyncThread', 'is_async_thread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine
from contextlib import contextmanager
from types import coroutine
import sys

# -- Curio

from . import sync
from .task import spawn, disable_cancellation, current_task
from .traps import _future_wait, _scheduler_wait
from . import errors
from . import io
from . import sched

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


@coroutine
def _acm_exit():
    yield _AsyncContextManager

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
        await self.thread.start()
        await _scheduler_wait(sched.SchedBarrier(), 'ASYNC_CONTEXT_ENTER', lambda: self.start.set())

    async def __aexit__(self, ty, val, tb):
        await _acm_exit()

    def _runner(self):
        # Wait for the task to be suspended
        self.start.wait()

        # Remove the task from the temporary barrier on which it was sleeping.
        # This is done by calling its cancellation function. Note: This doesn't
        # actually cancel the task, it merely performs cleanup actions and 
        # readies the task to run again 
        self.task.cancel_func()
        self.task.cancel_func = None

        # Run the code through a *single* send() cycle. It should end up on the
        # await _acm_exit() operation above.  It is critically important that
        # no await/async operations occur in this process.  The code should have
        # been validated previously.
        result = self.task._send(None)

        # If the result is not the result of _acm_exit() above, then
        # some kind of very bizarre runtime problem has been
        # encountered.
        if result is not _AsyncContextManager:
            self.task._throw(RuntimeError('yielding not allowed in AsyncThread. Got %r' % result))
            
        # Arrange to have the task join with the async thread runner.  This is rather subtle,
        # but this will cause the task to reawaken back in its original execution thread
        # upon the completion of this _runner() function.
        self.thread._task.joining.add(self.task)

def async_thread(func=None):
    if func is None:
        return _AsyncContextManager()

    @wraps(func)
    async def runner(*args, **kwargs):
        t = AsyncThread(func, args=args, kwargs=kwargs)
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
    
