# curio/queue.py
#
# Implementation of a queue object that can be used to communicate
# between tasks.  This is only safe to use within curio. It is not
# thread-safe.


from collections import deque
from heapq import heappush, heappop
import threading
import queue as thread_queue

from .traps import _wait_on_ksync, _reschedule_tasks, _ksync_reschedule_function
from .kernel import KSyncQueue
from .errors import CurioError
from .meta import awaitable
from . import workers
from .task import spawn
from . import sync

__all__ = ['Queue', 'PriorityQueue', 'LifoQueue', 'EpicQueue']


class Full(CurioError):
    pass


class Queue(object):
    __slots__ = ('maxsize', '_queue', '_get_waiting',
                 '_put_waiting', '_join_waiting', '_task_count',
                 '_get_reschedule_func')

    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._get_waiting = KSyncQueue()
        self._put_waiting = KSyncQueue()
        self._join_waiting = KSyncQueue()
        self._task_count = 0
        self._get_reschedule_func = None

        self._queue = self._init_internal_queue()

    def __repr__(self):
        res = super().__repr__()
        return '<%s, len=%d>' % (res[1:-1], len(self._queue))

    def _init_internal_queue(self):
        return deque()

    def empty(self):
        return not self._queue

    def full(self):
        return self.maxsize and len(self._queue) == self.maxsize

    async def get(self):
        if self._get_waiting or self.empty():
            if self._get_reschedule_func is None:
                self._get_reschedule_func = await _ksync_reschedule_function(self._get_waiting)
            await _wait_on_ksync(self._get_waiting, 'QUEUE_GET')
        result = self._get()
        if self._put_waiting:
            await _reschedule_tasks(self._put_waiting, n=1)
        return result

    def _get(self):
        return self._queue.popleft()

    async def join(self):
        if self._task_count > 0:
            await _wait_on_ksync(self._join_waiting, 'QUEUE_JOIN')

    def put(self, item):
        if self.full():
            raise Full('queue full')
        self._put(item)
        self._task_count += 1
        if self._get_waiting:
            self._get_reschedule_func(1)

    @awaitable(put)
    async def put(self, item):
        if self.full():
            await _wait_on_ksync(self._put_waiting, 'QUEUE_PUT')
        self._put(item)
        self._task_count += 1
        if self._get_waiting:
            await _reschedule_tasks(self._get_waiting, n=1)

    def _put(self, item):
        self._queue.append(item)

    def qsize(self):
        return len(self._queue)

    async def task_done(self):
        self._task_count -= 1
        if self._task_count == 0 and self._join_waiting:
            await _reschedule_tasks(self._join_waiting, n=len(self._join_waiting))


class PriorityQueue(Queue):
    '''
    A Queue that outputs an item with the lowest priority first

    Items have to be orderable objects
    '''

    def _init_internal_queue(self):
        return []

    def _put(self, item):
        heappush(self._queue, item)

    def _get(self):
        return heappop(self._queue)


class LifoQueue(Queue):
    '''
    Last In First Out queue

    Retrieves most recently added items first
    '''

    def _init_internal_queue(self):
        return []

    def _put(self, item):
        self._queue.append(item)

    def _get(self):
        return self._queue.pop()


class EpicQueue(object):
    '''
    The name says it all.
    '''
    def __init__(self, queue=None, maxsize=0):
        self._tqueue = queue if queue else thread_queue.Queue(maxsize=maxsize)
        self._get_sema = sync.Semaphore(1)
        self._put_sema = sync.Semaphore(1)
        self._join_sema = sync.Semaphore(1)
        self._all_tasks_done = threading.Condition()
        self._unfinished_tasks = 0

    def put(self, item):
        with self._all_tasks_done:
            self._unfinished_tasks += 1

        self._tqueue.put(item)

    @awaitable(put)
    async def put(self, item):
        async with self._put_sema:
            async with sync.abide(self._all_tasks_done):
                self._unfinished_tasks += 1
            await workers.run_in_thread(self._tqueue.put, item)

    def get(self):
        return self._tqueue.get()

    @awaitable(get)
    async def get(self):
        async with self._get_sema:
            return await workers.run_in_thread(self._tqueue.get)
    
    def _sync_task_done(self):
        with self._all_tasks_done:
            self._unfinished_tasks -= 1
            if self._unfinished_tasks == 0:
                self._all_tasks_done.notify_all()

    @awaitable(_sync_task_done)
    async def task_done(self):
        await workers.run_in_thread(self._sync_task_done)

    async def _join_worker(self):
        w = workers.ThreadWorker()
        try:
            await w.apply(self._join_sync)
            await self._joining.set()
        finally:
            self._joining = None
            self._join_task = None
            w.shutdown()

    def _join_sync(self):
        with self._all_tasks_done:
            while self._unfinished_tasks:
                self._all_tasks_done.wait()

    @awaitable(_join_sync)
    async def join(self):
        await workers.run_in_thread(self._join_sync)

    def __getattr__(self, name):
        return getattr(self._tqueue, name)

    # Footnote: all of the code in this class is experimental.
    # It's probably an epically bad idea.  YOLO.
