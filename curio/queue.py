# curio/queue.py

'''
Implementation of a queue object that can be used to communicate
between tasks.  This is only safe to use within curio. It is not
thread-safe.
'''

from .kernel import wait_on_queue, reschedule_tasks, kqueue
from collections import deque

__all__ = [ 'Queue' ]

class Queue(object):
    __slots__ = ('maxsize', '_queue', '_get_waiting', '_put_waiting', '_join_waiting', '_task_count')
    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._queue = deque()
        self._get_waiting = kqueue()
        self._put_waiting = kqueue()
        self._join_waiting = kqueue()
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
            await reschedule_tasks(self._put_waiting, n=1)
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
            await reschedule_tasks(self._get_waiting, n=1)

    def qsize(self):
        return len(self._queue)

    async def task_done(self):
        self._task_count -= 1
        if self._task_count == 0 and self._join_waiting:
            await reschedule_tasks(self._join_waiting, n=len(self._join_waiting))
