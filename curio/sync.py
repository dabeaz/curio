# curio/sync.py
'''
Implementation of common task synchronization primitives such as events,
locks, semaphores, condition variables, and queues.  These primitives
are only safe to use in the curio framework--they are not thread safe.
'''

from .kernel import get_kernel
from types import coroutine
from collections import deque

__all__ = ['Event', 'Lock', 'Semaphore', 'BoundedSemaphore', 'Condition', 'Queue']

class Event(object):
    def __init__(self, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        self._set = False
        self._waiting = []

    def is_set(self):
        return self._set

    def clear(self):
        self._set = False

    async def wait(self):
        if self._set:
            return
        await self._kernel.wait_on(self._waiting, 'EVENT_WAIT')
        
    def set(self):
        for task in self._waiting:
            self._kernel.reschedule_task(task)

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

    async def acquire(self):
        if self._acquired:
            await self._kernel.wait_on(self._waiting, 'LOCK_ACQUIRE')
        self._acquired = True
        return True

    def release(self):
        assert self._acquired, 'Lock not acquired'
        if self._waiting:
            self._kernel.reschedule_task(self._waiting.popleft())

    def locked(self):
        return self._acquired

class Semaphore(_LockBase):
    def __init__(self, value=1, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        self._waiting = deque()
        self._value = value

    async def acquire(self):
        if self._value <= 0:
            await self._kernel.wait_on(self._waiting, 'SEMA_ACQUIRE')
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
    pass

class Condition(object):
    pass

class Queue(object):
    pass

