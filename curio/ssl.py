# curio/ssl.py
#
# Wrapper around built-in SSL module

__all__ = []

from functools import wraps, partial
from .workers import run_blocking
from .io import Socket

try:
    import ssl as _ssl
    from ssl import *
except ImportError:
    # We need these exceptions defined, even if ssl is not available.
    class SSLWantReadError(Exception):
        pass
    class SSLWantWriteError(Exception):
        pass

if _ssl:
    @wraps(_ssl.wrap_socket)
    def wrap_socket(sock, *args, do_handshake_on_connect=True, **kwargs):
        if isinstance(sock, Socket):
            sock = sock._socket

        ssl_sock = _ssl.wrap_socket(sock, *args, do_handshake_on_connect=False, **kwargs)
        cssl_sock = Socket(ssl_sock)
        cssl_sock.do_handshake_on_connect = do_handshake_on_connect
        return cssl_sock

    @wraps(_ssl.wrap_socket)
    async def get_server_certificate(*args, **kwargs):
        return await run_blocking(partial(_ssl.get_server_certicate, *args, **kwargs))


    # Small wrapper class to make sure the wrap_socket() method returns the right type
    class CurioSSLContext(object):
        def __init__(self, context):
            self._context = context
            
        def __getattr__(self, name):
            return getattr(self._context, name)

        def wrap_socket(self, *args, do_handshake_on_connect=True, **kwargs):
            sock = self._context.wrap_socket(*args, do_handshake_on_connect=False, **kwargs)
            csock = Socket(sock)
            csock.do_handshake_on_connect = do_handshake_on_connect
            return csock
        
    @wraps(_ssl.create_default_context)
    def create_default_context(*args, **kwargs):
        context = _ssl.create_default_context(*args, **kwargs)
        return CurioSSLContext(context)

    
    
