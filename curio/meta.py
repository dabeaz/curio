# curio/meta.py
#     ___
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die.
#

__all__ = [ 'blocking', 'cpubound', 'awaitable', 'sync_only', 'AsyncABC', 'AsyncObject' ]

import sys
import inspect
from functools import wraps
from . import workers
from abc import ABCMeta, abstractmethod

def blocking(func):
    '''
    Decorator indicating that a function performs a blocking operation.
    If called from synchronous Python code, the function runs normally.
    However, if called from a coroutine, curio arranges for it to run
    in a thread.  
    '''
    @wraps(func)
    def wrapper(*args, **kwargs):
        if sys._getframe(1).f_code.co_flags & 0x80:
            return workers.run_in_thread(func, *args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wrapper

def cpubound(func):
    '''
    Decorator indicating that a function performs a cpu-intensive operation.
    If called from synchronous Python code, the function runs normally.
    However, if called from a coroutine, curio arranges for it to run
    in a process.
    '''
    @wraps(func)
    def wrapper(*args, **kwargs):
        if sys._getframe(1).f_code.co_flags & 0x80:
            # The use of wrapper in the next statement is not a typo.
            return workers.run_in_process(wrapper, *args, **kwargs)
        else:
            return func(*args, **kwargs)
    return wrapper

def sync_only(func):
    '''
    Decorator indicating that a function is only valid in synchronous code.
    '''
    @wraps(func)
    def wrapper(*args, **kwargs):
        if sys._getframe(1).f_code.co_flags & 0x80:
            raise RuntimeError('{} may only be used in synchronous code'.format(func.__name__))
        else:
            return func(*args, **kwargs)
    return wrapper
    
def awaitable(syncfunc):
    '''
    Decorator that allows an asynchronous function to be paired with a
    synchronous function in a single function call.  The selection of
    which function executes depends on the calling context.  For example:

        def spam(sock, maxbytes):                       (A)
            return sock.recv(maxbytes)

        @awaitable(spam)                                (B)
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

class AsyncABCMeta(ABCMeta):
    '''
    Metaclass that gives all of the features of an abstract base class, but
    additionally enforces coroutine correctness on subclasses. If any method
    is defined as a coroutine in a parent, it must also be defined as a 
    coroutine in any child.
    '''
    def __init__(cls, name, bases, methods):
        coros = {}
        for base in reversed(cls.__mro__):
            coros.update((name, val) for name, val in vars(base).items()
                         if inspect.iscoroutinefunction(val))

        for name, val in vars(cls).items():
            if name in coros and not inspect.iscoroutinefunction(val):
                raise TypeError('Must use async def %s%s' % (name, inspect.signature(val)))
        super().__init__(name, bases, methods)

class AsyncABC(metaclass=AsyncABCMeta):
    pass

class AsyncInstanceType(AsyncABCMeta):
    '''
    Metaclass that allows for asynchronous instance initialization and the
    __init__() method to be defined as a coroutine.   Usage:

    class Spam(metaclass=AsyncInstanceType):
        async def __init__(self, x, y):
            self.x = x
            self.y = y

    async def main(): 
         s = await Spam(2, 3)
         ...
    '''
    @staticmethod
    def __new__(meta, clsname, bases, attributes):
        if '__init__' in attributes and not inspect.iscoroutinefunction(attributes['__init__']):
            raise TypeError('__init__ must be a coroutine')
        return super().__new__(meta, clsname, bases, attributes)

    async def __call__(cls, *args, **kwargs):
         self = cls.__new__(cls, *args, **kwargs)
         await self.__init__(*args, **kwargs)
         return self

class AsyncObject(metaclass=AsyncInstanceType):
    pass
