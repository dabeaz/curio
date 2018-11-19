# test_asyncgen.py

import pytest
from curio import *
from curio.meta import finalize, awaitable, AsyncABC, abstractmethod


# Test to make sure a simple async generator runs
def test_simple_agen(kernel):
    async def countdown(n):
        while n > 0:
            yield n
            n -= 1

    async def main():
        nums = [ n async for n in countdown(5) ]
        assert nums == [5, 4, 3, 2, 1]

    kernel.run(main())

# Test to make sure a simple finally clause executes
def test_simple_agen_final(kernel):
    results = []
    async def countdown(n):
        try:
            while n > 0:
                yield n
                n -= 1
        finally:
            results.append('done')

    async def main():
        nums = [ n async for n in countdown(5) ]
        assert nums == [5, 4, 3, 2, 1]

    kernel.run(main())
    assert results == ['done']

# Make sure application of finalize() works
def test_agen_final_finalize(kernel):
    async def countdown(n):
        try:
            while n > 0:
                yield n
                n -= 1
        finally:
            await sleep(0.0)

    async def main():
        async with finalize(countdown(5)) as c:
            nums = [n async for n in c]
            assert nums == [5, 4, 3, 2, 1]

    kernel.run(main())

# Make sure a try-except without asyncs works
def test_agen_except_ok(kernel):
    async def countdown(n):
        while n > 0:
             try:
                 yield n
             except Exception:
                 pass
             n -= 1

    async def main():
        nums = [n async for n in countdown(5) ]
        assert nums == [5, 4, 3, 2, 1]

    kernel.run(main())

# Test to make sure a simple async generator runs
def test_awaitable_agen(kernel):
    async def countdown(n):
        while n > 0:
             try:
                 yield n
             except Exception:
                 pass
             n -= 1

    def add(x, y):
        return x + y

    @awaitable(add)
    async def add(x, y):
        return x + y

    async def main():
        nums = [ await add(n,n) async for n in countdown(5) ]
        assert nums == [10, 8, 6, 4, 2]

    kernel.run(main())

    nums = [ add(n,n) for n in range(5,0,-1) ]
    assert nums == [10, 8, 6, 4, 2]

def test_asyncapc_generator_function():
    class Parent(AsyncABC):
        @abstractmethod
        async def foo(self):
            raise NotImplementedError

    class Child(Parent):
        async def foo(self):
            yield 1
            return
