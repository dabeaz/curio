# curio/thread.py
#
# Not your parent's threading

__all__ = [ 'AWAIT', 'async_thread', 'async_context', 'async_iter', 'AsyncThread', 'is_async_thread' ]

# -- Standard Library

import threading
from concurrent.futures import Future
from functools import wraps
from inspect import iscoroutine
from contextlib import contextmanager

# -- Curio

from . import sync
from .task import spawn, disable_cancellation
from .traps import _future_wait
from . import errors
from . import io

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
    
