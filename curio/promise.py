from .sync import Event

__all__ = ['Promise']

class Promise:
    def __init__(self):
        self._event = Event()
        self._data = None
        self._exception = None

    async def set(self, data):
        self._data = data
        await self._event.set()

    async def get(self):
        await self._event.wait()

        if self._exception is not None:
            raise self._exception

        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._exception = exc
        await self._event.set()

        return True
