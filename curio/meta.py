# curio/meta.py
#     ___
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die. No seriously.
#

__all__ = [
    'iscoroutinefunction', 'finalize', 'blocking', 'cpubound',
    'awaitable', 'asyncioable', 'sync_only', 'AsyncABC',
    'AsyncObject', 'curio_running'
 ]

# -- Standard Library

from sys import _getframe
import inspect
from functools import wraps, partial
from abc import ABCMeta, abstractmethod
import dis
import asyncio
import threading

# -- Curio

from .errors import SyncIOError


_locals = threading.local()
def set_running_flag(flag):
    '''
    Set a flag that indicates whether or not Curio is running in the
    current thread.
    '''
    _locals.running = flag


def curio_running():
    '''
    Return a flag that indicates whether or not Curio is running in the current thread.
    '''
    return getattr(_locals, 'running', False)


# Some flags defined in Include/code.h
_CO_NESTED = 0x0010
_CO_GENERATOR = 0x0020
_CO_COROUTINE = 0x0080
_CO_ITERABLE_COROUTINE = 0x0100
_CO_ASYNC_GENERATOR = 0x0200
_CO_FROM_COROUTINE = _CO_COROUTINE | _CO_ITERABLE_COROUTINE | _CO_ASYNC_GENERATOR

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
    return inspect.iscoroutinefunction(func)

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
            raise SyncIOError('{} may only be used in synchronous code'.format(func.__name__))
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
            if _from_coroutine():
                return asyncfunc(*args, **kwargs)
            else:
                return syncfunc(*args, **kwargs)
        wrapper._syncfunc = syncfunc
        wrapper._asyncfunc = asyncfunc
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


# Dictionary that tracks the "safe" status of async generators with 
# respect to asynchronous finalization.  Normally this is automatically
# determined by looking at the code of async generators.  It can
# be overridden using the @safe_generator decorator below. 

_safe_async_generators = { }      # { code_objects: bool }

def safe_generator(func):
    _safe_async_generators[func.__code__] = True
    return func


class finalize(object):
    '''
    Context manager that safely finalizes an asynchronous generator.
    This might be needed if an asynchronous generator uses async functions
    in try-finally and other constructs.
    '''

    _finalized = set()

    def __init__(self, aobj):
        self.aobj = aobj

    async def __aenter__(self):
        self._finalized.add(self.aobj)
        return self.aobj

    async def __aexit__(self, ty, val, tb):
        if hasattr(self.aobj, 'aclose'):
            await self.aobj.aclose()
        self._finalized.discard(self.aobj)

    @classmethod
    def is_finalized(cls, aobj):
        return aobj in cls._finalized

def is_safe_generator(agen):
    '''
    Examine the code of an async generator to see if it appears
    unsafe with respect to async finalization.  A generator
    is unsafe if it utilizes any of the following constructs:

    1. Use of async-code in a finally block

       try:
           yield v
       finally:
           await coro()

    2. Use of yield inside an async context manager

       async with m:
           ...
           yield v
           ...

    3. Use of async-code in try-except

       try:
           yield v
       except Exception:
           await coro()
    '''
    if agen.ag_code in _safe_async_generators:
        return True

    def _is_unsafe_block(instr, end_offset=-1):
        is_generator = False
        in_final = False
        is_unsafe = False
        for op in instr:
            if op.offset == end_offset:
                in_final = True
            if op.opname == 'YIELD_VALUE':
                is_generator = True
            if op.opname == 'END_FINALLY':
                return (is_generator, is_unsafe)
            if op.opname in {'SETUP_FINALLY', 'SETUP_EXCEPT', 'SETUP_ASYNC_WITH'}:
                is_g, is_u = _is_unsafe_block(instr, op.argval)
                is_generator |= is_g
                is_unsafe |= is_u
            if op.opname == 'YIELD_FROM' and is_generator and in_final:
                is_unsafe = True
        return (is_generator, is_unsafe)

    if not _is_unsafe_block(dis.get_instructions(agen.ag_code))[1]:
        _safe_async_generators[agen.ag_code] = True
        return True
    else:
        return False

        
