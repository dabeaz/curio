# curio/queue.py
#
# Implementation of a queue object that can be used to communicate
# between tasks.  This is only safe to use within curio. It is not
# thread-safe.


from collections import deque
from heapq import heappush, heappop
from concurrent.futures import Future
import threading
import queue as thread_queue
import weakref
import socket as std_socket
import asyncio

from .traps import _wait_on_ksync, _reschedule_tasks, _ksync_reschedule_function, _future_wait
from .kernel import KSyncQueue
from .errors import CurioError, CancelledError, TaskTimeout
from .meta import awaitable, asyncioable
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
    '''
    def __init__(self, *, maxsize=0, withfd=False):
        self.maxsize = maxsize

        # The actual queue of items
        self._queue = deque()

        # A queue of Futures representing getters
        self._getters = deque()

        # A queue of Futures representing putters
        self._putters = deque()

        # Internal synchronization
        self._mutex = threading.Lock()
        self._all_tasks_done = threading.Condition(self._mutex)
        self._unfinished_tasks = 0

        # Optional socket that allows for external event loop monitoring
        if withfd:
            self._put_sock, self._get_sock = std_socket.socketpair()
            self._put_sock.setblocking(False)
            self._get_sock.setblocking(False)
        else:
            self._put_sock = self._get_sock = None

    def __del__(self):
        if self._put_sock:
            self._put_sock.close()
            self._get_sock.close()

    async def shutdown(self):
        pass

    def fileno(self):
        assert self._get_sock, "Queue not created with I/O polling enabled"
        return self._get_sock.fileno()

    def _put_send(self):
        if self._put_sock:
            try:
                self._put_sock.put(b'\x01')
            except BlockingIOError:
                pass

    def empty(self):
        return not bool(self._queue)

    def full(self):
        return False

    def qsize(self):
        return len(self._queue)

    # Discussion:  This method implements a special form of a nonblocking
    # queue get() where it either returns an item from the queue right away,
    # or it returns a Future that can be used to obtain the item later.
    # Any runtime environment that has the means to wait on a Future
    # (threads, curio, asyncio, etc.) can then block to complete the get.
    # Future is from the concurrent.futures module.

    def _get_complete(self):
        if self._get_sock:
            try:
                self._get_sock.recv(1)
            except BlockingIOError:
                pass

        # If there was something waiting to put, wake it
        if self._putters:
            putter = self._putters.popleft()
            putter.set_result(None)
            
    def _get(self):
        fut = item = None
        with self._mutex:
            # Critical section never blocks.
            if not self._queue:
                fut = Future()
                fut.add_done_callback(lambda f: self._get_complete() if not f.cancelled() else None)
                self._getters.append(fut)
            else:
                item = self._queue.popleft()
                self._get_complete()
        return item, fut

    # Synchronous queue get.   
    def get_sync(self):
        item, fut = self._get()
        if fut:
            item = fut.result()
        return item

    # Asynchronous queue get. 
    @awaitable(get_sync)
    async def get(self):
        item, fut = self._get()
        if fut:
            try:
                await _future_wait(fut)
                item = fut.result()
            except CancelledError as e:
                fut.add_done_callback(lambda f: self._put(f.result(), True) if not f.cancelled() else None)
                raise
        return item

    @asyncioable(get)
    async def get(self):
        item, fut = self._get()
        if fut:
            await asyncio.wait_for(asyncio.wrap_future(fut), None)
            item = fut.result()
        return item

    # A non-blocking queue put().  It either puts something on the queue
    # or it returns a Future that must be waited on before retrying.
    def _put(self, item, requeue=False):
        with self._mutex:
            if self.maxsize > 0 and len(self._queue) >= self.maxsize:
                fut = Future()
                self._putters.append(fut)
                return fut

            if requeue:
                self._queue.appendleft(item)
            else:
                self._queue.append(item)
                self._unfinished_tasks += 1
                self._put_send()

            # If there are any waiters. Wake one of them and pop a queue item
            while self._getters:
                getter = self._getters.popleft()
                if getter.cancelled():
                    continue
                getter.set_result(self._queue.popleft())
                break

    def put_sync(self, item):
        while True:
            fut = self._put(item)
            if not fut:
                break
            fut.result()

    @awaitable(put_sync)
    async def put(self, item):
        while True:
            fut = self._put(item)
            if not fut:
                break
            await _future_wait(fut)

    @asyncioable(put)
    async def put(self, item):
        while True:
            fut = self._put(item)
            if not fut:
                break
            await asyncio.wait_for(asyncio.wrap_future(fut), None)

    def task_done_sync(self):
        with self._all_tasks_done:
            self._unfinished_tasks -= 1
            assert self._unfinished_tasks >= 0, 'task_done called too many times'
            if self._unfinished_tasks <= 0:
                self._all_tasks_done.notify_all()

    @awaitable(task_done_sync)
    async def task_done(self):
        self.task_done_sync()

    def join_sync(self):
        with self._all_tasks_done:
            while self._unfinished_tasks:
                self._all_tasks_done.wait()

    @awaitable(join_sync)
    async def join(self):
        await workers.block_in_thread(self.join_sync)

    @asyncioable(join)
    async def join(self):
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, self.join_sync)
