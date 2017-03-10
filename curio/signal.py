# curio/signal.py
#
# Signal sets and signal related functionality

__all__ = ['SignalQueue', 'SignalEvent', 'SignalSet', 'EnableSignals', 'enable_signal_queues']

# -- Standard Library

import signal
import threading
from collections import defaultdict, Counter
import socket
from functools import partial
from contextlib import contextmanager


import logging
log = logging.getLogger(__name__)

# -- Curio

from .queue import UniversalQueue
from .meta import awaitable
from . import sync

# Discussion:  Signal handling.
#
# Signal handling in Python is a tricky affair with the main
# restriction that almost nothing useful can be done outside
# of the main execution thread.  Plus, the fact that signal
# handling is already insane.
#
# The Curio approach to signals is to have signals delivered
# on a loopback socket (using signal.set_wakeup_fd) which is
# constantly monitored by a background thread.  This thread
# takes received signals and pushes them into queues subscribed
# to various signal numbers.  These queues can be registered
# and unregistered by various Curio tasks, threads, and other
# parts of the system.   This arrangement allows for a high-degree
# of flexibility.  For example, Curio allows signals to be 
# received by different threads.  

_handler = None

class _SignalHandler(object):
    def __init__(self):
        assert _handler is None, 'Only one _SignalHandler may be created'
        self.signal_queues = defaultdict(set)
        self.watching = Counter()
        self.default_handlers = { }
        self.lock = threading.Lock()

        self._notify_sock, self._wait_sock = socket.socketpair()
        self._notify_sock.setblocking(False)
        signal.set_wakeup_fd(self._notify_sock.fileno())
        threading.Thread(target=self._monitor, daemon=True).start()
        
    def _monitor(self):
        '''
        Internal thread that watches for signals and dispatches them to queues
        '''
        while True:
            received_sigs = self._wait_sock.recv(1000)
            for signo in received_sigs:
                for q in list(self.signal_queues[signo]):
                    q.put(signo)

    def watch(self, signos, queue):
        '''
        Attach a queue to a set of signal numbers
        '''
        with self.lock:
            for signo in signos:
                if self.watching[signo] == 0:
                    self.default_handlers[signo] = signal.signal(signo, lambda signo, frame: None)
                self.watching[signo] += 1
                if queue:
                    self.signal_queues[signo].add(queue)

    def unwatch(self, signos, queue):
        '''
        Detach a queue from a set of signal  numbers
        '''
        with self.lock:
            for signo in signos:
                self.watching[signo] -= 1
                if self.watching[signo] == 0:
                    try:
                        signal.signal(signo, self.default_handlers[signo])
                    except ValueError as e:
                        log.warning('Exception %r ignored.', e)
                if queue:
                    self.signal_queues[signo].discard(queue)

def _init_handler():
    global _handler
    if _handler is None:
        _handler = _SignalHandler()

class SignalQueue(UniversalQueue):
    '''
    A queue for watching a given set of signals. This is a subclass of
    UniversalQueue and is safe to use in Curio or threads.
    '''

    def __init__(self, signos, maxsize=0, **kwargs):
        assert maxsize == 0, 'SignalQueues must be unbounded'
        super().__init__(**kwargs)
        self._signos = signos
        self._watching = False
        
    def __enter__(self):
        assert not self._watching
        _init_handler()
        try:
            _handler.watch(self._signos, self)
        except Exception as e:
            log.error("Could not install signal handler.", exc_info=e)
            raise
        self._watching = True
        return self

    def __exit__(self, *args):
        _handler.unwatch(self._signos, self)
        self._watching = False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)

class SignalEvent(sync.UniversalEvent):
    def __init__(self, signo):
        super().__init__()
        self._signo = signo
        self._default = signal.signal(signo, self)

    def __call__(self, signo, frame):
        self.set()
        if isinstance(self._default, SignalEvent):
            self._default(signo, frame)
             
    def __del__(self):
        signal.signal(self._signo, self._default)

@contextmanager
def enable_signal_queues(signos):
    '''
    Enable signal queuing on a given set of signals.  This function
    is only needed if any part of signal handling is going to run
    in a different thread than the main thread.  Python signals can
    only be initialized in the main thread so you need to do this
    in the main thread first.
    '''
    _init_handler()
    _handler.watch(signos, None)
    try:
        yield
    finally:
        _handler.unwatch(signos, None)

@contextmanager
def ignore_signals(*signos):
    '''
    Temporarily ignore a set of signals.  This is only safe to use
    from Python's main thread.
    '''
    orig_signals = [(signo, signal.signal(signo, signal.SIG_IGN)) for signo in self.signos]
    try:
        yield
    finally:
        for signo, handler in orig_signals:
            signal.signal(signo, handler)



class SignalSet(object):

    def __init__(self, *signos, noqueue=False):
        self._signos = signos
        self._noqueue = noqueue
        self._watching = False


    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)

    def __enter__(self):
        global _handler
        assert not self._watching
        self._pending = UniversalQueue() if not self._noqueue else None
        try:
            if _handler is None:
                _handler = _SignalHandler()
            _handler.watch(self._signos, self._pending)
            self._watching = True
            return self
        except Exception as e:
            # Be loud about failures on setup. If error reporting is
            # delayed, an uncaught signal will often cause Python to
            # terminate immediately with no useful diagnostic.
            log.error("Could not install signal handler.", exc_info=e)
            raise

    def __exit__(self, *args):
        _handler.unwatch(self._signos, self._pending)
        self._pending = None
        self._watching = False

    def signals_pending(self):
        '''
        Returns the number of signals pending.  
        '''
        return self._pending.qsize()

    def wait(self):
        '''
        Wait for any signals. Returns the signal number of first received signal
        '''
        assert not self._noqueue, "Can't wait on a non-queuing signal set"
        if not self._watching:
            with self:
                return self.wait()
        return self._pending.get()

    @awaitable(wait)
    async def wait(self):
        assert not self._noqueue, "Can't wait on a non-queuing signal set"
        if not self._watching:
            async with self:
                return await self.wait()

        return await self._pending.get()

    @contextmanager
    def ignore(self):
        '''
        Context manager. Temporarily ignores all signals in the signal set.
        This can only be used in Python's main thread.  
        '''
        try:
            orig_signals = [(signo, signal.signal(signo, signal.SIG_IGN)) for signo in self.signos]
            yield
        finally:
            for signo, handler in orig_signals:
                signal.signal(signo, handler)


# A special signal set that can be used to enable signals, but 
# doesn't perform any queuing of its own.  Mainly this is used
# if you're going to be running Curio in a different thread.
# Since signal handlers can only be initialized in Python's main
# thread, you'd have to set up handling there first before 
# launching the rest of the application.  Do this:
#
# with EnableSignals(signal.SIGUSR1, signal.SIGINT):
#     threading.Thread(target=run, args=(main,)).start()
#

EnableSignals = partial(SignalSet, noqueue=True)
