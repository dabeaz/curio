"""
curio clone of socketserver built-in library.
"""

import socket
import os
import errno
from .socket import Socket
from .file import File
from .kernel import new_task

__all__ = ["BaseServer", "TCPServer", "UDPServer", 
           "BaseRequestHandler", "StreamRequestHandler",
           "DatagramRequestHandler"]

if hasattr(socket, "AF_UNIX"):
    __all__.extend(["UnixStreamServer","UnixDatagramServer"])

class BaseServer:

    """Base class for server classes.

    Methods for the caller:

    - __init__(server_address, RequestHandlerClass)
    - serve_forever(poll_interval=0.5)
    - shutdown()
    - handle_request()  # if you do not use serve_forever()
    - fileno() -> int   # for selector

    Methods that may be overridden:

    - server_bind()
    - server_activate()
    - get_request() -> request, client_address
    - handle_timeout()
    - verify_request(request, client_address)
    - server_close()
    - process_request(request, client_address)
    - shutdown_request(request)
    - close_request(request)
    - service_actions()
    - handle_error()

    Methods for derived classes:

    - finish_request(request, client_address)

    Class variables that may be overridden by derived classes or
    instances:

    - timeout
    - address_family
    - socket_type
    - allow_reuse_address

    Instance variables:

    - RequestHandlerClass
    - socket

    """

    def __init__(self, server_address, RequestHandlerClass):
        """Constructor.  May be extended, do not override."""
        self.server_address = server_address
        self.RequestHandlerClass = RequestHandlerClass

    def server_activate(self):
        """Called by constructor to activate the server.

        May be overridden.

        """
        pass

    async def serve_forever(self):
        """Handle one request at a time until shutdown."""
        while True:
            await self._handle_request_noblock()
            await self.service_actions()

    async def shutdown(self):
        pass
    
    async def service_actions(self):
        """Called by the serve_forever() loop.

        May be overridden by a subclass / Mixin to implement any code that
        needs to be run during the loop.
        """
        pass

    # The distinction between handling, getting, processing and finishing a
    # request is fairly arbitrary.  Remember:
    #
    # - handle_request() is the top-level call.  It calls selector.select(),
    #   get_request(), verify_request() and process_request()
    # - get_request() is different for stream or datagram sockets
    # - process_request() is the place that may fork a new process or create a
    #   new thread to finish the request
    # - finish_request() instantiates the request handler class; this
    #   constructor will handle the request all by itself

    async def handle_request(self):
        """Handle one request, possibly blocking.

        Respects self.timeout.
        """
        return await self._handle_request_noblock()

    async def _handle_request_noblock(self):
        request, client_address = await self.get_request()
        await new_task(self._run_request(request, client_address))

    async def _run_request(self, request, client_address):
        if await self.verify_request(request, client_address):
            try:
                await self.process_request(request, client_address)
            except:
                self.handle_error(request, client_address)
                self.shutdown_request(request)

    async def verify_request(self, request, client_address):
        """Verify the request.  May be overridden.

        Return True if we should proceed with this request.
        """
        return True

    async def process_request(self, request, client_address):
        """Call finish_request.

        Overridden by ForkingMixIn and ThreadingMixIn.

        """
        await self.finish_request(request, client_address)
        self.shutdown_request(request)

    async def server_close(self):
        """Called to clean-up the server.

        May be overridden.

        """
        pass

    async def finish_request(self, request, client_address):
        """Finish one request by instantiating RequestHandlerClass."""
        reqobj = self.RequestHandlerClass(request, client_address, self)
        await reqobj.setup()
        try:
            await reqobj.handle()
        finally:
            await reqobj.finish()

    def shutdown_request(self, request):
        """Called to shutdown and close an individual request."""
        self.close_request(request)

    def close_request(self, request):
        """Called to clean up an individual request."""
        pass

    def handle_error(self, request, client_address):
        """Handle an error gracefully.  May be overridden.

        The default is to print a traceback and continue.

        """
        print('-'*40)
        print('Exception happened during processing of request from', end=' ')
        print(client_address)
        import traceback
        traceback.print_exc() # XXX But this goes to stderr!
        print('-'*40)


