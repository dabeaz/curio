# curio/sync.py
'''
Implementation of common task synchronization primitives such as
events, locks, semaphores, and condition variables. These primitives
are only safe to use in the curio framework--they are not thread safe.
'''

from .kernel import wait_on_queue, reschedule_tasks, kqueue
from types import coroutine

__all__ = ['Event', 'Lock', 'Semaphore', 'BoundedSemaphore', 'Condition' ]

class Event(object):
    def __init__(self):
        self._set = False
        self._waiting = kqueue()

    def __repr__(self):
        res = super().__repr__()
        extra = 'set' if self._set else 'unset'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    def is_set(self):
        return self._set

    def clear(self):
        self._set = False

    async def wait(self, *, timeout=None):
        if self._set:
            return
        await wait_on_queue(self._waiting, 'EVENT_WAIT', timeout)

    async def set(self):
        self._set = True
        await reschedule_tasks(self._waiting, len(self._waiting))

class _LockBase(object):
    async def __aenter__(self):
        await self.acquire()
        return None

    async def __aexit__(self, exc_type, exc, tb):
        await self.release()

class Lock(_LockBase):
    def __init__(self):
        self._kernel = None
        self._waiting = kqueue()
        self._acquired = False

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    async def acquire(self, *, timeout=None):
        if self._acquired:
            await wait_on_queue(self._waiting, 'LOCK_ACQUIRE', timeout)
        self._acquired = True
        return True

    async def release(self):
        assert self._acquired, 'Lock not acquired'
        if self._waiting:
            await reschedule_tasks(self._waiting, n=1)
        else:
            self._acquired = False

    def locked(self):
        return self._acquired

class Semaphore(_LockBase):
    def __init__(self, value=1):
        self._kernel = None
        self._waiting = kqueue()
        self._value = value

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},value:{},waiters:{}]>'.format(res[1:-1], extra, self._value, len(self._waiting))

    async def acquire(self, *, timeout=None):
        if self._value <= 0:
            await wait_on_queue(self._waiting, 'SEMA_ACQUIRE', timeout)
        else:
            self._value -= 1
        return True

    async def release(self):
        if self._waiting:
            await reschedule_tasks(self._waiting, n=1)
        else:
            self._value += 1
        
    def locked(self):
        return self._value == 0

class BoundedSemaphore(Semaphore):
    def __init__(self, value=1):
        self._bound_value = value
        super().__init__(value)

    async def release(self):
        if self._value >= self._bound_value:
            raise ValueError('BoundedSemaphore released too many times')
        await super().release()

class Condition(_LockBase):
    def __init__(self, lock=None):
        self._kernel = None
        if lock is None:
            self._lock = Lock()
        else:
            self._lock = lock
        self._waiting = kqueue()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    def locked(self):
        return self._lock.locked()

    async def acquire(self, *, timeout=None):
        await self._lock.acquire(timeout=timeout)

    async def release(self):
        await self._lock.release()

    async def wait(self, *, timeout=None):
        if not self.locked():
            raise RuntimeError("Can't wait on unacquired lock")
        await self.release()
        try:
            await wait_on_queue(self._waiting, 'COND_WAIT', timeout)
        finally:
            await self.acquire()

    async def wait_for(self, predicate, *, timeout=None):
        while True:
            result = predicate()
            if result:
                return result
            await self.wait(timeout=timeout)

    async def notify(self, n=1):
        if not self.locked():
            raise RuntimeError("Can't notify on unacquired lock")
        await reschedule_tasks(self._waiting, n=n)

    async def notify_all(self):
        await self.notify(len(self._waiting))

