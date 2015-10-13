# kernel.py

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, defaultdict
import socket
from types import coroutine
import heapq
import time
import threading
import os

class Kernel(object):
    def __init__(self, selector=None):
        if selector is None:
            selector = DefaultSelector()
        self._selector = selector
        self._ready = deque()
        self._status = defaultdict(dict)
        self._sleeping = []
        self._suspended = { }
        self._killed = set()
        self._current_task = None
        self.njobs = 0

        # Create task responsible for waiting the event loop
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self.add_task(self._wait_task(), daemon=True)

    # Callback that causes the kernel to wake on non-I/O events
    def _wake(self, task):
        self._ready.append(task)
        self._notify_sock.send(b'x')

    # Internal task that wakes the kernel on non-I/O events
    @coroutine
    def _wait_task(self):
        while True:
            yield 'trap_read_wait', self._wait_sock
            data = self._wait_sock.recv(100)

    # Traps
    def trap_read_wait(self, resource, task):
        self._selector.register(resource, EVENT_READ, task)
        self._status[id(task)]['state'] = 'READ_WAIT'

    def trap_write_wait(self, resource, task):
        self._selector.register(resource, EVENT_WRITE, task)
        self._status[id(task)]['state'] = 'WRITE_WAIT'

    def trap_future_wait(self, future, task):
        future.add_done_callback(lambda fut: self._wake(task))
        self._status[id(task)]['state'] = 'FUTURE_WAIT'

    def trap_wait(self, queue, task, state):
        queue.append(task)
        self._status[id(task)]['state'] = state

    def trap_sleep(self, seconds, task):
        heapq.heappush(self._sleeping, (time.monotonic() + seconds, task))
        self._status[id(task)]['state'] = 'TIME_SLEEP'

    @coroutine
    def wait_on(self, queue, state):
        yield 'trap_wait', queue, state

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
            self._status[id(task)]['state'] = 'READY'

        # Process sleeping tasks
        current = time.monotonic()
        while self._sleeping and self._sleeping[0][0] <= current:
            _, task = heapq.heappop(self._sleeping)
            self._ready.append(task)
            self._status[id(task)]['state'] = 'READY'

    def run(self, detached=False):
        if detached:
            threading.Thread(target=self.run).start()
            return

        while self.njobs > 0:
            self._current_task = None

            # Poll for I/O as long as there is nothing to run
            while not self._ready:
                self.poll_for_io()

            # Run everything that's ready
            while self._ready:
                self._current_task = self._ready.popleft()
                taskid = id(self._current_task)

                if taskid in self._killed:
                    self._current_task.close()
                    self._killed.remove(taskid)
                    del self._status[taskid]
                    self.njobs -= 1
                    continue
                    
                if taskid in self._suspended:
                    self._suspended[taskid] = task
                    self._status[taskid]['state'] = 'SUSPENDED'
                    continue

                try:
                    self._status[taskid]['state'] = 'RUNNING'
                    self._status[taskid]['cycles'] += 1
                    op, resource, *extra = self._current_task.send(None)
                    trap = getattr(self, op, None)
                    assert trap, "Unknown trap: %s" % op
                    trap(resource, self._current_task, *extra)
                except StopIteration as e:
                    del self._status[taskid]
                    self.njobs -= 1

    def reschedule_task(self, task):
        self._ready.append(task)
        self._status[id(task)]['state'] = 'READY'

    def add_task(self, task, daemon=False):
        self._ready.append(task)
        self._status[id(task)]['coro'] = task
        self._status[id(task)]['state'] = 'READY'
        self._status[id(task)]['cycles'] = 0
        if not daemon:
            self.njobs += 1

    # Debugging
    def ps(self):
        headers = ('Task ID', 'State', 'Cycles', 'Task')
        widths = (12, 12, 10, 50)
        for h, w in zip(headers, widths):
            print('%-*s' % (w, h), end=' ')
        print()
        print(' '.join(w*'-' for w in widths))
        for taskid in sorted(self._status):
            state = self._status[taskid]['state']
            coro = self._status[taskid]['coro']
            cycles = self._status[taskid]['cycles']
            print('%-*d %-*s %-*d %-*s' % (widths[0], taskid, 
                                           widths[1], state,
                                           widths[2], cycles,
                                           widths[3], coro))

    def suspend_task(self, taskid):
        self._suspended[taskid] = None

    def resume_task(self, taskid):
        self._wake(self._suspended.pop(taskid))

    def kill_task(self, taskid):
        self._killed.add(taskid)

