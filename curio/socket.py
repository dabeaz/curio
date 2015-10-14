# curio/socket.py

import socket
from types import coroutine

__all__ = ['Socket']

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
        try:
            return self._socket.connect(address)
        except BlockingIOError:
            yield 'trap_write_wait', self._socket
        err = self._socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        if err != 0:
            raise OSError(err, 'Connect call failed %s' % (address,))

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
