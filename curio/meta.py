# curio/meta.py
#     ___        
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die. 
#

import sys
import inspect
from functools import wraps

from .kernel import Kernel

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

class _AwaitDict(dict):
    '''
    Metaclass helper that allows sync/async methods to be paired together.
    Uses the @awaitable decorator above to do the pairing.
    '''
    def __setitem__(self, name, value):
        sync_func = None
        async_func = None
        previous_func = self.get(name)
        if previous_func:
            if inspect.iscoroutinefunction(previous_func):
                async_func = previous_func
            else:
                sync_func = previous_func
            if inspect.iscoroutinefunction(value):
                async_func = value
            else:
                sync_func = value
        if sync_func and async_func:
            value = awaitable(sync_func)(async_func)
        super().__setitem__(name, value)

class DualIOMeta(type):
    '''
    Metaclass that allows the definition of both synchronous and asynchronous
    methods in the same class.  For example:

        class Spam(metaclass=DualIOMeta):
            def foo(self):
                ...
            async def foo(self):
                ...

    The method foo() becomes a single method that triggers the appropriate version
    depending on the calling context. See the @awaitable decorator above.
    '''
    def __prepare__(self, *args, **kwargs):
        return _AwaitDict()

class DualIO(metaclass=DualIOMeta):
    pass

def allow_sync(func):
    if not inspect.iscoroutinefunction(func):
        raise TypeError('%s must be a coroutine' % func.__name__)

    @wraps(func)
    def wrapper(*args, **kwargs):
        if sys._getframe(1).f_code.co_flags & 0x80:
            return func(*args, **kwargs)
        else:
            # Not being called from a coroutine. Have a kernel run it
            with Kernel() as k:
                return k.run(func(*args, **kwargs))

    return wrapper






