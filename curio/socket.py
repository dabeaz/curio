# curio/socket.py

import socket
from types import coroutine
from .kernel import read_wait, write_wait
from .file import File

__all__ = ['Socket', 'socketpair']

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

    async def recv(self, maxsize, flags=0):
        while True:
            try:
                return self._socket.recv(maxsize, flags)
            except BlockingIOError:
                await read_wait(self._socket, self._timeout)

    async def recv_into(self, buffer, nbytes=0, flags=0):
        while True:
            try:
                return self._socket.recv_into(buffer, nbytes, flags)
            except BlockingIOError:
                await read_wait(self._socket, self._timeout)

    async def send(self, data, flags=0):
        while True:
            try:
                return self._socket.send(data, flags)
            except BlockingIOError:
                await write_wait(self._socket, self._timeout)

    async def sendall(self, data, flags=0):
        buffer = memoryview(data).cast('b')
        while buffer:
            try:
                nsent = self._socket.send(buffer, flags)
                if nsent >= len(buffer):
                    return
                buffer = buffer[nsent:]
            except BlockingIOError:
                await write_wait(self._socket, self._timeout)

    async def accept(self):
        while True:
            try:
                client, addr = self._socket.accept()
                return Socket.from_sock(client), addr
            except BlockingIOError:
                await read_wait(self._socket, self._timeout)

    async def connect(self, address):
        try:
            return self._socket.connect(address)
        except BlockingIOError:
            await write_wait(self._socket, self._timeout)
        err = self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            raise OSError(err, 'Connect call failed %s' % (address,))

    async def recvfrom(self, buffersize, flags=0):
        while True:
            try:
                return self._socket.recvfrom(buffersize, flags)
            except BlockingIOError:
                await read_wait(self._socket, self._timeout)

    async def recvfrom_into(self, buffer, bytes=0, flags=0):
        while True:
            try:
                return self._socket.recvfrom_into(buffer, bytes, flags)
            except BlockingIOError:
                await read_wait(self._socket, self._timeout)

    async def sendto(self, data, address):
        while True:
            try:
                return self._socket.sendto(data, address)
            except BlockingIOError:
                await write_wait(self._socket, self._timeout)


    def makefile(self, mode, buffering=0):
        if mode not in ['rb', 'wb', 'rwb']:
            raise RuntimeError('File can only be created in binary mode')
        f = self._socket.makefile(mode, 0)
        return File(f)

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def __enter__(self):
        self._socket.__enter__()
        return self

    def __exit__(self, ety, eval, etb):
        self._socket.__exit__(ety, eval, etb)

def socketpair():
    s1, s2 = socket.socketpair()
    return Socket.from_sock(s1), Socket.from_sock(s2)
