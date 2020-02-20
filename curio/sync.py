# curio/sync.py
#
# Implementation of common task synchronization primitives such as
# events, locks, semaphores, and condition variables. These primitives
# are only safe to use within Curio--they are not thread safe
# unless otherwise indicated.
#
# The general implementation strategy is based on task scheduling.
# For example, if a task needs to wait on a lock, it goes to sleep on
# a queue.  When a task releases a lock, it wakes a sleeping task.
# Task scheduling is provided by the SchedFIFO and SchedBarrier classes in sched.py

__all__ = ['Event', 'UniversalEvent', 'Lock', 'RLock', 'Semaphore', 'Condition' ]

# -- Standard library

import threading
from concurrent.futures import Future
import asyncio

# -- Curio

from .sched import SchedFIFO, SchedBarrier
from . import workers
from .task import current_task
from .meta import awaitable, asyncioable, iscoroutinefunction
from . import thread
from .traps import _future_wait

class Event(object):

    def __init__(self):
        self._set = False
        self._waiting = SchedBarrier()

    def __repr__(self):
        res = super().__repr__()
        extra = 'set' if self._set else 'unset'
        return f'<{res[1:-1]} [{extra},waiters:{len(self._waiting)}]>'

    def is_set(self):
        return self._set

    def clear(self):
        self._set = False

    async def wait(self):
        if self._set:
            return
        await self._waiting.suspend('EVENT_WAIT')

    async def set(self):
        self._set = True
        await self._waiting.wake()

class UniversalEvent(object):
    '''
    An event that's safe to use from Curio and threads.
    '''
    def __init__(self):
        self._fut = Future()
        self._set = False

    def __repr__(self):
        res = super().__repr__()
        extra = 'set' if self._set else 'unset'
        return f'<{res[1:-1]} [{extra}]>'

    def is_set(self):
        return self._set

    def clear(self):
        self._fut = Future()
        self._set = False

    def wait(self):
        self._fut.result()

    @awaitable(wait)
    async def wait(self):
        if not self._set:
            await _future_wait(self._fut)

    @asyncioable(wait)
    async def wait(self):
        if not self._set:
            await asyncio.wrap_future(self._fut)

    def set(self):
        self._set = True
        self._fut.set_result(True)

    @awaitable(set)
    async def set(self):
        self._set = True
        self._fut.set_result(True)

    @asyncioable(set)
    async def set(self):
        self._set = True
        self._fut.set_result(True)

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
        return f'<{res[1:-1]} [{extra},waiters:{len(self._waiting)}]>'

    async def acquire(self):
        if self._acquired:
            await self._waiting.suspend('LOCK_ACQUIRE')
        self._acquired = True
        return True

    async def release(self):
        assert self._acquired, 'Lock not acquired'
        if self._waiting:
            await self._waiting.wake()
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
        return f'<{res[1:-1]} [{extra},recursion:{self._count}]>'

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
        return f'<{res[1:-1]} [{extra},value:{self._value},waiters:{len(self._waiting)}]>'

    @property
    def value(self):
        return self._value

    async def acquire(self):
        if self._value <= 0:
            await self._waiting.suspend('SEMA_ACQUIRE')
        else:
            self._value -= 1
        return True

    async def release(self):
        if self._waiting:
            await self._waiting.wake()
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
        return f'<{res[1:-1]} [{extra},waiters:{len(self._waiting)}]>'

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
            await self._waiting.suspend('COND_WAIT')
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
        await self._waiting.wake(n)

    async def notify_all(self):
        await self.notify(len(self._waiting))