class TCPServer(BaseServer):
    address_family = socket.AF_INET
    socket_type = socket.SOCK_STREAM
    request_queue_size = 5
    allow_reuse_address = False

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        BaseServer.__init__(self, server_address, RequestHandlerClass)
        self.socket = Socket(self.address_family,
                                   self.socket_type)
        if bind_and_activate:
            try:
                self.server_bind()
                self.server_activate()
            except:
                self.server_close()
                raise

    def server_bind(self):
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()

    def server_activate(self):
        self.socket.listen(self.request_queue_size)

    def server_close(self):
        self.socket.close()

    def fileno(self):
        return self.socket.fileno()

    async def get_request(self):
        return await self.socket.accept()

    def shutdown_request(self, request):
        try:
            request.shutdown(socket.SHUT_WR)
        except OSError:
            pass #some platforms may raise ENOTCONN here
        self.close_request(request)

    def close_request(self, request):
        """Called to clean up an individual request."""
        request.close()


class UDPServer(TCPServer):
    allow_reuse_address = False
    socket_type = socket.SOCK_DGRAM
    max_packet_size = 8192

    async def get_request(self):
        data, client_addr = await self.socket.recvfrom(self.max_packet_size)
        return (data, self.socket), client_addr

    def server_activate(self):
        # No need to call listen() for UDP.
        pass

    def shutdown_request(self, request):
        # No need to shutdown anything.
        self.close_request(request)

    def close_request(self, request):
        # No need to close anything.
        pass

if hasattr(socket, 'AF_UNIX'):
    class UnixStreamServer(TCPServer):
        address_family = socket.AF_UNIX

    class UnixDatagramServer(UDPServer):
        address_family = socket.AF_UNIX

class BaseRequestHandler:

    """Base class for request handler classes.

    This class is instantiated for each request to be handled.  The
    constructor sets the instance variables request, client_address
    and server.  To implement a specific service, all you need to do
    is to derive a class which defines a handle() method.

    The handle() method can find the request as self.request, the
    client address as self.client_address, and the server (in case it
    needs access to per-server information) as self.server.  Since a
    separate instance is created for each request, the handle() method
    can define arbitrary other instance variariables.

    """
    def __init__(self, request, client_address, server):
        self.request = request
        self.client_address = client_address
        self.server = server

    async def setup(self):
        pass

    async def handle(self):
        pass

    async def finish(self):
        pass


# The following two classes make it possible to use the same service
# class for stream or datagram servers.
# Each class sets up these instance variables:
# - rfile: a file object from which receives the request is read
# - wfile: a file object to which the reply is written
# When the handle() method returns, wfile is flushed properly

class StreamRequestHandler(BaseRequestHandler):

    """Define self.rfile and self.wfile for stream sockets."""

    # Default buffer sizes for rfile, wfile.
    # We default rfile to buffered because otherwise it could be
    # really slow for large data (a getc() call per byte); we make
    # wfile unbuffered because (a) often after a write() we want to
    # read and we need to flush the line; (b) big writes to unbuffered
    # files are typically optimized by stdio even when big reads
    # aren't.
    rbufsize = -1
    wbufsize = 0

    # Disable nagle algorithm for this socket, if True.
    # Use only when wbufsize != 0, to avoid small packets.
    disable_nagle_algorithm = False

    async def setup(self):
        self.connection = self.request
        if self.disable_nagle_algorithm:
            self.connection.setsockopt(socket.IPPROTO_TCP,
                                       socket.TCP_NODELAY, True)

        self.rfile = File(self.connection.fileno())
        self.wfile = File(self.connection.fileno())

        # self.rfile = self.connection.makefile('rb', self.rbufsize)
        # self.wfile = self.connection.makefile('wb', self.wbufsize)

    async def finish(self):
        if not self.wfile.closed:
            try:
                await self.wfile.flush()
            except socket.error:
                # An final socket error may have occurred here, such as
                # the local error ECONNABORTED.
                pass
        self.wfile.close()
        self.rfile.close()

class DatagramRequestHandler(BaseRequestHandler):
    """Define self.rfile and self.wfile for datagram sockets."""

    def setup(self):
        from io import BytesIO
        self.packet, self.socket = self.request
        self.rfile = BytesIO(self.packet)
        self.wfile = BytesIO()

    def finish(self):
        self.socket.sendto(self.wfile.getvalue(), self.client_address)
