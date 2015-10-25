# curio/socketserver.py
#
# A clone of the socketserver interface from the standard library

from . import socket
import os
import errno
from .kernel import new_task

__all__ = ["BaseServer", "TCPServer", "UDPServer", 
           "BaseRequestHandler", "StreamRequestHandler",
           "DatagramRequestHandler"]

if hasattr(socket, "AF_UNIX"):
    __all__.extend(["UnixStreamServer","UnixDatagramServer"])

class BaseServer:
    def __init__(self, server_address, RequestHandlerClass):
        self.server_address = server_address
        self.RequestHandlerClass = RequestHandlerClass

    def server_activate(self):
        pass

    async def serve_forever(self):
        """Handle one request at a time until shutdown."""
        while True:
            await self.handle_request()

    async def shutdown(self):
        pass

    async def handle_request(self):
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
        return True

    async def process_request(self, request, client_address):
        await self.finish_request(request, client_address)
        self.shutdown_request(request)

    def server_close(self):
        pass

    async def finish_request(self, request, client_address):
        reqobj = self.RequestHandlerClass(request, client_address, self)
        await reqobj.setup()
        try:
            await reqobj.handle()
        finally:
            await reqobj.finish()

    def shutdown_request(self, request):
        self.close_request(request)

    def close_request(self, request):
        pass

    def handle_error(self, request, client_address):
        print('-'*40)
        print('Exception happened during processing of request from', end=' ')
        print(client_address)
        import traceback
        traceback.print_exc()
        print('-'*40)


class TCPServer(BaseServer):
    address_family = socket.AF_INET
    socket_type = socket.SOCK_STREAM
    request_queue_size = 5
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        BaseServer.__init__(self, server_address, RequestHandlerClass)
        self.socket = socket.socket(self.address_family, self.socket_type)
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
        request.close()


class UDPServer(TCPServer):
    allow_reuse_address = True
    socket_type = socket.SOCK_DGRAM
    max_packet_size = 8192

    async def get_request(self):
        data, client_addr = await self.socket.recvfrom(self.max_packet_size)
        return (data, self.socket), client_addr

    def server_activate(self):
        pass

    def shutdown_request(self, request):
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
    __slots__ = ('request', 'client_address', 'server')
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

        self.rfile = self.connection.makefile('rb')
        self.wfile = self.connection.makefile('wb')

    async def finish(self):
        await self.wfile.close()
        await self.rfile.close()

class DatagramRequestHandler(BaseRequestHandler):
    """Define self.rfile and self.wfile for datagram sockets."""

    async def setup(self):
        from io import BytesIO
        self.packet, self.socket = self.request
        self.rfile = BytesIO(self.packet)
        self.wfile = BytesIO()

    async def finish(self):
        await self.socket.sendto(self.wfile.getvalue(), self.client_address)
