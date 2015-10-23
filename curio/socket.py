# curio/socket.py
#
# Standin for the standard library socket library.  The entire contents of stdlib socket are
# made available here.  However, the socket class is replaced by an async compatible version.
# Certain blocking operations are also replaced by versions safe to use in async.

import socket as _socket

__all__ = _socket.__all__

from socket import *
from functools import wraps, partial

from .kernel import read_wait, write_wait
from .file import File
from .workers import run_blocking

class CurioSocket(object):
    __slots__ = ('_socket', '_timeout')
    '''
    Wrapper around a standard socket object.
    '''
    def __init__(self, family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None):
        self._socket = _socket.socket(family, type, proto, fileno)
        self._socket.setblocking(False)
        self._timeout = None

    def settimeout(self, seconds):
        self._timeout = seconds

    @classmethod
    def from_sock(cls, sock):
        self = cls.__new__(cls)
        self._socket = sock
        self._socket.setblocking(False)
        self._timeout = None
        return self

    def __repr__(self):
        return '<curio.socket %r>' % (self._socket)

    def dup(self):
        return socket.from_sock(self._socket.dup())

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
                return socket.from_sock(client), addr
            except BlockingIOError:
                await read_wait(self._socket, self._timeout)

    async def connect(self, address):
        try:
            return self._socket.connect(address)
        except BlockingIOError:
            await write_wait(self._socket, self._timeout)
        err = self._socket.getsockopt(SOL_SOCKET, SO_ERROR)
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

# Alias socket to CurioSocket
socket = CurioSocket

@wraps(_socket.socketpair)
def socketpair(*args, **kwargs):
    s1, s2 = _socket.socketpair(*args, **kwargs)
    return socket.from_sock(s1), socket.from_sock(s2)

@wraps(_socket.fromfd)
def fromfd(*args, **kwargs):
    return socket.from_sock(_socket.fromfd(*args, **kwargs))

# Replacements for blocking functions related to domain names and DNS

@wraps(_socket.create_connection)
async def create_connection(*args, **kwargs):
    sock = await run_blocking(partial(_socket.create_connection, *args, **kwargs))
    return socket.from_sock(sock)

@wraps(_socket.getaddrinfo)
async def getaddrinfo(*args, **kwargs):
    return await run_blocking(partial(_socket.getaddrinfo, *args, **kwargs))

@wraps(_socket.getfqdn)
async def getfqdn(*args, **kwargs):
    return await run_blocking(partial(_socket.getfqdn, *args, **kwargs))

@wraps(_socket.gethostbyname)
async def gethostbyname(*args, **kwargs):
    return await run_blocking(partial(_socket.gethostbyname, *args, **kwargs))

@wraps(_socket.gethostbyname_ex)
async def gethostbyname_ex(*args, **kwargs):
    return await run_blocking(partial(_socket.gethostbyname_ex, *args, **kwargs))

@wraps(_socket.gethostname)
async def gethostname(*args, **kwargs):
    return await run_blocking(partial(_socket.gethostname, *args, **kwargs))

@wraps(_socket.gethostbyaddr)
async def gethostbyaddr(*args, **kwargs):
    return await run_blocking(partial(_socket.gethostbyaddr, *args, **kwargs))

@wraps(_socket.getnameinfo)
async def getnameinfo(*args, **kwargs):
    return await run_blocking(partial(_socket.getnameinfo, *args, **kwargs))




    

     
    
