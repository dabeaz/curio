# curio/meta.py
#     ___
#     \./      DANGER:  This module implements some experimental
#  .--.O.--.            metaprogramming techniques involving async/await.
#   \/   \/             If you use it, you might die.
#

__all__ = [ 'blocking', 'cpubound' ]

import sys
import inspect
from functools import wraps
from . import workers

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
