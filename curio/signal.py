# curio/signal.py
#
# Signal related functionality

__all__ = ['SignalQueue', 'SignalEvent', 'enable_signals']

# -- Standard Library

import signal
import threading
from collections import defaultdict, Counter
import socket
from contextlib import contextmanager
import weakref

import logging
log = logging.getLogger(__name__)

# -- Curio

from .queue import UniversalQueue
from . import sync

# Discussion:  Signal handling.
#
# Signal handling in Python is a tricky affair with the main
# restriction that almost nothing useful can be done outside
# of the main execution thread.  Plus, the fact that signal
# handling is already inherently insane.
#
# The Curio approach to signals is to funnel signals into
# either a SignalQueue or SignalEvent object. These objects
# can be used by any combination of Curio tasks and even
# threads. 
#
# To make this work, a special _SignalHandler class operates
# in Python's main thread.  It is responsible for interacting
# with the signal module which only allows initialization
# and configuration from the main thread.   For queuing,
# the handler arranges to have signals delivered via a
# loopback socket (using signal.set_wakeup_fd).  A background
# thread watches the signal stream and redirects signals
# into queues.  For events, the _SignalHandler class also
# installs a normal signal handler that sets events.  To
# coordinate everything, _SignalHandler allows tasks, threads,
# to register/unregister their interest in various signals.
#
# This arrangement allows for a high-degree of flexibility.  For
# example, Curio allows signals to be received by different threads,
# multiple tasks, and more.


# Main signal handler class.  It tracks queues, events, and
# default signal handlers.   It is meant to be a singleton
# and basically just sits in the background. 

class _SignalHandler(object):
    _signal_queues = defaultdict(set)
    _watching = Counter()
    _default_handlers = { }
    _event_handlers = defaultdict(list)
    _lock = threading.Lock()
    _initialized = False
    _notify_sock = _wait_sock = None

    def __init__(self):
        raise RuntimeError('Do not instantiate _SignalHandler')

    # Initialize signal queues. This only gets enabled if someone
    # uses the signal queuing feature.
    @classmethod
    def _init_queuing(cls):
        if not cls._initialized:
            cls._notify_sock, cls._wait_sock = socket.socketpair()
            cls._notify_sock.setblocking(False)
            signal.set_wakeup_fd(cls._notify_sock.fileno())
            threading.Thread(target=cls._monitor, daemon=True).start()
        cls._initialized = True

    # Internal thread that watches the loopback and dispatches into queues
    @classmethod
    def _monitor(cls):
        while True:
            received_sigs = cls._wait_sock.recv(1000)
            for signo in received_sigs:
                for q in list(cls._signal_queues[signo]):
                    q.put(signo)

    # Signal handler that gets installed for handling SignalEvent
    @classmethod
    def _handler(cls, signo, frame):
        for evtref in cls._event_handlers[signo]:
            evt = evtref()
            if evt:
                evt.set()

    # Watch specified signal numbers with an queue or event
    @classmethod
    def watch(cls, signos, queue_or_evt):
        with cls._lock:
            for signo in signos:
                if cls._watching[signo] == 0:
                    cls._default_handlers[signo] = signal.signal(signo, cls._handler)
                cls._watching[signo] += 1
                if isinstance(queue_or_evt, UniversalQueue):
                    cls._signal_queues[signo].add(queue_or_evt)
                elif isinstance(queue_or_evt, SignalEvent):
                    cls._event_handlers[signo].append(weakref.ref(queue_or_evt))

    # Unwatch specified signal numbers
    @classmethod
    def unwatch(cls, signos, queue_or_evt):
        '''
        Detach a queue from a set of signal  numbers
        '''
        with cls._lock:
            for signo in signos:
                cls._watching[signo] -= 1
                if cls._watching[signo] == 0:
                    try:
                        signal.signal(signo, cls._default_handlers[signo])
                    except ValueError as e:
                        log.warning('Exception %r ignored.', e)
                if isinstance(queue_or_evt, UniversalQueue):
                    cls._signal_queues[signo].discard(queue_or_evt)
                elif isinstance(queue_or_evt, SignalEvent):
                    cls._event_handlers[signo] = [ evt for evt in cls._event_handlers[signo] if evt() ]

class SignalQueue(UniversalQueue):
    '''
    A queue for watching a given set of signals. This is a subclass of
    UniversalQueue and is safe to use in Curio or threads.
    '''

    def __init__(self, *signos, maxsize=0, **kwargs):
        assert maxsize == 0, 'SignalQueues must be unbounded'
        super().__init__(**kwargs)
        self._signos = signos
        self._watching = False
        
    def __enter__(self):
        assert not self._watching
        _SignalHandler._init_queuing()
        try:
            _SignalHandler.watch(self._signos, self)
        except Exception as e:
            log.error("Could not install signal handler.", exc_info=e)
            raise
        self._watching = True
        return self

    def __exit__(self, *args):
        _SignalHandler.unwatch(self._signos, self)
        self._watching = False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, *args):
        return self.__exit__(*args)

class SignalEvent(sync.UniversalEvent):
    def __init__(self, *signos):
        super().__init__()
        self._signos = signos
        _SignalHandler.watch(signos, self)
             
    def __del__(self):
        try:
            _SignalHandler.unwatch(self._signos, self)
        except TypeError:
            # For reasons unclear, calling signal() with valid arguments during
            # interpreter shutdown can cause a spurious TypeError. We ignore it
            pass

@contextmanager
def enable_signals(signos):
    '''
    Enable signal handling on a given set of signals.  This function
    is only needed if any part of signal handling is going to run
    in a different thread than the main thread.  Python signals can
    only be initialized in the main thread so you need to do this
    in the main thread first.
    '''
    _SignalHandler._init_queuing()
    _SignalHandler.watch(signos, None)
    try:
        yield
    finally:
        _SignalHandler.unwatch(signos, None)

@contextmanager
def ignore_signals(signos):
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
