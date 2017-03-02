import curio
import pytest

from curio import Promise

async def consumer(promise):
    return await promise.get()

def test_promise(kernel):
    async def producer(promise):
        await promise.set(42)

    async def main():
        promise = Promise()
        producer_task = await curio.spawn(producer(promise))

        assert 42 == await consumer(promise)

    kernel.run(main())

def test_promise_exception(kernel):
    async def exception_producer(promise):
        async with promise:
            raise RuntimeError()

    async def main():
        promise = Promise()
        producer_task = await curio.spawn(exception_producer(promise))

        with pytest.raises(RuntimeError):
            await consumer(promise)

    kernel.run(main())
