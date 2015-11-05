# curio/io.py
#
# I/O wrapper objects.
# 
# Copyright (C) 2015
# David Beazley (Dabeaz LLC)
# All rights reserved.
#
# Let's talk about design for a moment...
#
# Curio is primarily concerned with the scheduling of tasks. In
# particular, the kernel does not actually perform any I/O.  It merely
# blocks tasks that need to wait for reading or writing.  To actually
# perform I/O, you use the existing file and socket abstractions
# already provided by the Python standard library.  The only
# difference is that you need to take extra steps to manage their
# non-blocking behavior.  The classes in this file provide wrappers
# around socket-like and file-like objects. Methods responsible for
# reading/writing have a small amount of extra logic to added to
# handle their scheduling.  Other methods are simply passed through to
# the original object via delegation.
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
# on the provided file or socket?  If so, it will probably work here.

from .kernel import _read_wait, _write_wait

from socket import SOL_SOCKET, SO_ERROR
from contextlib import contextmanager

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

# There is a certain amount of repetition in this class.  It can
# probably be shortened with some sort of decorator magic. On the
# other, the KISSS (Keep it Stupid Simple Stupid) principle might be a
# better policy--just in case someone needs to debug it.

class Socket(object):
    '''
    Non-blocking wrapper around a socket object.   The original socket is put
    into a non-blocking mode when it's wrapped.
    '''
    def __init__(self, sock):
        self._socket = sock
        self._socket.setblocking(False)
        self._timeout = None
        self._fileno = sock.fileno()

    def __repr__(self):
        return '<curio.Socket %r>' % (self._socket)

    def __getattr__(self, name):
        return getattr(self._socket, name)
            
    def fileno(self):
        return self._fileno

    def settimeout(self, seconds):
        self._timeout = seconds

    def dup(self):
        return Socket(self._socket.dup())

    def makefile(self, mode, buffering=0, *, encoding=None, errors=None, newline=None):
        if 'b' not in mode:
            raise RuntimeError('File can only be created in binary mode')
        f = self._socket.makefile(mode, buffering=buffering)
        return Stream(f)

    def make_streams(self, buffering=0):
        return (
            self.makefile('rb', buffering), 
            self.makefile('wb', buffering)
            )

    @contextmanager
    def blocking(self):
        '''
        Allow temporary access to the underlying socket in blocking mode
        '''
        try:
            self._socket.setblocking(True)
            yield self._socket
        finally:
            self._socket.setblocking(False)

    async def recv(self, maxsize, flags=0):
        while True:
            try:
                return self._socket.recv(maxsize, flags)
            except WantRead:
                await _read_wait(self._socket, self._timeout)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)

    async def recv_into(self, buffer, nbytes=0, flags=0):
        while True:
            try:
                return self._socket.recv_into(buffer, nbytes, flags)
            except WantRead:
                await _read_wait(self._socket, self._timeout)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)

    async def send(self, data, flags=0):
        while True:
            try:
                return self._socket.send(data, flags)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)
            except WantRead:
                await _read_wait(self._socket, self._timeout)

    async def sendall(self, data, flags=0):
        buffer = memoryview(data).cast('b')
        while buffer:
            try:
                nsent = self._socket.send(buffer, flags)
                if nsent >= len(buffer):
                    return
                buffer = buffer[nsent:]
            except WantWrite:
                await _write_wait(self._socket, self._timeout)
            except WantRead:
                await _read_wait(self._socket, self._timeout)

    async def accept(self):
        while True:
            try:
                client, addr = self._socket.accept()
                return Socket(client), addr
            except WantRead:
                await _read_wait(self._socket, self._timeout)

    async def connect_ex(self, address):
        try:
            await self.connect(address)
            return 0
        except OSError as e:
            return e.errno

    async def connect(self, address):
        try:
            result = self._socket.connect(address)
            if getattr(self, 'do_handshake_on_connect', False):
                await self.do_handshake()
            return result
        except WantWrite:
            await _write_wait(self._socket, self._timeout)
        err = self._socket.getsockopt(SOL_SOCKET, SO_ERROR)
        if err != 0:
            raise OSError(err, 'Connect call failed %s' % (address,))
        if getattr(self, 'do_handshake_on_connect', False):
            await self.do_handshake()

    async def recvfrom(self, buffersize, flags=0):
        while True:
            try:
                return self._socket.recvfrom(buffersize, flags)
            except WantRead:
                await _read_wait(self._socket, self._timeout)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)

    async def recvfrom_into(self, buffer, bytes=0, flags=0):
        while True:
            try:
                return self._socket.recvfrom_into(buffer, bytes, flags)
            except WantRead:
                await _read_wait(self._socket, self._timeout)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)

    async def sendto(self, bytes, flags_or_address, address=None):
        if address:
            flags = flags_or_address
        else:
            address = flags_or_address
            flags = 0
        while True:
            try:
                return self._socket.sendto(bytes, flags, address)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)
            except WantRead:
                await _read_wait(self._socket, self._timeout)

    async def recvmsg(self, bufsize, ancbufsize=0, flags=0):
        while True:
            try:
                return self._socket.recvmsg(bufsize, ancbufsize, flags)
            except WantRead:
                await _read_wait(self._socket, self._timeout)

    async def recvmsg_into(self, buffers, ancbufsize=0, flags=0):
        while True:
            try:
                return self._socket.recvmsg_into(buffers, ancbufsize, flags)
            except WantRead:
                await _read_wait(self._socket, self._timeout)

    async def sendmsg(self, buffers, ancdata=(), flags=0, address=None):
        while True:
            try:
                return self._socket.sendmsg(buffers, ancdata, flags, address)
            except WantRead:
                await _write_wait(self._socket, self._timeout)
    
    # Special functions for SSL
    async def do_handshake(self):
        while True:
            try:
                return self._socket.do_handshake()
            except WantRead:
                await _read_wait(self._socket, self._timeout)
            except WantWrite:
                await _write_wait(self._socket, self._timeout)

            
    # Design discussion.  Why make close() async?   Partly it's to make the
    # programming interface highly uniform with the other methods (all of which
    # involve an await).  It's also to provide consistency with the Stream
    # API below which requires an asynchronous close to properly flush I/O
    # buffers.

    async def close(self):
        self._socket.close()

    async def __aenter__(self):
        self._socket.__enter__()
        return self

    async def __aexit__(self, *args):
        self._socket.__exit__(*args)
      
    def __enter__(self):
        raise RuntimeError('Use async-with for context management')

    def __exit__(self, *args):
        pass

