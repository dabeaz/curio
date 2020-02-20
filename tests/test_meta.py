from curio import meta
from curio import *
from functools import partial
import pytest
import sys
import inspect

def test_iscoroutinefunc():
    async def spam(x, y):
        pass

    assert meta.iscoroutinefunction(partial(spam, 1))

def test_instantiate_coroutine():
    async def coro(x, y):
        pass

    def func(x, y):
        pass

    c = meta.instantiate_coroutine(coro(2,3))
    assert inspect.iscoroutine(c)

    d = meta.instantiate_coroutine(coro, 2, 3)
    assert inspect.iscoroutine(d)

    with pytest.raises(TypeError):
        meta.instantiate_coroutine(func(2,3))

    with pytest.raises(TypeError):
        meta.instantiate_coroutine(func, 2, 3)


def test_bad_awaitable():
    def spam(x, y):
        pass

    with pytest.raises(TypeError):
        @meta.awaitable(spam)
        def spam(x, y, z):
            pass


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

if sys.version_info >= (3,7):
    import contextlib
    def test_asynccontextmanager(kernel):
        results = []
        @contextlib.asynccontextmanager
        async def manager():
             try:
                 yield (await coro())
             finally:
                 await cleanup()

        async def coro():
            results.append('coro')
            return 'result'

        async def cleanup():
            results.append('cleanup')

        async def main():
            async with manager() as r:
                results.append(r)

        kernel.run(main)
        assert results == ['coro', 'result', 'cleanup']


    def test_missing_asynccontextmanager(kernel):
        results = []
        async def manager():
             try:
                 yield (await coro())
             finally:
                 await cleanup()

        async def coro():
            results.append('coro')
            return 'result'

        async def cleanup():
            results.append('cleanup')

        async def main():
             async for x in manager():
                  break

        kernel.run(main)
        assert results == ['coro']
