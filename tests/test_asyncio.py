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
            with pytest.raises(TypeError):
                await loop.run_asyncio(aio_child, 2, '3')
                
    kernel.run(main)
