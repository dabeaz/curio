from curio import meta
from curio import *
import time
from functools import partial
import pytest

def test_blocking(kernel):
    @meta.blocking
    def func():
        return 1

    async def main():
         r = await func()
         assert r == 1

    assert func() == 1

    kernel.run(main)

@meta.cpubound
def cpufunc():
    return 1

def test_cpubound(kernel):
    async def main():
         r = await cpufunc()
         assert r == 1

    assert cpufunc() == 1
    kernel.run(main)

def test_iscoroutinefunc():
    async def spam(x, y):
        pass

    assert meta.iscoroutinefunction(partial(spam, 1))

def test_async_instance(kernel):

    class AsyncSpam(meta.AsyncObject):
        async def __init__(self, x):
            await sleep(0)
            self.x = x

    async def main():
        s = await AsyncSpam(37)
        assert s.x == 37
        
    kernel.run(main)

def test_bad_async_instance():

    with pytest.raises(TypeError):
        class AsyncSpam(meta.AsyncObject):
            def __init__(self, x):
                self.x = x


def test_async_abc():
    class AsyncSpam(meta.AsyncABC):
        async def spam(self):
            pass
    
    with pytest.raises(TypeError):
        class Child(AsyncSpam):
            def spam(self):
                pass

    class Child2(AsyncSpam):
        async def spam(self):
            pass


def test_sync_only(kernel):
    @meta.sync_only
    def func():
        return 1

    async def main():
         with pytest.raises(SyncIOError):
             r = func()

    assert func() == 1

    kernel.run(main)

def test_bad_awaitable():
    def spam(x, y):
        pass

    with pytest.raises(TypeError):
        @meta.awaitable(spam)
        def spam(x, y, z):
            pass


from functools import partial

def test_awaitable_partial(kernel):
    def func(x, y, z):
        assert False

    @meta.awaitable(func)
    async def func(x, y, z):
        assert x == 1
        assert y == 2
        assert z == 3
        return True
        
    async def main():
        assert await func(1, 2, 3)
        assert await ignore_after(1, func(1,2,3))
        assert await ignore_after(1, func, 1, 2, 3)
        assert await ignore_after(1, partial(func, 1, 2), 3)
        assert await ignore_after(1, partial(func, z=3), 1, 2)
        assert await ignore_after(1, partial(partial(func, 1), 2), 3)

        # Try spawns
        t = await spawn(func(1,2,3))
        assert await t.join()

        t = await spawn(func, 1, 2, 3)
        assert await t.join()

        t = await spawn(partial(func, 1, 2), 3)
        assert await t.join()

        t = await spawn(partial(func, z=3), 1, 2)
        assert await t.join()

        t = await spawn(partial(partial(func, 1), 2), 3)
        assert await t.join()


    kernel.run(main)
    kernel.run(func, 1, 2, 3)
    kernel.run(partial(func, 1, 2), 3)
    kernel.run(partial(func, z=3), 1, 2)


    
