# curio/io.py
#
# I/O wrapper objects.  Let's talk about design for a moment...
#
# Curio is primarily concerned with the scheduling of tasks. In particular,
# the kernel does not actually perform any I/O.   It merely blocks tasks
# that need to wait for reading or writing.  To actually perform I/O, you
# use the existing file and socket abstractions already provided by the Python
# standard library.  The only difference is that you need to take extra steps
# to manage their behavior with non-blocking I/O.
#
# The classes in this file provide wrappers around socket-like and file-like
# objects. Methods responsible for reading/writing have a small amount of extra
# logic to added to handle their scheduling.  Other methods are simply passed
# through to the original object via delegation. 
#
# It's important to emphasize that these classes can be applied to
# *ANY* existing socket-like or file-like object as long as it
# represents a real system-level file (must have a fileno() method)
# and can be used with the underlying I/O selector.  For example, the
# Socket class can wrap a normal socket or an SSL socket--it doesn't
# matter which.  Similarly, the Stream class can wrap normal files,
# files created from sockets, pipes, and other file-like abstractions.
#
# No assumption is made about system compatibility (Unix vs. Windows).  
# The main compatibility concern would be at the level of the I/O
# selector used by the kernel.  For example, can it detect I/O events
# on the provide file or socket.

from .kernel import read_wait, write_wait

from socket import SOL_SOCKET, SO_ERROR
import io
import os

__all__ = ['Socket', 'Stream']

# Exceptions raised for non-blocking I/O.  For normal sockets, blocking operations
# normally just raise BlockingIOError.  For SSL sockets, more specific exceptions
# are raised.  Here we're just making some aliases for the possible exceptions.

try:
    from ssl import SSLWantReadError, SSLWantWriteError
    WantRead = (BlockingIOError, SSLWantReadError)
    WantWrite = (BlockingIOError, SSLWantWriteError)
except ImportError:
    WantRead = BlockingIOError
    WantWrite = BlockingIOError

class Socket(object):
    '''
    Non-blocking wrapper around a socket object.   The original socket is put
    into a non-blocking mode when it's wrapped.
    '''
    def __init__(self, sock):
        self._socket = sock
        self._socket.setblocking(False)
        self._timeout = None

    def settimeout(self, seconds):
        self._timeout = seconds

    def __repr__(self):
        return '<curio.socket %r>' % (self._socket)

    def dup(self):
        return Socket(self._socket.dup())

    async def recv(self, maxsize, flags=0):
        while True:
            try:
                return self._socket.recv(maxsize, flags)
            except WantRead:
                await read_wait(self._socket, self._timeout)
            except WantWrite:
                await write_wait(self._socket, self._timeout)

    async def recv_into(self, buffer, nbytes=0, flags=0):
        while True:
            try:
                return self._socket.recv_into(buffer, nbytes, flags)
            except WantRead:
                await read_wait(self._socket, self._timeout)
            except WantWrite:
                await write_wait(self._socket, self._timeout)

    async def send(self, data, flags=0):
        while True:
            try:
                return self._socket.send(data, flags)
            except WantWrite:
                await write_wait(self._socket, self._timeout)
            except WantRead:
                await read_wait(self._socket, self._timeout)

    async def sendall(self, data, flags=0):
        buffer = memoryview(data).cast('b')
        while buffer:
            try:
                nsent = self._socket.send(buffer, flags)
                if nsent >= len(buffer):
                    return
                buffer = buffer[nsent:]
            except WantWrite:
                await write_wait(self._socket, self._timeout)
            except WantRead:
                await read_wait(self._socket, self._timeout)

    async def accept(self):
        while True:
            try:
                client, addr = self._socket.accept()
                return Socket(client), addr
            except WantRead:
                await read_wait(self._socket, self._timeout)

    async def connect(self, address):
        try:
            result = self._socket.connect(address)
            if getattr(self, 'do_handshake_on_connect', False):
                await self.do_handshake()
            return result
        except WantWrite:
            await write_wait(self._socket, self._timeout)
        err = self._socket.getsockopt(SOL_SOCKET, SO_ERROR)
        if err != 0:
            raise OSError(err, 'Connect call failed %s' % (address,))

    async def recvfrom(self, buffersize, flags=0):
        while True:
            try:
                return self._socket.recvfrom(buffersize, flags)
            except WantRead:
                await read_wait(self._socket, self._timeout)
            except WantWrite:
                await write_wait(self._socket, self._timeout)

    async def recvfrom_into(self, buffer, bytes=0, flags=0):
        while True:
            try:
                return self._socket.recvfrom_into(buffer, bytes, flags)
            except WantRead:
                await read_wait(self._socket, self._timeout)
            except WantWrite:
                await write_wait(self._socket, self._timeout)

    async def sendto(self, data, address):
        while True:
            try:
                return self._socket.sendto(data, address)
            except WantWrite:
                await write_wait(self._socket, self._timeout)
            except WantRead:
                await read_wait(self._socket, self._timeout)

    # Special functions for SSL
    async def do_handshake(self):
        while True:
            try:
                return self._socket.do_handshake()
            except WantRead:
                await read_wait(self._socket, self._timeout)
            except WantWrite:
                await write_wait(self._socket, self._timeout)

    def makefile(self, mode, buffering=0):
        if 'b' not in mode:
            raise RuntimeError('File can only be created in binary mode')
        f = self._socket.makefile(mode, buffering=buffering)
        return Stream(f)

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def __enter__(self):
        self._socket.__enter__()
        return self

    def __exit__(self, ety, eval, etb):
        self._socket.__exit__(ety, eval, etb)

