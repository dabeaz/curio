# curio/sync.py
#
# Implementation of common task synchronization primitives such as
# events, locks, semaphores, and condition variables. These primitives
# are only safe to use in the curio framework--they are not thread safe
# unless otherwise indicated.
#
# The general implementation strategy is based on task scheduling.
# For example, if a task needs to wait on a lock, it goes to sleep on
# a queue.  When a task releases a lock, it wakes a sleeping task.
#
# Internally, task scheduling is provided by the SchedFIFO and
# SchedBarrier classes in sched.py.  These are never manipulated
# directly.  Instead the _scheduler_wait() and _scheduler_wake()
# functions must be used.

__all__ = ['Event', 'UniversalEvent', 'Lock', 'RLock', 'Semaphore', 'Condition' ]

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

    def clear(self):
        self._evt.clear()

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

# Base class for all synchronization primitives that operate as context managers.

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
        if not self.locked():
            raise RuntimeError('RLock is not locked')
        if not await current_task() is self._owner:
            raise RuntimeError('RLock can only be released by the owner')
        self._count -= 1
        if self._count == 0:
            await self._lock.release()
            self._owner = None

    def locked(self):
        return self._count > 0


class Semaphore(_LockBase):

    def __init__(self, value=1):
        self._value = value
        self._waiting = SchedFIFO()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},value:{},waiters:{}]>'.format(
            res[1:-1], extra, self._value, len(self._waiting))

    @property
    def value(self):
        return self._value

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


class Condition(_LockBase):

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

