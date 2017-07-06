# test_asyncio.py
#
# Test the asyncio bridge

from curio import *
from curio.bridge import AsyncioLoop
import asyncio
import pytest

def test_asyncio_simple(kernel):
    async def aio_child(x, y):
        return x + y

    async def main():
        async with AsyncioLoop() as loop:
            r = await loop.run_asyncio(aio_child, 2, 3)
            assert r == 5

            r2 = await loop.run_asyncio(aio_child(2, 5))
            assert r2 == 7

            with pytest.raises(TypeError):
                await loop.run_asyncio(aio_child, 2, '3')
                
    kernel.run(main)

def test_asyncio_wrapper(kernel):
    loop = AsyncioLoop()

    @asyncio_coroutine(loop)
    async def aio_child(x, y):
        print("AIO_CHILD:", x,  y)
        return x ** y

    async def main():
        result = await aio_child(2, 2)
        assert result == 4

        # CRITICAL. Must shut down the loop
        await loop.shutdown()

    kernel.run(main)
