# curio/meta.py
#     ___
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die. No seriously.
#

__all__ = [
    'iscoroutinefunction', 'finalize', 'blocking', 'cpubound',
    'awaitable', 'asyncioable', 'sync_only', 'AsyncABC',
    'AsyncObject', 'curio_running', 'instantiate_coroutine',
 ]

# -- Standard Library

from sys import _getframe
import sys
import inspect
from functools import wraps, partial
from abc import ABCMeta, abstractmethod
import dis
import asyncio
import threading
from contextlib import contextmanager

# -- Curio

from .errors import SyncIOError


_locals = threading.local()

# Context manager that is used when the kernel is executing.

@contextmanager
def running():
    if getattr(_locals, 'running', False):
        raise RuntimeError('Only one Curio kernel per thread is allowed')
    _locals.running = True
    try:
        with asyncgen_manager():
            yield
    finally:
        _locals.running = False

def curio_running():
    '''
    Return a flag that indicates whether or not Curio is running in the current thread.
    '''
    return getattr(_locals, 'running', False)

_CO_NESTED = inspect.CO_NESTED
_CO_FROM_COROUTINE = inspect.CO_COROUTINE | inspect.CO_ITERABLE_COROUTINE | inspect.CO_ASYNC_GENERATOR

try:
    _isasyncgenfunction = inspect.isasyncgenfunction
except AttributeError:
    # Not supported in python 3.5
    _isasyncgenfunction = lambda func: False

def _from_coroutine(level=2):
    f_code = _getframe(level).f_code
    if f_code.co_flags & _CO_FROM_COROUTINE:
        return True
    else:
        # Comment:  It's possible that we could end up here if one calls a function
        # from the context of a list comprehension or a generator expression. For
        # example:
        #
        #   async def coro():
        #        ...
        #        a = [ func() for x in s ]
        #        ...
        #
        # Where func() is some function that we've wrapped with one of the decorators
        # below.  If so, the code object is nested and has a name such as <listcomp> or <genexpr>
        if (f_code.co_flags & _CO_NESTED and f_code.co_name[0] == '<'):
            return _from_coroutine(level + 2)
        else:
            return False

def iscoroutinefunction(func):
    '''
    Modified test for a coroutine function with awareness of functools.partial
    '''
    if isinstance(func, partial):
        return iscoroutinefunction(func.func)
    if hasattr(func, '__func__'):
        return iscoroutinefunction(func.__func__)
    return inspect.iscoroutinefunction(func) or hasattr(func, '_awaitable') or _isasyncgenfunction(func)

def instantiate_coroutine(corofunc, *args, **kwargs):
    '''
    Try to instantiate a coroutine. If corofunc is already a coroutine,
    we're done.  If it's a coroutine function, we call it inside an
    async context with the given arguments to create a coroutine.  If
    it's not a coroutine, we call corofunc(*args, **kwargs) and hope
    for the best.
    '''
    if inspect.iscoroutine(corofunc) or inspect.isgenerator(corofunc):
        return corofunc

    if not iscoroutinefunction(corofunc) and not getattr(corofunc, '_async_thread', False):
        coro = corofunc(*args, **kwargs)
        if not inspect.iscoroutine(coro):
            raise TypeError(f'Could not create coroutine from {corofunc}')
        return coro

    async def context():
        return corofunc(*args, **kwargs)

    try:
        context().send(None)
    except StopIteration as e:
        return e.value

def blocking(func):
    '''
    Decorator indicating that a function performs a blocking operation.
    If called from synchronous Python code, the function runs normally.
    However, if called from a coroutine, curio arranges for it to run
    in a thread.
    '''
    from . import workers

    @wraps(func)
    def wrapper(*args, **kwargs):
        if _from_coroutine():
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
    from . import workers

    @wraps(func)
    def wrapper(*args, **kwargs):
        if _from_coroutine():
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
        if _from_coroutine():
            raise SyncIOError(f'{func.__name__} may only be used in synchronous code')
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
            raise TypeError(f'{syncfunc.__name__} and async {asyncfunc.__name__} have different signatures')

        @wraps(asyncfunc)
        def wrapper(*args, **kwargs):
            if _from_coroutine():
                return asyncfunc(*args, **kwargs)
            else:
                return syncfunc(*args, **kwargs)
        wrapper._syncfunc = syncfunc
        wrapper._asyncfunc = asyncfunc
        wrapper._awaitable = True
        wrapper.__doc__ = syncfunc.__doc__ or asyncfunc.__doc__
        return wrapper
    return decorate

def asyncioable(awaitablefunc):
    '''
    Decorator that additionally allows an asyncio compatible call to
    be attached to an already awaitable function. For example:

      def spam():
          print('Synchronous spam')

      @awaitable(spam)
      def spam():
          print('Async spam (Curio)')

      @asynioable(spam)
      def spam():
          print('Async spam (asyncio)')

    This only works if Curio/Asyncio are running in different threads.
    Main use is in the implementation of UniversalQueue.
    '''
    def decorate(asyncfunc):
        @wraps(asyncfunc)
        def wrapper(*args, **kwargs):
            if _from_coroutine():
                # Check if we're Curio or not
                if curio_running():
                    return awaitablefunc._asyncfunc(*args, **kwargs)
                else:
                    return asyncfunc(*args, **kwargs)
            else:
                return awaitablefunc._syncfunc(*args, **kwargs)
        wrapper._awaitable = True
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
                         if iscoroutinefunction(val))

        for name, val in vars(cls).items():
            if name in coros and not iscoroutinefunction(val):
                raise TypeError(f'Must use async def {name}{inspect.signature(val)}')
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


def safe_generator(func):
    '''
    Deprecated. For backwards compatibility only.
    '''
    return func

class finalize(object):
    '''
    Context manager that safely finalizes an asynchronous generator.
    This might be needed if an asynchronous generator uses async functions
    in try-finally and other constructs.
    '''
    def __init__(self, aobj):
        self.aobj = aobj

    async def __aenter__(self):
        return self.aobj

    async def __aexit__(self, ty, val, tb):
        if hasattr(self.aobj, 'aclose'):
            await self.aobj.aclose()


# This context manager is used to manage the execution of async generators
# in Python 3.6.  In certain circumstances, they can't be used safely
# unless finalized properly.  This context manager installs some a hook
# for detecting lack of finalization.

@contextmanager
def asyncgen_manager():
    if hasattr(sys, 'get_asyncgen_hooks'):
        old_asyncgen_hooks = sys.get_asyncgen_hooks()
        def _fini_async_gen(agen):
            if agen.ag_frame is not None:
                raise RuntimeError("Async generator with async finalization must be wrapped by\n"
                                   "async with curio.meta.finalize(agen) as agen:\n"
                                   "    async for n in agen:\n"
                                   "         ...\n"
                                   "See PEP 533 for further discussion.")

        sys.set_asyncgen_hooks(None, _fini_async_gen)
    try:
        yield
    finally:
        if hasattr(sys, 'get_asyncgen_hooks'):
            sys.set_asyncgen_hooks(*old_asyncgen_hooks)

