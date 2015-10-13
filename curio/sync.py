# curio/sync.py
'''
Implementation of common task synchronization primitives such as
events, locks, semaphores, and condition variables. These primitives
are only safe to use in the curio framework--they are not thread safe.
'''

from .kernel import get_kernel
from types import coroutine
from collections import deque

__all__ = ['Event', 'Lock', 'Semaphore', 'BoundedSemaphore', 'Condition' ]

class Event(object):
    def __init__(self, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        self._set = False
        self._waiting = []

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
        await self._kernel.wait_on(self._waiting, 'EVENT_WAIT', timeout)
        
    def set(self):
        self._set = True
        for task in self._waiting:
             self._kernel.reschedule_task(task)
        self._waiting = []

class _LockBase(object):
    async def __aenter__(self):
        await self.acquire()
        return None

    async def __aexit__(self, exc_type, exc, tb):
        self.release()

class Lock(_LockBase):
    def __init__(self, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        self._waiting = deque()
        self._acquired = False

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    async def acquire(self, *, timeout=None):
        if self._acquired:
            await self._kernel.wait_on(self._waiting, 'LOCK_ACQUIRE', timeout)
        self._acquired = True
        return True

    def release(self):
        assert self._acquired, 'Lock not acquired'
        if self._waiting:
            self._kernel.reschedule_task(self._waiting.popleft())
        else:
            self._acquired = False

    def locked(self):
        return self._acquired

class Semaphore(_LockBase):
    def __init__(self, value=1, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        self._waiting = deque()
        self._value = value

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},value:{},waiters:{}]>'.format(res[1:-1], extra, self._value, len(self._waiting))

    async def acquire(self, *, timeout=None):
        if self._value <= 0:
            await self._kernel.wait_on(self._waiting, 'SEMA_ACQUIRE', timeout)
        else:
            self._value -= 1
        return True

    def release(self):
        if self._waiting:
            self._kernel.reschedule_task(self._waiting.popleft())
        else:
            self._value += 1
        
    def locked(self):
        return self._value == 0

class BoundedSemaphore(Semaphore):
    def __init__(self, value=1, *, kernel=None):
        self._bound_value = value
        super().__init__(value, kernel=kernel)

    def release(self):
        if self._value >= self._bound_value:
            raise ValueError('BoundedSemaphore released too many times')
        super().release()

class Condition(_LockBase):
    def __init__(self, lock=None, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        if lock is None:
            self._lock = Lock(kernel=self._kernel)
        else:
            self._lock = lock
        assert self._kernel is self._lock._kernel
        self._waiting = deque()

    def __repr__(self):
        res = super().__repr__()
        extra = 'locked' if self.locked() else 'unlocked'
        return '<{} [{},waiters:{}]>'.format(res[1:-1], extra, len(self._waiting))

    def locked(self):
        return self._lock.locked()

    async def acquire(self, *, timeout=None):
        await self._lock.acquire(timeout=timeout)

    def release(self):
        self._lock.release()

    async def wait(self, *, timeout=None):
        if not self.locked():
            raise RuntimeError("Can't wait on unacquired lock")
        self.release()
        await self._kernel.wait_on(self._waiting, 'COND_WAIT', timeout)
        await self.acquire()

    async def wait_for(self, predicate, *, timeout=None):
        while True:
            result = predicate()
            if result:
                return result
            await self.wait(timeout=timeout)

    def notify(self, n=1):
        if not self.locked():
            raise RuntimeError("Can't notify on unacquired lock")

        while self._waiting and n > 0:
            self._kernel.reschedule_task(self._waiting.popleft())
            n -= 1
        
    def notify_all(self):
        self.notify(len(self._waiting))

