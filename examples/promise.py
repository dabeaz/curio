# Example of implementing a Promise class using
# built-in synchronization primitives.

from curio import Event

class Promise:
    def __init__(self):
        self._event = Event()
        self._data = None
        self._exception = None

    def __repr__(self):
        res = super().__repr__()
        if self.is_set():
            extra = repr(self._exception) if self._exception else repr(self._data)
        else:
            extra = 'unset'
        return f'<{res[1:-1]} [{extra}]>'

    def is_set(self):
        '''Return `True` if the promise is set'''
        return self._event.is_set()

    def clear(self):
        '''Clear the promise'''
        self._data = None
        self._exception = None
        self._event.clear()

    async def set(self, data):
        '''Set the promise. Wake all waiting tasks (if any).'''
        self._data = data
        await self._event.set()

    async def get(self):
        '''Wait for the promise to be set, and return the data.

        If an exception was set, it will be raised.'''
        await self._event.wait()

        if self._exception is not None:
            raise self._exception

        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._exception = exc
            await self._event.set()

            return True

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
        await producer_task.join()

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
            
        await producer_task.join()

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
