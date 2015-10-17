# curio/queue.py

'''
Implementation of a queue object that can be used to communicate
between tasks.  This is only safe to use within curio. It is not
thread-safe.
'''

from .kernel import get_kernel, wait_on_queue
from collections import deque

__all__ = [ 'Queue', 'QueueEmpty', 'QueueFull' ]

class QueueEmpty(Exception):
    pass

class QueueFull(Exception):
    pass

class Queue(object):
    def __init__(self, maxsize=0, *, kernel=None):
        self._kernel = kernel if kernel else get_kernel()
        self.maxsize = maxsize
        self._queue = deque()
        self._get_waiting = deque()
        self._put_waiting = deque()
        self._join_waiting = []
        self._task_count = 0

    def empty(self):
        return not self._queue

    def full(self):
        return self.maxsize and len(self._queue) == self.maxsize

    async def get(self, *, timeout=None):
        if self.empty():
            await wait_on_queue(self._get_waiting, 'QUEUE_GET', timeout)
        result = self._queue.popleft()
        if self._put_waiting:
            self._kernel.reschedule_task(self._put_waiting.popleft())
        return result

    def get_nowait(self):
        if self.empty():
            raise QueueEmpty()
        result = self._queue.popleft()
        if self._put_waiting:
            self._kernel.reschedule_task(self._put_waiting.popleft())
        return result

    async def join(self, *, timeout=None):
        if self._task_count > 0:
            await wait_on_queue(self._join_waiting, 'QUEUE_JOIN', timeout)

    async def put(self, item, *, timeout=None):
        if self.full():
            await wait_on_queue(self._put_waiting, 'QUEUE_PUT', timeout)
        self._queue.append(item)
        self._task_count += 1
        if self._get_waiting:
            self._kernel.reschedule_task(self._get_waiting.popleft())

    def put_nowait(self, item):
        if self.full():
            raise QueueFull()
        self._queue.append(item)
        self._task_count += 1
        if self._get_waiting:
            self._kernel.reschedule_task(self._get_waiting.popleft())

    def qsize(self):
        return len(self._queue)

    def task_done(self):
        self._task_count -= 1
        if self._task_count == 0:
            for task in self._join_waiting:
                self._kernel.reschedule_task(task)
            self._join_waiting = []