class Stream(object):
    '''
    Wrapper around a file-like object.  File is put into non-blocking mode.
    The underlying file must be in binary mode.  
    '''
    def __init__(self, fileobj):
        assert not isinstance(fileobj, io.TextIOBase), 'Only binary mode files allowed'
        self._file = fileobj
        self._fileno = fileobj.fileno()
        os.set_blocking(self._fileno, False)
        self._linebuffer = bytearray()
        self._timeout = None

    def __repr__(self):
        return '<curio.Stream %r>' % (self._file)

    def __getattr__(self, name):
        return getattr(self._file, name)

    def fileno(self):
        return self._fileno

    def settimeout(self, timeout):
        self._timeout = timeout

    @contextmanager
    def blocking(self):
        '''
        Allow temporary access to the underlying socket in blocking mode
        '''
        try:
            os.set_blocking(self._fileno, True)
            yield self._file
        finally:
            os.set_blocking(self._fileno, False)

    async def _read(self, maxbytes=-1):
        while True:
            # In non-blocking mode, a file-like object might return None if no data is
            # available.  Alternatively, we'll catch the usual blocking exceptions just to be safe
            try:
                data = self._file.read(maxbytes)
                if data is None:
                    await _read_wait(self._file, timeout=self._timeout)
                else:
                    return data
            except WantRead:
                await _read_wait(self._file, timeout=self._timeout)
            except WantWrite:
                await _write_wait(self._file, timeout=self._timeout)

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
                nbytes = self._file.write(view)
                if nbytes is None:
                    raise BlockingIOError()
                nwritten += nbytes
                view = view[nbytes:]
            except WantWrite as e:
                if hasattr(e, 'characters_written'):
                    nwritten += e.characters_written
                    view = view[e.characters_written:]
                await _write_wait(self._file, timeout=self._timeout)
            except WantRead:
                await _read_wait(self._file, timeout=self._timeout)

        return nwritten

    async def writelines(self, lines):
        for line in lines:
            await self.write(line)

    async def flush(self):
        while True:
            try:
                return self._file.flush() 
            except WantWrite:
                await _write_wait(self._file, timeout=self._timeout)
            except WantRead:
                await _read_wait(self._file, timeout=self._timeout)

    # Why async close()?   If the underlying file is buffered, the contents need
    # to be flushed first--a process that might cause a BlockingIOError.  In
    # that case, we have to suspend briefly until the buffers free up space.

    async def close(self):
        await self.flush()
        self._file.close()
        self._fileno = -1
        
    async def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.readline()
        if line:
            return line
        else:
            raise StopAsyncIteration

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    def __iter__(self):
        raise RuntimeError('Use: async-for to iterate')

    def __enter__(self):
        raise RuntimeError('Use: async-with for context management')

    def __exit__(self, *args):
        pass
