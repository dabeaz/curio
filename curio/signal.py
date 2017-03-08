# curio/signal.py
#
# Signal sets and signal related functionality

__all__ = ['SignalSet']

# -- Standard Library

from contextlib import contextmanager
import signal

# -- Curio

from . import thread
from .queue import UniversalQueue

class SignalSet(object):

    def __init__(self, *signos):
        self.signos = signos            # List of all signal numbers being tracked
        self.pending = UniversalQueue() # Queue of incoming signals
        self.watching = False
        self.previous_handlers = { }

    # Signal handler. Puts the signal number on the pending queue
    def _handler(self, signo, frame):
        self.pending.put(signo)
        if callable(self.previous_handlers[signo]):
            self.previous_handlers[signo](signo, frame)

    async def __aenter__(self):
        assert not self.watching
        for signo in self.signos:
            self.previous_handlers[signo] = signal.signal(signo, self._handler)
        self.watching = True
        return self

    async def __aexit__(self, *args):
        for signo in self.signos:
            signal.signal(signo, self.previous_handlers[signo])
        self.watching = False

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

    async def wait(self):
        '''
        Wait for any signals. Return a set of all signals received.
        '''
        if not self.watching:
            async with self:
                return await self.wait()

        return await self.pending.get()

    @contextmanager
    def ignore(self):
        '''
        Context manager. Temporarily ignores all signals in the signal set.
        '''
        try:
            orig_signals = [(signo, signal.signal(signo, signal.SIG_IGN)) for signo in self.signos]
            yield
        finally:
            for signo, handler in orig_signals:
                signal.signal(signo, handler)