class Socket(object):
    '''
    Wrapper around a standard socket object.
    '''
    def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
        self._socket = socket.socket(family, type, proto, fileno)
        self._socket.setblocking(False)

    @classmethod
    def from_sock(cls, sock):
        self = Socket.__new__(Socket)
        self._socket = sock
        self._socket.setblocking(False)
        return self

    def __repr__(self):
        return '<curio.Socket %r>' % (self._socket)

    def dup(self):
        return Socket.from_sock(self._socket.dup())

    @coroutine
    def recv(self, maxsize):
        while True:
            try:
                return self._socket.recv(maxsize)
            except BlockingIOError:
                yield 'trap_read_wait', self._socket

    @coroutine
    def send(self, data):
        while True:
            try:
                return self._socket.send(data)
            except BlockingIOError:
                yield 'trap_write_wait', self._socket

    @coroutine
    def sendall(self, data):
        while data:
            try:
                nsent = self._socket.send(data)
                if nsent >= len(data):
                    return
                data = data[nsent:]
            except BlockingIOError:
                yield 'trap_write_wait', self._socket

    @coroutine
    def accept(self):
        while True:
            try:
                client, addr = self._socket.accept()
                return Socket.from_sock(client), addr
            except BlockingIOError:
                yield 'trap_read_wait', self._socket

    @coroutine
    def connect(self, address):
        while True:
            try:
                return self._socket.connect(address)
            except BlockingIOError:
                yield 'trap_write_wait', self._socket

    @coroutine
    def recvfrom(self, buffersize):
        while True:
            try:
                return self._socket.recvfrom(buffersize)
            except BlockingIOError:
                yield 'trap_read_wait', self._socket

    @coroutine
    def sendto(self, data, address):
        while True:
            try:
                return self._socket.sendto(data, address)
            except BlockingIOError:
                yield 'trap_write_wait', self._socket

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def __enter__(self):
        return self

    def __exit__(self, ety, eval, etb):
        self._socket.__exit__(ety, eval, etb)

class File(object):
    '''
    Wrapper around file objects.  Proof of concept. Needs to be redone
    '''
    def __init__(self, fileno):

        if not isinstance(fileno, int):
            fileno = fileno.fileno()

        self._fileno = fileno
        os.set_blocking(fileno, False)
        self._linebuffer = bytearray()
        self.closed = False

    def fileno(self):
        return self._fileno

    @coroutine
    def read(self, maxbytes):
        while True:
            try:
                return os.read(self._fileno, maxbytes)
            except BlockingIOError:
                yield 'trap_read_wait', self

    async def readline(self):
        while True:
            nl_index = self._linebuffer.find(b'\n')
            if nl_index >= 0:
                resp = bytes(self._linebuffer[:nl_index+1])
                del self._linebuffer[:nl_index+1]
                return resp
            data = await self.read(1000)
            if not data:
                resp = bytes(self._linebuffer)
                del self._linebuffer[:]
                return resp
            self._linebuffer.extend(data)

    @coroutine
    def write(self, data):
        nwritten = 0
        while data:
            try:
                nbytes = os.write(self._fileno, data)
                nwritten += nbytes
                data = data[nbytes:]
            except BlockingIOError:
                yield 'trap_write_wait', self

        return nwritten

    async def writelines(self, lines):
        for line in lines:
            await self.write(line)

    def close(self):
        os.close(self._fileno)
        self.closed = True

    async def flush(self):
        pass

_default_kernel = None
def get_kernel():
    '''
    Return the default kernel.
    '''
    global _default_kernel
    if _default_kernel is None:
        _default_kernel = Kernel()
    return _default_kernel

async def sleep(seconds):
    kernel = get_kernel()
    await kernel.sleep(seconds)

__all__ = [ 'Kernel', 'Socket', 'File', 'get_kernel', 'sleep' ]
            
        
