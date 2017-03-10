# curio/sync.py
#
# Implementation of common task synchronization primitives such as
# events, locks, semaphores, and condition variables. These primitives
# are only safe to use in the curio framework--they are not thread safe.
#
# The general implementation strategy is based on task scheduling.
# For example, if a task needs to wait on a lock, it goes to sleep.
# When a task releases a lock, it wakes a sleeping task. 
#
# Internally, there are a few kernel-level sychronization primitives
# used to coordinate tasks (KSyncQueue, and KSyncEvent).  KSyncQueue
# is used for queue-based coordination.  KSyncEvent is used for
# barrier synchronization.  The _scheduler_wait() and _scheduler_wake()
# traps are used to coordinate synchronization with the underlying Kernel.


__all__ = ['Event', 'UniversalEvent', 'Lock', 'RLock', 'Semaphore', 'BoundedSemaphore', 'Condition', 'abide']

# -- Standard library

import threading

# -- Curio

from .traps import _scheduler_wait, _scheduler_wake
from .sched import SchedFIFO, SchedBarrier
from . import workers
from .task import current_task
from .meta import awaitable, iscoroutinefunction
from . import thread

class Event(object):
    __slots__ = ('_set', '_waiting')

    def __init__(self):
        self._set = False
        self._waiting = SchedBarrier()

    def __repr__(self):
        res = super().__repr__()
        extra = 'set' if self._set else 'unset'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    def is_set(self):
        return self._set

    def clear(self):
        self._set = False

    async def wait(self):
        if self._set:
            return

        await _scheduler_wait(self._waiting, 'EVENT_WAIT')

    async def set(self):
        self._set = True
        await _scheduler_wake(self._waiting, len(self._waiting))

class UniversalEvent(object):
    '''
    An event that's safe to use from Curio and threads.
    '''
    def __init__(self):
        self._evt = threading.Event()
        
    def is_set(self):
        return self._evt.is_set()

    def wait(self):
        self._evt.wait()

    @awaitable(wait)
    async def wait(self):
        await workers.block_in_thread(self._evt.wait)

    def set(self):
        self._evt.set()

    @awaitable(set)
    async def set(self):
        self._evt.set()

class _LockBase(object):

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.release()

    def __enter__(self):
        return thread.AWAIT(self.__aenter__())

    def __exit__(self, *args):
        return thread.AWAIT(self.__aexit__(*args))

class Lock(_LockBase):

    __slots__ = ('_acquired', '_waiting')

    def __init__(self):
        self._acquired = False
        self._waiting = SchedFIFO()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    async def acquire(self):
        if self._acquired:
            await _scheduler_wait(self._waiting, 'LOCK_ACQUIRE')
        self._acquired = True
        return True

    async def release(self):
        assert self._acquired, 'Lock not acquired'
        if self._waiting:
            await _scheduler_wake(self._waiting, n=1)
        else:
            self._acquired = False

    def locked(self):
        return self._acquired


class RLock(_LockBase):

    __slots__ = ('_lock', '_owner', '_count')

    def __init__(self):
        self._lock = Lock()
        self._owner = None
        self._count = 0

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},recursion:{}]>'.format(res[1:-1], extra, self._count)

    async def acquire(self):

        me = await current_task()

        if self._owner is not me:

            await self._lock.acquire()
            self._owner = me
        self._count += 1
        return True

    async def release(self):
        """Release the lock

        If the acquisitions count reaches 0, release the underlying
        lock. Only the owner of the lock can release it.

        Note, that due to the asynchronous nature of the _LocBase.__aexit__(),
        this lock could be acquired by another waiter before the current owner
        executes the first line after the context, which might surprise a user:

        >>>lck = RLock()
        >>>async def foo():
        >>>    async with lck:
        >>>        print('locked')
        >>>        # since the actual call to lck.release() will be done before
        >>>        # exiting the context, some other waiter coroutine could be
        >>>        # scheduled to run before we actually exit the context
        >>>    print('This line might be executed after'
        >>>          'another coroutine acquires this lock')

        """
        if not await current_task() is self._owner:
            raise RuntimeError('RLock can only be released by the owner')
        if not self.locked():
            raise RuntimeError('RLock is not locked')
        self._count -= 1
        if self._count == 0:
            await self._lock.release()

    def locked(self):
        return self._count > 0


