# curio/meta.py
#     ___
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die.
#

__all__ = [ 'acontextmanager' ]

import sys
import inspect
from functools import wraps
from contextlib import contextmanager

class acontextmanager(object):
    '''
    Decorator that allows an asynchronous context manager to be written
    using the same technique as with the @contextlib.contextmanager
    decorator.
    '''
    def __init__(self, func):
        self.manager = contextmanager(func)

    def __aenter__(self):
        return self.manager.__enter__()

    def __aexit__(self, *args):
        return self.manager.__exit(*args)

    def __enter__(self):
        raise RuntimeError('Use async with')

    def __exit__(self, *args):
        pass

def awaitable(syncfunc):
    '''
    Decorator that allows an asynchronous function to be paired with a
    synchronous function in a single function call.  The selection of
    which function executes depends on the calling context.  For example:

        def spam(sock, maxbytes):                       (A)
            return sock.recv(maxbytes)

        @awaitable(read)                                (B)
        async def spam(sock, maxbytes):
            return await sock.recv(maxbytes)

    In later code, you could use the spam() function in either a synchronous
    or asynchronous context.  For example:

        def foo():
            ...
            r = spam(s, 1024)          # Calls synchronous function (A) above
            ...

        async def bar():
            ...
            r = await spam(s, 1024)    # Calls async function (B) above
            ...

    '''
    def decorate(asyncfunc):
        if inspect.signature(syncfunc) != inspect.signature(asyncfunc):
            raise TypeError('%s and async %s have different signatures' %
                            (syncfunc.__name__, asyncfunc.__name__))

        @wraps(asyncfunc)
        def wrapper(*args, **kwargs):
            if sys._getframe(1).f_code.co_flags & 0x80:
                return asyncfunc(*args, **kwargs)
            else:
                return syncfunc(*args, **kwargs)
        return wrapper
    return decorate
