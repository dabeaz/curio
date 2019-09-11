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
