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
        assert not promise.is_set()

        producer_task = await curio.spawn(producer(promise))

        assert 42 == await consumer(promise)
        assert promise.is_set()

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

def test_promise_no_exception(kernel):
    async def main():
        promise = Promise()
        async with promise:
            pass
        assert not promise.is_set()

    kernel.run(main())

def test_promise_internals(kernel):
    async def main():
        promise = Promise()
        assert not promise.is_set()
        assert repr(promise).endswith('[unset]>')

        await promise.set(42)

        assert promise.is_set()
        assert promise._data == 42
        assert promise._exception is None
        assert repr(promise).endswith('[42]>')

        promise.clear()

        assert not promise.is_set()
        assert promise._data is None
        assert promise._exception is None
        assert repr(promise).endswith('[unset]>')

        async with promise:
            raise RuntimeError()

        assert promise.is_set()
        assert promise._data is None
        assert isinstance(promise._exception, RuntimeError)
        assert repr(promise).endswith('[RuntimeError()]>')

        promise.clear()

        assert not promise.is_set()
        assert promise._data is None
        assert promise._exception is None
        assert repr(promise).endswith('[unset]>')

    kernel.run(main())