class Stream(object):
    '''
    Wrapper around a file-like object.  File is put into non-blocking mode.
    The underlying file must be in binary mode.  
    '''
    def __init__(self, fileobj):
        assert not isinstance(fileobj, io.TextIOBase), 'Only binary mode files allowed'
        self._fileobj = fileobj
        os.set_blocking(fileobj.fileno(), False)
        self._linebuffer = bytearray()
        self._timeout = None

    def settimeout(self, timeout):
        self._timeout = timeout

    def fileno(self):
        return self._fileobj.fileno()

    async def _read(self, maxbytes=-1):
        while True:
            # In non-blocking mode, a file-like object might return None if no data is
            # available.  Alternatively, we'll catch the usual blocking exceptions just to be safe
            try:
                data = self._fileobj.read(maxbytes)
                if data is None:
                    await read_wait(self._fileobj, timeout=self._timeout)
                else:
                    return data
            except WantRead:
                await read_wait(self._fileobj, timeout=self._timeout)
            except WantWrite:
                await write_wait(self._fileobj, timeout=self._timeout)

    async def read(self, maxbytes=-1):
        if self._linebuffer:
            if maxbytes == -1:
                maxbytes = len(self._linebuffer)
            data = bytes(self._linebuffer[:maxbytes])
            del self._linebuffer[:maxbytes]
            return data
        else:
            return await self._read(maxbytes)

    async def readall(self):
        chunks = []
        while True:
            chunk = await self.read()
            if not chunk:
                return b''.join(chunks)
            chunks.append(chunk)

    async def readline(self):
        while True:
            nl_index = self._linebuffer.find(b'\n')
            if nl_index >= 0:
                resp = bytes(self._linebuffer[:nl_index+1])
                del self._linebuffer[:nl_index+1]
                return resp
            data = await self._read(1000)
            if data == b'':
                resp = bytes(self._linebuffer)
                del self._linebuffer[:]
                return resp
            self._linebuffer.extend(data)


    async def readlines(self):
        lines = []
        async for line in self:
            lines.append(line)
        return lines

    async def write(self, data):
        nwritten = 0
        view = memoryview(data).cast('b')
        while view:
            try:
                nbytes = self._fileobj.write(view)
                if nbytes is None:
                    raise BlockingIOError()
                nwritten += nbytes
                view = view[nbytes:]
            except WantWrite as e:
                if hasattr(e, 'characters_written'):
                    nwritten += e.characters_written
                    view = view[e.characters_written:]
                await write_wait(self._fileobj, timeout=self._timeout)
            except WantRead:
                await read_wait(self._fileobj, timeout=self._timeout)

        return nwritten

    async def writelines(self, lines):
        for line in lines:
            await self.write(line)

    async def flush(self):
        while True:
            try:
                return self._fileobj.flush() 
            except WantWrite:
                await write_wait(self._fileobj, timeout=self._timeout)
            except WantRead:
                await read_wait(self._fileobj, timeout=self._timeout)

    async def close(self):
        # Note: behavior of close() is broken on Python 3.5. See Issue #25476
        # Workaround is to call flush above first
        await self.flush()
        self._fileobj.close()

    def __getattr__(self, name):
        return getattr(self._fileobj, name)
        
    async def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.readline()
        if line:
            return line
        else:
            raise StopAsyncIteration

    def __iter__(self):
        raise RuntimeError('Use: async-for to iterate')

    async def __aenter__(self):
        self._fileobj.__enter__()
        return self

    async def __aexit__(self, *args):
        await self.close()
