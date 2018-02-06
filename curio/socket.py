# curio/socket.py
#
# Standin for the standard socket library.  The entire contents of stdlib socket are
# made available here.  However, the socket class is replaced by an async compatible version.
# Certain blocking operations are also replaced by versions safe to use in async.
#

import socket as _socket

__all__ = _socket.__all__

from socket import *
from functools import wraps

from . import workers
from . import io


@wraps(_socket.socket)
def socket(*args, **kwargs):
    return io.Socket(_socket.socket(*args, **kwargs))


@wraps(_socket.socketpair)
def socketpair(*args, **kwargs):
    s1, s2 = _socket.socketpair(*args, **kwargs)
    return io.Socket(s1), io.Socket(s2)


@wraps(_socket.fromfd)
def fromfd(*args, **kwargs):
    return io.Socket(_socket.fromfd(*args, **kwargs))

# Replacements for blocking functions related to domain names and DNS


@wraps(_socket.create_connection)
async def create_connection(*args, **kwargs):
    sock = await workers.run_in_thread(_socket.create_connection, *args, **kwargs)
    return io.Socket(sock)


@wraps(_socket.getaddrinfo)
async def getaddrinfo(*args, **kwargs):
    return await workers.run_in_thread(_socket.getaddrinfo, *args, **kwargs)


@wraps(_socket.getfqdn)
async def getfqdn(*args, **kwargs):
    return await workers.run_in_thread(_socket.getfqdn, *args, **kwargs)


@wraps(_socket.gethostbyname)
async def gethostbyname(*args, **kwargs):
    return await workers.run_in_thread(_socket.gethostbyname, *args, **kwargs)


@wraps(_socket.gethostbyname_ex)
async def gethostbyname_ex(*args, **kwargs):
    return await workers.run_in_thread(_socket.gethostbyname_ex, *args, **kwargs)


@wraps(_socket.gethostname)
async def gethostname(*args, **kwargs):
    return await workers.run_in_thread(_socket.gethostname, *args, **kwargs)


@wraps(_socket.gethostbyaddr)
async def gethostbyaddr(*args, **kwargs):
    return await workers.run_in_thread(_socket.gethostbyaddr, *args, **kwargs)


@wraps(_socket.getnameinfo)
async def getnameinfo(*args, **kwargs):
    return await workers.run_in_thread(_socket.getnameinfo, *args, **kwargs)
