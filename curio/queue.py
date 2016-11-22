# curio/queue.py
#
# Implementation of a queue object that can be used to communicate
# between tasks.  This is only safe to use within curio. It is not
# thread-safe.


from collections import deque
from heapq import heappush, heappop
import threading
import queue as thread_queue

from .traps import _wait_on_queue, _reschedule_tasks, _queue_reschedule_function
from .kernel import kqueue
from .errors import CurioError
from .meta import awaitable
from . import workers
from .task import spawn
from . import sync

__all__ = ['Queue', 'PriorityQueue', 'LifoQueue']


class Full(CurioError):
    pass


class Queue(object):
    __slots__ = ('maxsize', '_queue', '_get_waiting',
                 '_put_waiting', '_join_waiting', '_task_count',
                 '_get_reschedule_func')

    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._get_waiting = kqueue()
        self._put_waiting = kqueue()
        self._join_waiting = kqueue()
        self._task_count = 0
        self._get_reschedule_func = None

        self._queue = self._init_internal_queue()

    def _init_internal_queue(self):
        return deque()

    def empty(self):
        return not self._queue

    def full(self):
        return self.maxsize and len(self._queue) == self.maxsize

    async def get(self):
        if self.empty():
            if self._get_reschedule_func is None:
                self._get_reschedule_func = await _queue_reschedule_function(self._get_waiting)
            await _wait_on_queue(self._get_waiting, 'QUEUE_GET')
        result = self._get()
        if self._put_waiting:
            await _reschedule_tasks(self._put_waiting, n=1)
        return result

    def _get(self):
        return self._queue.popleft()

    async def join(self):
        if self._task_count > 0:
            await _wait_on_queue(self._join_waiting, 'QUEUE_JOIN')

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
            await _wait_on_queue(self._put_waiting, 'QUEUE_PUT')
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
    def __init__(self, queue=None):
        self._tqueue = queue if queue else thread_queue.Queue()
        self._aqueue = Queue()
        self._get_task = None
        self._put_task = None
        self._join_task = None
        self._joining = None
        self._all_tasks_done = threading.Condition()
        self._unfinished_tasks = 0

    def __del__(self):
        assert self._get_task is None, 'Queue %r not properly terminated' % self

    async def shutdown(self):
        if self._get_task:
            await self._get_task.cancel()
            
        if self._put_task:
            await self._put_task.cancel()

        if self._join_task:
            await self._join_task.cancel()

    async def _put_worker(self):
        w = workers.ThreadWorker()
        try:
            while True:
                item = await self._aqueue.get()
                await w.apply(self._tqueue.put, (item,))
        finally:
            w.shutdown()
            self._put_task = None

    def put(self, item):
        if self._tqueue.full():
            raise Full('queue full')

        with self._all_tasks_done:
            self._unfinished_tasks += 1

        self._tqueue.put(item)

    @awaitable(put)
    async def put(self, item):
        if self._put_task is None:
            self._put_task = await spawn(self._put_worker())

        if self._tqueue.full():
            raise Full('queue full')

        async with sync.abide(self._all_tasks_done):
            self._unfinished_tasks += 1

        await self._aqueue.put(item)

    async def _get_worker(self):
        w = workers.ThreadWorker()
        try:
            while True:
                item = await w.apply(self._tqueue.get)
                await self._aqueue.put(item)
        finally:
            w.shutdown()
            self._get_task = None

    def get(self):
        return self._tqueue.get()

    @awaitable(get)
    async def get(self):
        if self._get_task is None:
            self._get_task = await spawn(self._get_worker())
        return (await self._aqueue.get())

    def _sync_task_done(self):
        with self._all_tasks_done:
            self._unfinished_tasks -= 1
            if self._unfinished_tasks == 0:
                self._all_tasks_done.notify_all()

    @awaitable(_sync_task_done)
    async def task_done(self):
         await sync.abide(self._sync_task_done)

    async def _join_worker(self):
        w = workers.WorkerThread()
        try:
            await w.apply(self._join)
            await self._joining.set()
        finally:
            self._joining = None
            self._join_task = None
            w.shutdown()

    def join(self):
        with self._all_tasks_done:
            while self._unfinished_tasks:
                self._all_tasks_done.wait()

    @awaitable(join)
    async def join(self):
        async with sync.abide(self._all_tasks_done):
            if self._unfinished_tasks > 0:
                if self._join_task is None:
                    self._joining = sync.Event()
                    self._join_task = await spawn(self._join_worker())

        if self._joining:
            await self._joining.wait()

    # Footnote: all of the code in this class is experimental.
    # It's probably an epically bad idea.  YOLO. 
