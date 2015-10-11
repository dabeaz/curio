# sched.py

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque
import socket
from types import coroutine
import heapq
import time

class Scheduler(object):
    def __init__(self):
        self._selector = DefaultSelector()
        self._ready = deque()
        self._sleeping = []
        self.njobs = 0
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self._ready.append(self._wait_task())

    # Callback that causes the scheduler to wake
    def _wake(self, task):
        self._ready.append(task)
        self._notify_sock.send(b'x')

    # Internal task for ready notifications
    async def _wait_task(self):
         while True:
             data = await self.sock_recv(self._wait_sock, 100)

    # Traps
    def trap_read_wait(self, resource, task):
        self._selector.register(resource, EVENT_READ, task)

    def trap_write_wait(self, resource, task):
        self._selector.register(resource, EVENT_WRITE, task)

    def trap_future_wait(self, future, task):
        future.add_done_callback(lambda fut: self._wake(task))

    def trap_sleep(self, seconds, task):
        heapq.heappush(self._sleeping, (time.monotonic() + seconds, task))

    # Low-level syscalls
    @coroutine
    def sock_recv(self, sock, maxsize):
        while True:
            try:
                return sock.recv(maxsize)
            except BlockingIOError:
                yield 'trap_read_wait', sock

    @coroutine
    def sock_sendall(self, sock, data):
        while data:
            try:
                nsent = sock.send(data)
                if nsent >= len(data):
                    return
                data = data[nsent:]
            except BlockingIOError:
                yield 'trap_write_wait', sock

    @coroutine
    def sock_accept(self, sock):
        while True:
            try:
                return sock.accept()
            except BlockingIOError:
                yield 'trap_read_wait', sock

    @coroutine
    def sock_connect(self, sock, address):
        while True:
            try:
                return sock.connect(address)
            except BlockingIOError:
                yield 'trap_write_wait', sock

    @coroutine
    def run_in_executor(self, exc, callable, *args):
        future = exc.submit(callable, *args)
        yield 'trap_future_wait', future
        return future.result()

    @coroutine
    def sleep(self, seconds):
        yield 'trap_sleep', seconds

    # I/O 
    def poll_for_io(self):
        if self._sleeping:
            timeout = self._sleeping[0][0] - time.monotonic()
        else:
            timeout = None

        events = self._selector.select(timeout)
        for key, mask in events:
            task = key.data
            self._selector.unregister(key.fileobj)
            self._ready.append(task)

        # Process sleeping tasks
        current = time.monotonic()
        while self._sleeping and self._sleeping[0][0] <= current:
            _, task = heapq.heappop(self._sleeping)
            self._ready.append(task)

    def run(self):
        while self.njobs > 0:
            # Poll for I/O as long as there is nothing to run
            while not self._ready:
                self.poll_for_io()

            # Run everything that's ready
            while self._ready:
                task = self._ready.popleft()
                try:
                    op, resource = task.send(None)
                    trap = getattr(self, op, None)
                    assert trap, "Unknown trap: %s" % op
                    trap(resource, task)
                except StopIteration as e:
                    self.njobs -= 1

    def add_task(self, coro):
        self._ready.append(coro)
        self.njobs += 1

            
        
