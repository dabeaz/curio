# curio/file.py
#
# (WORK IN PROGRESS)
#
# Let's talk about files for a moment.  Suppose you're in a coroutine
# and you start using things like the built-in open() function:
#
#     async def coro():
#         f = open(somefile, 'r')
#         data = f.read()
#         ...
#
# Yes, this will "work", but who knows what's actually going to happen
# on that open() call and associated read().  If it's on a disk, the
# whole program might lock up for a few milliseconds (aka. "an
# eternity") doing a disk seek.  While that happens, your whole
# coroutine based server is going to grind to a screeching halt.  This
# is bad--especially if a lot of coroutines start doing it all at
# once.
#
# Knowing how to handle this is sort of an tricky question. 
# Traditional files don't really support "async" in the usual way a
# socket might.    However, one thing is for certain--if files
# are going to be handled in a sane way, they also have to have
# an async interface.
#
# This file does just that by providing an async-compatible aopen()
# call.  You use it the same way you use open() and a normal file:
#
#    async def coro():
#        f = await aopen(somefile, 'r')
#        data = await f.read()
#        ...
#
# If you want to use context managers or iteration, make sure you
# use the asynchronous versions:
#
#    async def coro():
#        async with aopen(somefile, 'r') as f:
#            async for line in f:
#                ...
#
# An "async" file is sufficiently file-like to be passed as a file
# to traditional synchronous code.  However, be aware that doing
# so may cause all sorts of bad things to happen.  You'll probably
# want to run such code in a separate thread or by putting data
# into a io.StringIO or io.BytesIO instance instead.

__all__ = ['aopen', 'anext']

from .meta import blocking, sync_only
from .workers import run_in_thread

class AsyncFile(object):
    def __init__(self, file):
        self._file = file

    @blocking
    def read(self, *args, **kwargs):
        return self._file.read(*args, **kwargs)

    @blocking
    def readlines(self, *args, **kwargs):
        return self._file.readlines(*args, **kwargs)

    @blocking
    def write(self, *args, **kwargs):
        return self._file.write(*args, **kwargs)

    @blocking
    def writelines(self, *args, **kwargs):
        return self._file.writelines(*args, **kwargs)

    @blocking
    def flush(self):
        return self._file.flush()

    @blocking
    def close(self):
        return self._file.close()

    @blocking
    def truncate(self, *args, **kwargs):
        return self._file.truncate(*args, **kwargs)

    @sync_only
    def __iter__(self):
        return self._file.__iter__()

    @sync_only
    def __next__(self):
        return self._file.__next__()

    @sync_only
    def __enter__(self):
        return self._file.__enter__()

    def __exit__(self, *args):
        return self._file.__exit__(*args)

    def __aiter__(self):
        return self
        
    async def __anext__(self):
        data = await run_in_thread(next, self._file, None)
        if data is None:
            raise StopAsyncIteration
        return data
        
    def __getattr__(self, name):
        return getattr(self._file, name)

@blocking
def aopen(*args, **kwargs):
    '''
    Async version of the builtin open() function that returns an async-compatible
    file object.  Takes the same arguments.  Returns a wrapped file in which
    blocking I/O operations must be awaited.
    '''
    f = open(*args, **kwargs)
    return AsyncFile(f)

async def anext(f, sentinel=object):
    '''
    Async version of the builtin next() function that advances an async iterator.
    Sometimes used to skip a single line in files.
    '''    
    try:
        return await f.__anext__()
    except StopAsyncIteration:
        if sentinel is not object:
            return sentinel
        else:
            raise

