# curio/network.py
#
# Copyright (C) 2015
# David Beazley (Dabeaz LLC)
# All rights reserved.
#
# Some high-level functions useful for writing network code.  These are largely
# based on their similar counterparts in the asyncio library. Some of the
# fiddly low-level bits are borrowed.   
#
# Note: Not sure this module will be retained in future of curio.  Currently
# experimental.

import logging
log = logging.getLogger(__name__)

from . import socket
from . import ssl as curiossl
from .kernel import new_task

__all__ = [ 
    'open_connection',
    'create_server',
    'run_server',
    'open_unix_connection',
    'create_unix_server',
    'run_unix_server'
    ]

async def _wrap_ssl_client(sock, ssl, server_hostname):
    # Applies SSL to a client connection. Returns an SSL socket.
    if ssl:
        if isinstance(ssl, bool):
            sslcontext = curiossl.create_default_context()
            if not server_hostname:
                sslcontext._context.check_hostname = False
                sslcontext._context.verify_mode = curiossl.CERT_NONE
        else:
            # Assume that ssl is an already created context
            sslcontext = ssl

        if server_hostname:
            extra_args = {'server_hostname': server_hostname}
        else:
            extra_args = { }

        sock = sslcontext.wrap_socket(sock, **extra_args)
        await sock.do_handshake()
    return sock

async def open_connection(host, port, *, ssl=None, source_addr=None, server_hostname=None, timeout=None):
    '''
    Create a TCP connection to a given Internet host and port with optional SSL applied to it.
    '''
    if server_hostname and not ssl:
        raise ValueError('server_hostname is only applicable with SSL')

    sock = await socket.create_connection((host,port), timeout, source_addr)

    try:
        # Apply SSL wrapping to the connection, if applicable
        if ssl:
            sock = await _wrap_ssl_client(sock, ssl, server_hostname)

        return sock
    except Exception:
        sock._socket.close()
        raise

async def open_unix_connection(path, *, ssl=None, server_hostname=None):
    if server_hostname and not ssl:
        raise ValueError('server_hostname is only applicable with SSL')

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        await sock.connect(path)

        # Apply SSL wrapping to connection, if applicable
        if ssl:
            sock = await _wrap_ssl_client(sock, ssl, server_hostname)

        return sock
    except Exception:
        sock._socket.close()
        raise

class Server(object):
    def __init__(self, sock, client_connected_task, ssl=None):
        self._sock = sock
        self._ssl = ssl
        self._client_connected_task = client_connected_task
        self._task = None

    async def serve_forever(self):
        async with self._sock:
            while True:
                client, addr = await self._sock.accept()

                if self._ssl:
                    client = self._ssl.wrap_socket(client, server_side=True, do_handshake_on_connect=False)

                client_task = await new_task(self.run_client(client, addr))
                del client

    async def run_client(self, client, addr):
        async with client:
            await self._client_connected_task(client, addr)

    async def cancel(self):
        if self._task:
            await self._task.cancel()
        
def create_server(host, port, client_connected_task, *, 
                        family=socket.AF_INET, backlog=100, ssl=None, reuse_address=True):

    if ssl and not isinstance(ssl, curiossl.CurioSSLContext):
        raise ValueError('ssl argument must be a curio.ssl.SSLContext instance')

    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if reuse_address:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        sock.bind((host, port))
        sock.listen(backlog)
        serv = Server(sock, client_connected_task, ssl)
        return serv
    except Exception:
        sock._socket.close()
        raise

async def run_server(*args, **kwargs):
    serv = create_server(*args, **kwargs)
    await serv.serve_forever()

def create_unix_server(path, client_connected_task, *, backlog=100, ssl=None):
    if ssl and not isinstance(ssl, curiossl.CurioSSLContext):
        raise ValueError('ssl argument must be a curio.ssl.SSLContext instance')
  
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(path)
        sock.listen(backlog)
        serv = Server(sock, client_connected_task, ssl)
        return serv
    except Exception:
        sock._socket.close()
        raise

async def run_unix_server(*args, **kwargs):
    serv = create_unix_server(*args, **kwargs)
    await serv.serve_forever()
