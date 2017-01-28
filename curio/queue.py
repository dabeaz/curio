# curio/queue.py
#
# Implementation of a queue object that can be used to communicate
# between tasks.  This is only safe to use within curio. It is not
# thread-safe.


from collections import deque
from heapq import heappush, heappop
import threading
import queue as thread_queue
import weakref

from .traps import _wait_on_ksync, _reschedule_tasks, _ksync_reschedule_function
from .kernel import KSyncQueue
from .errors import CurioError, CancelledError, TaskTimeout
from .meta import awaitable
from . import workers
from .task import spawn, timeout_after
from . import sync

__all__ = ['Queue', 'PriorityQueue', 'LifoQueue', 'UniversalQueue']


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
        must_wait = bool(self._get_waiting)
        while must_wait or self.empty():
            must_wait = False
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
        while self.full():
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


class UniversalQueue(object):
    '''
    A queue that's compatible with both Curio tasks and external threads.
    Can be used to send data in both directions.
    '''

    _sentinel = object()

    def __init__(self, queue=None, maxsize=0):
        self._tqueue = queue if queue else thread_queue.Queue(maxsize=maxsize)
        self._local = threading.local()

    async def shutdown(self):
        if hasattr(self._local, 'get_task'):
            await self._local.get_task.cancel()
            del self._local.get_task
            del self._local.cqueue
            del self._local.num_getting

    # A daemon task that pulls items from the thread queue and queues
    # them on the async side.  The purpose of having this task is to
    # shield the process of pulling items over to async from cancellation.
    # Without care, cancellation would cause items to be lost
    async def _get_helper(self):
        tqueue = self._tqueue
        cqueue = self._local.cqueue
        num_getting = self._local.num_getting

        # Discussion: We break all internel references to ourself and create
        # a weak reference instead.  This allows the queue to be garbage
        # collected when it's no longer in use.  We'll periodically check
        # to see if it went away.  If so, there's no point in having the
        # helper task stick around. 
        self = weakref.ref(self)
        try:
            while True:
                try:
                    await timeout_after(0.1, num_getting.acquire())
                except TaskTimeout:
                    # If the queue is no longer around, we're done
                    if not self():
                        return
                    continue
                item = await workers.run_in_thread(tqueue.get, call_on_cancel=lambda fut: tqueue.put(fut.result))
                await cqueue.put(item)
        except CancelledError:
            while not cqueue.empty():
                item = await cqueue.get()
                await workers.run_in_thread(tqueue.put, item)
            raise

    def get(self):
        return self._tqueue.get()

    @awaitable(get)
    async def get(self):
        if not hasattr(self._local, 'get_task'):
            self._local.cqueue = Queue()
            self._local.num_getting = sync.Semaphore(0)
            self._local.get_task = await spawn(self._get_helper(), daemon=True)

        if self._local.cqueue.empty() or self._local.num_getting.locked():
            await self._local.num_getting.release()
        try:
            item = await self._local.cqueue.get()
            return item
        except CancelledError:
            if not self._local.num_getting.locked():
                await self._local.num_getting.acquire()
            raise

    def put(self, item):
        self._tqueue.put(item)

    @awaitable(put)
    async def put(self, item):
        await workers.block_in_thread(self._tqueue.put, item)
    
    def task_done(self):
        self._tqueue.task_done()

    @awaitable(task_done)
    async def task_done(self):
        await workers.run_in_thread(self._tqueue.task_done)

    def join(self):
        self._tqueue.join()

    @awaitable(join)
    async def join(self):
        await workers.block_in_thread(self._tqueue.join)

    def __getattr__(self, name):
        return getattr(self._tqueue, name)
