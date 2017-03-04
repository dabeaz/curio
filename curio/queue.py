# curio/queue.py
#
# A few different queue structures.

# -- Standard library

from collections import deque
from heapq import heappush, heappop
from concurrent.futures import Future
import threading
import socket as std_socket
import asyncio

# -- Curio

from .traps import _scheduler_wait, _scheduler_wake, _future_wait
from .sched import SchedFIFO
from .errors import CurioError, CancelledError
from .meta import awaitable, asyncioable
from . import workers

__all__ = ['Queue', 'PriorityQueue', 'LifoQueue', 'UniversalQueue']


class Queue(object):
    '''
    A queue for communicating between Curio tasks. It is
    not safe for communicating between Curio and external
    threads, processes, etc.
    '''
    __slots__ = ('maxsize', '_queue', '_get_waiting',
                 '_put_waiting', '_join_waiting', '_task_count')

    def __init__(self, maxsize=0):
        self.maxsize = maxsize
        self._get_waiting = SchedFIFO()
        self._put_waiting = SchedFIFO()
        self._join_waiting = SchedFIFO()
        self._task_count = 0
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
            await _scheduler_wait(self._get_waiting, 'QUEUE_GET')

        result = self._get()

        if self._put_waiting:
            await _scheduler_wake(self._put_waiting, n=1)
        return result

    def _get(self):
        return self._queue.popleft()

    async def join(self):
        if self._task_count > 0:
            await _scheduler_wait(self._join_waiting, 'QUEUE_JOIN')

    async def put(self, item):
        while self.full():
            await _scheduler_wait(self._put_waiting, 'QUEUE_PUT')
        self._put(item)
        self._task_count += 1
        if self._get_waiting:
            await _scheduler_wake(self._get_waiting, n=1)

    def _put(self, item):
        self._queue.append(item)

    def qsize(self):
        return len(self._queue)

    async def task_done(self):
        self._task_count -= 1
        if self._task_count == 0 and self._join_waiting:
            await _scheduler_wake(self._join_waiting, n=len(self._join_waiting))


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


# UniversalQueue is one of the more interesting, and possibly,
# diabolical features of Curio.  The goal is to provide a Queue that's
# compatible with Curio, Threads, and asyncio using an identical API.
# The underlying operation is based on a combination of non-blocking
# queuing coupled with Futures.   Basically, each underlying operation 
# such as get() and put() completes immediately or else a Future
# is created for obtaining the result when it becomes available.
# This works because all of these runtime environments have a mechanism
# for waiting on a Future.   So, the general idea for each queuing 
# operation is that you first try the operation.  If it works, you're
# done.  If it doesn't work, you get a Future and you wait on it
# using whatever mechanism the runtime environment uses to do that.

class UniversalQueue(object):
    '''
    A queue for communicating between Curio and external threads,
    including foreign event loops running in different threads.
    '''

    def __init__(self, *, maxsize=0, withfd=False):
        self.maxsize = maxsize

        # The actual queue of items
        self._queue = deque()

        # A queue of Futures representing getters
        self._getters = deque()

        # A queue of Futures representing putters
        self._putters = deque()

        # Internal synchronization.  
        # 
        # This is one of the only thread locks that's used inside
        # Curio and used from async code.  It's use here is avoid
        # a race condition on a few attributes.  It is only held
        # briefly, and never in a situation where a blocking operation
        # would take place with the lock held.
        self._mutex = threading.Lock()
        self._all_tasks_done = threading.Condition(self._mutex)
        self._unfinished_tasks = 0

        # Optional socket for monitoring on an external event loop.
        # The fileno() method below returns a socket that becomes
        # readable once an item is available on the queue.
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

    def _get_complete(self):
        if self._get_sock:
            try:
                self._get_sock.recv(1)
            except BlockingIOError:
                pass
        self._put_notify()
            
    def _get(self):
        fut = item = None
        with self._mutex:
            # Critical section never blocks.
            if not self._queue or self._getters:
                fut = Future()
                fut.add_done_callback(lambda f: self._get_complete() if not f.cancelled() else None)
                self._getters.append(fut)
            else:
                item = self._queue.popleft()
                self._get_complete()
        return item, fut

    # Synchronous queue get.   
    def get(self):
        item, fut = self._get()
        if fut:
            item = fut.result()
        return item

    # Asynchronous queue get (Curio) 
    @awaitable(get)
    async def get(self):
        item, fut = self._get()
        if fut:
            try:
                await _future_wait(fut)
                item = fut.result()
            except CancelledError as e:
                # If we're cancelled, but the future completes successfully anyways,
                # we must arrange for the item to go back onto the queue.  Note:
                # the Curio kernel cancels futures when _future_wait() is cancelled.
                fut.add_done_callback(lambda f: self._put(f.result(), True) if not f.cancelled() else None)
                raise
        return item

    # Asynchronous queue get (Asyncio)
    @asyncioable(get)
    async def get(self):
        item, fut = self._get()
        if fut:
            await asyncio.wait_for(asyncio.wrap_future(fut), None)
            item = fut.result()
        return item

    # Wake any waiting putters
    def _put_notify(self):
        while self._putters:
            putter = self._putters.popleft()
            if not putter.cancelled():
                putter.set_result(None)
                break

    # Put something on the queue or return a Future that must
    # be waited on before retrying.
    def _put(self, item, requeue=False):
        with self._mutex:
            # Critical section never blocks.
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

    # Synchronous put. For threads.
    def put(self, item):
        while True:
            fut = self._put(item)
            if not fut:
                break
            fut.result()

    # Asynchronous put. For Curio
    @awaitable(put)
    async def put(self, item):
        while True:
            fut = self._put(item)
            if not fut:
                break
            try:
                await _future_wait(fut)
            except CancelledError:
                # If we're cancelled, but the future completes, it means that the getter alerted
                # a task that space was available, but the alert is lost.  We renotify any waiters.
                fut.add_done_callback(lambda fut: self._put_notify() if not fut.cancelled() else None)
                raise

    # Asynchronous put. For Asyncio.
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

