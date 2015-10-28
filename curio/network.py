# curio/network.py
#
# Some high-level functions useful for writing network code.  These are largely
# based on their similar counterparts in the asyncio library. Some of the
# fiddly low-level bits are borrowed.

import logging
import collections

log = logging.getLogger(__name__)

from . import socket
from . import ssl as curiossl
from .kernel import new_task

__all__ = [ 
    'open_tcp_connection',
    'start_tcp_server',
    'create_datagram_endpoint',
    'open_unix_connection',
    'start_unix_server'
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

async def open_tcp_connection(host, port, *, ssl=None, family=0, proto=0, flags=0, 
                              local_addr=None, server_hostname=None):
    '''
    Create a TCP connection to a given Internet host and port with 
    optional SSL applied to it.
    '''
    if server_hostname and not ssl:
        raise ValueError('server_hostname is only applicable with SSL')

    remote_info = await socket.getaddrinfo(host, port, 
                                           family=family, type=socket.SOCK_STREAM, 
                                           proto=proto, flags=flags)
    if not remote_info:
        raise OSError('getaddrinfo returned empty list for (%r, %r)' % (host, port))

    if local_addr:
        local_info = await socket.getaddrinfo(*local_addr,
                                               family=family, type=socket.SOCK_STREAM, 
                                               proto=proto, flags=flags)
        if not local_info:
            raise OSError('getaddrinfo returned empty list for (%r, %r)' % local_addr)
    else:
        local_info = []

    exceptions = []
    for family, type, proto, cname, address in remote_info:
        try:
            sock = socket.socket(family=family, type=type, proto=proto)
            if local_info:
                for *_, laddr in local_info:
                    try:
                        sock.bind(laddr)
                        break
                    except OSError as exc:
                        exc = OSError(
                            exc.errno, 'error while '
                                       'attempting to bind on address '
                                       '{!r}: {}'.format(
                                laddr, exc.strerror.lower()))
                        exceptions.append(exc)
                else:
                    sock.close()
                    sock = None
                    continue

                    logger.debug("connect %r to %r", sock, address)
            await sock.connect(address)
        except OSError as exc:
            if sock is not None:
                await sock.close()
            exceptions.append(exc)
        except:
            if sock is not None:
                await sock.close()
            raise
        else:
            break
    else:
        if len(exceptions) == 1:
            raise exceptions[0]
        else:
            # If they all have the same str(), raise one.                                                                                                
            model = str(exceptions[0])
            if all(str(exc) == model for exc in exceptions):
                raise exceptions[0]
            # Raise a combined exception so the user can see all                                                                                         
            # the various error messages.                                                                                                                
            raise OSError('Multiple exceptions: {}'.format(
                    ', '.join(str(exc) for exc in exceptions)))

    # Apply SSL wrapping to connection, if applicable
    if ssl:
        sock = await _wrap_ssl_client(sock, ssl, server_hostname)

    return sock

async def start_tcp_server(host, port, client_connected_task, *, 
                           family=socket.AF_UNSPEC, flags=socket.AI_PASSIVE,
                           backlog=100, ssl=None, reuse_address=True, debug=False):

    if ssl and not isinstance(ssl, curiossl.CurioSSLContext):
        raise ValueError('ssl argument must be a curio.ssl.SSLContext instance')
  
    if host == '':
        host = None

    infos = await socket.getaddrinfo(host, port, family=family,
                                     type=socket.SOCK_STREAM, proto=0, flags=flags)
    if not infos:
        raise OSError('getaddrinfo() returned empty list')

    sockets = []
    completed = False
    try:
        for af, socktype, proto, canonname, sa in infos:
            try:
                sock = socket.socket(af, socktype, proto)
            except socket.error as e:
                if debug:
                    log.warning('tcp_server() failed to create '
                                'socket.socket(%r, %r, %r)',
                                af, socktype, proto, exc_info=True)
                continue

            sockets.append(sock)

            if reuse_address:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,  True)

            # Disable IPv4/IPv6 dual stack support (enabled by                                                                                           
            # default on Linux) which makes a single socket                                                                                              
            # listen on both address families.                                                                                                           
            if af == socket.AF_INET6 and hasattr(socket, 'IPPROTO_IPV6'):
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, True)
            try:
                sock.bind(sa)
            except OSError as err:
                raise OSError(err.errno, 'error while attempting '
                                         'to bind on address %r: %s'
                                        % (sa, err.strerror.lower()))

        completed = True
    finally:
        if not completed:
            for sock in sockets:
                sock._socket.close()

    # Bring the servers up if successfully bound
    tasks = []
    for sock in sockets:
        sock.listen(backlog)
        tasks.append(await new_task(_stream_server_run(sock, client_connected_task, ssl)))
    return tasks

async def _stream_server_run(sock, client_connected_task, ssl):
    while True:
        client, addr = await sock.accept()
        if ssl:
            client = ssl.wrap_socket(client, server_side=True, do_handshake_on_connect=False)
            client.ssl_context = ssl
        await new_task(client_connected_task(client, addr))
        del client

async def create_datagram_endpoint(local_addr=None, remote_addr=None, *, family=0,
                                   proto=0, flags=0, reuse_address=False):

    if not (local_addr or remote_addr):
        if family == 0:
            raise ValueError('unexpected address family')
        addr_pairs_info = (((family, proto), (None, None)),)
    else:
        # join address by (family, protocol)                                                                                                                 
        addr_infos = collections.OrderedDict()
        for idx, addr in ((0, local_addr), (1, remote_addr)):
            if addr is not None:
                assert isinstance(addr, tuple) and len(addr) == 2, (
                    '2-tuple is expected')

                infos = await socket.getaddrinfo(
                    *addr, family=family, type=socket.SOCK_DGRAM,
                    proto=proto, flags=flags)

                if not infos:
                    raise OSError('getaddrinfo() returned empty list')

                for fam, _, pro, _, address in infos:
                    key = (fam, pro)
                    if key not in addr_infos:
                        addr_infos[key] = [None, None]
                    addr_infos[key][idx] = address

        # each addr has to have info for each (family, proto) pair                                                                                           
        addr_pairs_info = [
            (key, addr_pair) for key, addr_pair in addr_infos.items()
            if not ((local_addr and addr_pair[0] is None) or
                    (remote_addr and addr_pair[1] is None))]

        if not addr_pairs_info:
            raise ValueError('can not get address information')

    exceptions = []

    for ((family, proto),
         (local_address, remote_address)) in addr_pairs_info:
        sock = None
        r_addr = None
        try:
            sock = socket.socket(
                family=family, type=socket.SOCK_DGRAM, proto=proto)

            if reuse_address:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if local_addr:
                sock.bind(local_address)
            if remote_addr:
                await sock.connect(remote_address)
        except OSError as exc:
            if sock is not None:
                await sock.close()
            exceptions.append(exc)
        except:
            if sock is not None:
                sock.close()
            raise
        else:
            break
    else:
        raise exceptions[0]

    return sock

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
    except Exception as e:
        await sock.close()
        raise

async def start_unix_server(path, client_connected_task, *, backlog=100, ssl=None):
    if ssl and not isinstance(ssl, curiossl.CurioSSLContext):
        raise ValueError('ssl argument must be a curio.ssl.SSLContext instance')
  
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(path)
        sock.listen(backlog)
        return await new_task(_stream_server_run(sock, client_connected_task, ssl))
    except Exception as e:
        await sock.close()
        raise

