# kernel.py

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, defaultdict
import socket
from types import coroutine
import heapq
import time
import threading
import os

class CancelledError(Exception):
    pass

class TimeoutError(Exception):
    pass

class Kernel(object):
    def __init__(self, selector=None):
        if selector is None:
            selector = DefaultSelector()
        self._selector = selector
        self._ready = deque()              # Tasks ready to run
        self._status = defaultdict(dict)   # Task status information
        self._sleeping = []                # Heap of tasks waiting on sleep()
        self._suspended = {}               # Tasks that have requested a suspension
        self._killed = set()               # Tasks with a pending kill request
        self._current_task = None          # Currently running task 
        self._current_status = None        # Status dict of current running task
        self.njobs = 0

        # Create task responsible for waiting the event loop
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self.add_task(self._wait_task(), daemon=True)

    # Callback that causes the kernel to wake on non-I/O events
    def _wake(self, task, value=None, exc=None):
        self.reschedule_task(task, value, exc)
        self._notify_sock.send(b'x')

    # Internal task that monitors the loopback socket--allowing the kernel to
    # awake for non-I/O events.
    @coroutine
    def _wait_task(self):
        while True:
            yield 'trap_read_wait', self._wait_sock
            data = self._wait_sock.recv(100)

    # Traps.  Low level system calls. Direct use is discouraged.
    def trap_read_wait(self, resource, timeout=None):
        self._selector.register(resource, EVENT_READ, self._current_task)
        self._current_status['state'] = 'READ_WAIT'
        self._current_status['kill'] = lambda task=self._current_task: self._selector.unregister(resource)
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_write_wait(self, resource, timeout=None):
        self._selector.register(resource, EVENT_WRITE, self._current_task)
        self._current_status['state'] = 'WRITE_WAIT'
        self._current_status['kill'] = lambda task=self._current_task: self._selector.unregister(resource)
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_future_wait(self, future, timeout=None):
        future.add_done_callback(lambda fut, task=self._current_task: self._wake(task))
        self._current_status['state'] = 'FUTURE_WAIT'
        self._current_status['kill'] = lambda: None
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_wait(self, queue, state, timeout=None):
        queue.append(self._current_task)
        self._current_status['state'] = state
        self._current_status['kill'] = lambda task=self._current_task: queue.remove(task)
        if timeout is not None:
            self._set_timeout(timeout)

    def trap_alarm(self, timeout):
        self._set_timeout(timeout)
        self.reschedule_task(self._current_task)

    def _set_timeout(self, seconds, sleep_type='timeout'):
        item = (time.monotonic() + seconds, self._current_task, sleep_type)
        heapq.heappush(self._sleeping, item)
        
    def trap_sleep(self, seconds, sleep_type='sleep'):
        self._set_timeout(seconds, sleep_type)
        self._current_status['state'] = 'TIME_SLEEP'
        def remove():
            self._sleeping.remove(item)
            heapq.heapify(self._sleeping)
        self._current_status['kill'] = remove

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
            self.reschedule_task(task)

        # Process sleeping tasks
        current = time.monotonic()
        while self._sleeping and self._sleeping[0][0] <= current:
            _, task, sleep_type = heapq.heappop(self._sleeping)
            if sleep_type == 'sleep':
                self.reschedule_task(task)
            elif sleep_type == 'timeout':
                self.cancel_task(id(task), exc=TimeoutError)

    # Kernel central loop
    def run(self, detached=False):
        if detached:
            threading.Thread(target=self.run).start()
            return

        while self.njobs > 0:
            self._current_task = None
            self._current_status = None

            # Poll for I/O as long as there is nothing to run
            while not self._ready:
                self.poll_for_io()

            # Run everything that's ready
            while self._ready:
                self._current_task, value, exc = self._ready.popleft()
                self._current_status = self._status[id(self._current_task)]
                taskid = id(self._current_task)

                if taskid in self._killed:
                    self._current_task.close()        # Might be dicey (what if holding locks with async context manager)
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
                    if exc is None:
                        op, *args = self._current_task.send(value)
                    else:
                        op, *args = self._current_task.throw(exc)
                    trap = getattr(self, op, None)
                    assert trap, "Unknown trap: %s" % op
                    trap(*args)
                except (StopIteration, CancelledError) as e:
                    del self._status[taskid]
                    self.njobs -= 1

    def reschedule_task(self, task, value=None, exc=None):
        self._ready.append((task, value, exc))
        self._status[id(task)]['state'] = 'READY'
        self._status[id(task)].pop('kill', None)

    def add_task(self, task, daemon=False):
        self.reschedule_task(task)
        self._status[id(task)]['coro'] = task
        self._status[id(task)]['cycles'] = 0
        if not daemon:
            self.njobs += 1
        return id(task)

    def cancel_task(self, taskid, exc=CancelledError):
        task_status = self._status[taskid]
        if task_status == self._current_status:
            raise CancelledError()

        # Remove/unregister the task from whereever it might happen to be at the moment
        kill_func = task_status.pop('kill', None)
        if kill_func:
            kill_func()

        # Reschedule it with a pending exception
        self.reschedule_task(task_status['coro'], exc=exc())

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

    # System calls
    @coroutine
    def wait_on(self, queue, state, timeout=None):
        yield 'trap_wait', queue, state, timeout

    @coroutine
    def run_in_executor(self, exc, callable, *args):
        future = exc.submit(callable, *args)
        yield 'trap_future_wait', future
        return future.result()

@coroutine
def sleep(seconds):
    yield 'trap_sleep', seconds

@coroutine
def alarm(seconds):
    yield 'trap_alarm', seconds

class Socket(object):
    '''
    Wrapper around a standard socket object.
    '''
    def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
        self._socket = socket.socket(family, type, proto, fileno)
        self._socket.setblocking(False)
        self._timeout = None

    def settimeout(self, seconds):
        self._timeout = seconds

    @classmethod
    def from_sock(cls, sock):
        self = Socket.__new__(Socket)
        self._socket = sock
        self._socket.setblocking(False)
        self._timeout = None
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
                yield 'trap_read_wait', self._socket, self._timeout

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
                yield 'trap_read_wait', self._socket, self._timeout

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
                yield 'trap_read_wait', self._socket, self._timeout

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

__all__ = [ 'Kernel', 'Socket', 'File', 'get_kernel', 'sleep', 'alarm',
            'CancelledError', 'TimeoutError' ]
            
        