class Semaphore(_LockBase):

    __slots__ = ('_value', '_waiting')

    def __init__(self, value=1):
        self._value = value
        self._waiting = SchedFIFO()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},value:{},waiters:{}]>'.format(
            res[1:-1], extra, self._value, len(self._waiting))

    async def acquire(self):
        if self._value <= 0:
            await _scheduler_wait(self._waiting, 'SEMA_ACQUIRE')
        else:
            self._value -= 1
        return True

    async def release(self):
        if self._waiting:
            await _scheduler_wake(self._waiting, n=1)
        else:
            self._value += 1

    def locked(self):
        return self._value == 0


class BoundedSemaphore(Semaphore):

    __slots__ = ('_bound_value',)

    def __init__(self, value=1):
        self._bound_value = value
        super().__init__(value)

    async def release(self):
        if self._value >= self._bound_value:
            raise ValueError('BoundedSemaphore released too many times')
        await super().release()


class Condition(_LockBase):

    __slots__ = ('_lock', '_waiting')

    def __init__(self, lock=None):
        if lock is None:
            self._lock = Lock()
        else:
            self._lock = lock
        self._waiting = SchedFIFO()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    def locked(self):
        return self._lock.locked()

    async def acquire(self):
        await self._lock.acquire()

    async def release(self):
        await self._lock.release()

    async def wait(self):
        if not self.locked():
            raise RuntimeError("Can't wait on unacquired lock")
        await self.release()
        try:
            await _scheduler_wait(self._waiting, 'COND_WAIT')
        finally:
            await self.acquire()

    async def wait_for(self, predicate):
        while True:
            result = predicate()
            if result:
                return result
            await self.wait()

    async def notify(self, n=1):
        if not self.locked():
            raise RuntimeError("Can't notify on unacquired lock")
        await _scheduler_wake(self._waiting, n=n)

    async def notify_all(self):
        await self.notify(len(self._waiting))

# Class that adapts a synchronous context-manager to an asynchronous manager

class _contextadapt_basic(object):
    def __init__(self, manager):
        self._manager = manager

    async def __aenter__(self):
        return await workers.block_in_thread(self._manager.__enter__,
                                             call_on_cancel=lambda fut: self._manager.__exit__(None, None, None))

    async def __aexit__(self, *args):
        return await workers.run_in_thread(self._manager.__exit__, *args)

# Adapt a synchronous context-manager to an asynchronous manager, but 
# with a reserved backing thread (the same thread used for the duration of the 
# context manager)

class _contextadapt_reserve(object):
    def __init__(self, manager):
        self._manager = manager

    async def __aenter__(self):
        self._worker = await workers.reserve_thread_worker()
        self._result = await self._worker.apply(self._manager.__enter__,
                                                call_on_cancel=lambda fut: self._manager.__exit__(None, None, None))
        return self

    async def __aexit__(self, *args):
        try:
            await self._worker.apply(self._manager.__exit__, args)
        finally:
            await self._worker.release()

    def __getattr__(self, name):
        item = getattr(self._manager, name)
        if callable(item):
            async def call(*args, **kwargs):
                return await self._worker.apply(item, args, kwargs)
            return call
        else:
            return item

def abide(op, *args, reserve_thread=False):
    '''
    Make curio abide by the execution requirements of an external
    synchronization primitive such as a Lock, Semaphore, or Condition
    variable from the threading library.

    sync should be an object supporting the synchronous context-management
    protocol.  It is adapted so that the __enter__() and __exit__()
    methods execute in a background thread.  Cancellation is handled
    gracefully.

    The reserve_thread flag, if given exposes the background thread for further
    use.  This may be required for certain kinds of synchronization
    primitives such as condition variables:

        cond = threading.Condition()

        async with abide(cond, reserve_thread=True) as c:
            await c.wait()   # Uses same thread as used to acquire the lock
            ...

    The main use of this function is in code that wants to safely
    synchronize curio with threads and processes. For example, if you
    write code this like:

        async with abide(lck):
            statements

    The code will work correctly if lck is an async lock defined by curio or
    a foreign lock defined by the threading or multiprocessing modules.

    abide() can be used with simple functions and methods.  For example
    events,

        evt = threading.Event()
        ...
        await abide(evt.wait)

    In this case, the operation is executed using block_in_thread().
    '''

    # If op is already a coroutine function, return it unmodified
    if iscoroutinefunction(op):
        return op(*args)

    # If the object is already an asynchronous context manager, return it unmodified
    if hasattr(op, '__aexit__'):
        return op

    if hasattr(op, '__exit__'):
        return _contextadapt_reserve(op) if reserve_thread else _contextadapt_basic(op)

    # Object must be callable at least
    if not callable(op):
        raise TypeError('Must supply a callable')

    return workers.block_in_thread(op, *args)
