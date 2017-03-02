from .sync import Condition

__all__ = ['Promise']

class Promise:
    def __init__(self):
        self._done = False
        self._data = None
        self._exception = None

        self._condition = Condition()

    async def set(self, data):
        async with self._condition:
            self._data = data
            self._done = True

            await self._condition.notify()

    async def get(self):
        async with self._condition:
            while not self._done:
                await self._condition.wait()

            if self._exception is not None:
                raise self._exception

            return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        async with self._condition:
            self._done = True
            self._exception = exc
            await self._condition.notify()

        return True
