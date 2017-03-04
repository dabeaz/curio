from .sync import Event

__all__ = ['Promise']

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
        return '<{} [{}]>'.format(res[1:-1], extra)

    def is_set(self):
        return self._event.is_set()

    def clear(self):
        self._data = None
        self._exception = None
        self._event.clear()

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
