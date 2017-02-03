# curio/network.py
#
# Some high-level functions useful for writing network code.  These are loosely
# based on their similar counterparts in the asyncio library. Some of the
# fiddly low-level bits are borrowed.

__all__ = [
    'open_connection',
    'tcp_server',
    'open_unix_connection',
    'unix_server'
]

from . import socket
from . import ssl as curiossl
from .task import spawn
from .io import Socket
import logging

log = logging.getLogger(__name__)

async def _wrap_ssl_client(sock, ssl, server_hostname, alpn_protocols):
    # Applies SSL to a client connection. Returns an SSL socket.
    if ssl:
        if isinstance(ssl, bool):
            sslcontext = curiossl.create_default_context()
            if not server_hostname:
                sslcontext._context.check_hostname = False
                sslcontext._context.verify_mode = curiossl.CERT_NONE

            if alpn_protocols:
                sslcontext.set_alpn_protocols(alpn_protocols)
        else:
            # Assume that ssl is an already created context
            sslcontext = ssl

        if server_hostname:
            extra_args = {'server_hostname': server_hostname}
        else:
            extra_args = {}

        # if the context is Curio's own, it expects a Curio socket and
        # returns one. If context is from an external source, including
        # the stdlib's ssl.SSLContext, it expects a non-Curio socket and
        # returns a non-Curio socket, which then needs wrapping in a Curio
        # socket.
        #
        # Perhaps the CurioSSLContext is no longer needed. In which case,
        # this code can be simplified to just the else case below.
        #
        if isinstance(sslcontext, curiossl.CurioSSLContext):
            sock = sslcontext.wrap_socket(sock, **extra_args)
        else:
            # do_handshake_on_connect should not be specified for
            # non-blocking sockets
            extra_args['do_handshake_on_connect'] = sock._socket.gettimeout() != 0.0
            sock = Socket(sslcontext.wrap_socket(sock._socket, **extra_args))
        await sock.do_handshake()
    return sock

async def open_connection(host, port, *, ssl=None, source_addr=None, server_hostname=None, alpn_protocols=None):
    '''
    Create a TCP connection to a given Internet host and port with optional SSL applied to it.
    '''
    if server_hostname and not ssl:
        raise ValueError('server_hostname is only applicable with SSL')

    sock = await socket.create_connection((host, port), source_addr)

    try:
        # Apply SSL wrapping to the connection, if applicable
        if ssl:
            sock = await _wrap_ssl_client(sock, ssl, server_hostname, alpn_protocols)

        return sock
    except Exception:
        sock._socket.close()
        raise

async def open_unix_connection(path, *, ssl=None, server_hostname=None, alpn_protocols=None):
    if server_hostname and not ssl:
        raise ValueError('server_hostname is only applicable with SSL')

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        await sock.connect(path)

        # Apply SSL wrapping to connection, if applicable
        if ssl:
            sock = await _wrap_ssl_client(sock, ssl, server_hostname, alpn_protocols)

        return sock
    except Exception:
        sock._socket.close()
        raise

async def _run_server(sock, client_connected_task, ssl=None):
    async def run_client(client, addr):
        async with client:
            await client_connected_task(client, addr)

    async with sock:
        while True:
            client, addr = await sock.accept()
            if ssl:
                client = ssl.wrap_socket(client._socket, server_side=True, do_handshake_on_connect=False)
                if not isinstance(client, Socket):
                    client = Socket(client)
            await spawn(run_client(client, addr))
            del client

async def tcp_server(host, port, client_connected_task, *,
                     family=socket.AF_INET, backlog=100, ssl=None,
                     reuse_address=True, reuse_port=False):

    if ssl and not hasattr(ssl, 'wrap_socket'):
        raise ValueError('ssl argument must have a wrap_socket method')

    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        if reuse_address:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)

        if reuse_port:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, True)
            except (AttributeError, OSError) as e:
                log.warning('reuse_port=True option failed', exc_info=True)

        sock.bind((host, port))
        sock.listen(backlog)
        await _run_server(sock, client_connected_task, ssl)
    except Exception:
        sock._socket.close()
        raise

async def unix_server(path, client_connected_task, *, backlog=100, ssl=None):
    if ssl and not hasattr(ssl, 'wrap_socket'):
        raise ValueError('ssl argument must have a wrap_socket method')

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(path)
        sock.listen(backlog)
        await _run_server(sock, client_connected_task, ssl)
    except Exception:
        sock._socket.close()
        raise
