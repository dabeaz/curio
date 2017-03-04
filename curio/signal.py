# curio/signal.py
#
# Signal sets and signal related functionality

__all__ = ['SignalSet']

# -- Standard Library

from contextlib import contextmanager
from collections import deque
import signal

# -- Curio

from .traps import *
from . import thread


class SignalSet(object):

    def __init__(self, *signos):
        self.signos = signos          # List of all signal numbers being tracked
        self.pending = deque()        # Pending signals received
        self.waiting = None           # Task waiting for the signals (if any)
        self.watching = False         # Are the signals being watched right now?

    async def __aenter__(self):
        assert not self.watching
        await _sigwatch(self)
        self.watching = True
        return self

    async def __aexit__(self, *args):
        await _sigunwatch(self)
        self.watching = False

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

    async def wait(self):
        '''
        Wait for a single signal from the signal set to arrive.
        '''
        if not self.watching:
            async with self:
                return await self.wait()

        while True:
            if self.pending:
                return signal.Signals(self.pending.popleft())
            await _sigwait(self)

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
