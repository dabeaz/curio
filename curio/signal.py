# curio/signal.py
#
# Signal sets and signal related functionality

__all__ = ['SignalSet']

# -- Standard Library

from contextlib import contextmanager
from collections import deque, defaultdict
import signal
import socket

# -- Curio

from .traps import _read_wait, _get_kernel
from . import thread
from . import sync
from .task import spawn


# SignalHandler class takes care of managing signals. 
# For now, uses a notification file.  However, I have other
# plans.... stay tuned. Bwhahahahaha!!!

class SignalHandler(object):
    def __init__(self, kernel):
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._notify_sock.setblocking(False)
        self._wait_sock.setblocking(False)
        
        self._signal_sets = defaultdict(list)
        self._default_signals = { }
        _old_fd = signal.set_wakeup_fd(self._notify_sock.fileno())
        assert _old_fd < 0, 'Signals already initialized %d' % old_fd
        kernel.signal_handler = self
        kernel._call_at_shutdown(self.shutdown)

    def shutdown(self):
        self._notify_sock.close()
        self._wait_sock.close()
        signal.set_wakeup_fd(-1)

    async def signal_monitor(self):
        while True:
            await _read_wait(self._wait_sock)
            data = self._wait_sock.recv(1000)
            sigs = (n for n in data if n in self._signal_sets)
            for signo in sigs:
                for sigset in self._signal_sets[signo]:
                    sigset.pending.append(signo)
                    await sigset.waiting.set()

    def sigwatch(self, sigset):
        for signo in sigset.signos:
            if not self._signal_sets[signo]:
                self._default_signals[signo] = signal.signal(signo, lambda signo, frame: None)
            self._signal_sets[signo].append(sigset)

    def sigunwatch(self, sigset):
        for signo in sigset.signos:
            if sigset in self._signal_sets[signo]:
                self._signal_sets[signo].remove(sigset)
            
            if not self._signal_sets[signo]:
                signal.signal(signo, self._default_signals[signo])
                del self._signal_sets[signo]

class SignalSet(object):

    def __init__(self, *signos):
        self.signos = signos          # List of all signal numbers being tracked
        self.pending = deque()        # Pending signals received
        self.waiting = sync.Event()   # Event for waiting tasks
        self.handler = None           # Handler watching signals right now

    async def __aenter__(self):
        assert not self.handler
        kernel = await _get_kernel()
        if not hasattr(kernel, 'signal_handler'):
            handler = SignalHandler(kernel)
            await spawn(handler.signal_monitor, daemon=True)
        else:
            handler = kernel.signal_handler
        handler.sigwatch(self)
        self.handler = handler

        return self

    async def __aexit__(self, *args):
        self.handler.sigunwatch(self)
        self.handler = None

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

    async def wait(self):
        '''
        Wait for a single signal from the signal set to arrive.
        '''
        if not self.handler:
            async with self:
                return await self.wait()

        while True:
            if self.pending:
                return signal.Signals(self.pending.popleft())
            self.waiting.clear()
            await self.waiting.wait()

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
