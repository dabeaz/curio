# channel.py
#
# Support for a message passing channel that can send bytes or pickled
# Python objects on a stream.  Similar to the Connection class in the
# multiprocessing module.
#
# WARNING: This module is experimental, undocumented, and may be removed
# or rewritten at any time.

import os
import pickle
import struct
import io
import hmac
from . import socket

from .kernel import _write_wait, _read_wait, CurioError
from .io import Stream
from .meta import DualIO, awaitable

__all__ = ['Channel']

# Authentication parameters
AUTH_MESSAGE_LENGTH = 20
CHALLENGE = b'#CHALLENGE#'
WELCOME = b'#WELCOME#'
FAILURE = b'#FAILURE#'

class AuthenticationError(CurioError):
    pass

class Channel(DualIO):
    '''
    A communication channel for sending size-prefixed messages of bytes
    or pickled Python objects.  Must be passed a pair of reader/writer
    streams for performing the underlying communication.
    '''
    def __init__(self, reader, writer):
        assert isinstance(reader, Stream) and isinstance(writer, Stream)
        self._reader = reader
        self._writer = writer

    async def close(self):
        await self._reader.close()
        await self._writer.close()

    def close(self):
        with self._reader.blocking() as r:
            r.close()
        with self._writer.blocking() as w:
            w.close()

    async def send_bytes(self, buf):
        '''
        Send a buffer of bytes as a single message
        '''
        size = len(buf)
        header = struct.pack('!I', size)
        if size >= 16384:
            await self._writer.write(header)
        else:
            buf = header + bytes(buf)

        await self._writer.write(buf)

    def send_bytes(self, buf):
        with self._writer.blocking() as writer:
            size = len(buf)
            header = struct.pack('!I', size)
            if size >= 16384:
                writer.write(header)
            else:
                buf = header + bytes(buf)
            writer.write(buf)

    async def recv_bytes(self, *, maxsize=None):
        '''
        Receive a message of bytes as a single message.
        '''
        header = await self._reader.read_exactly(4)
        size,  = struct.unpack('!I', header)
        if maxsize is not None:
            if size > maxsize:
                raise IOError('Message too large. %d bytes > %d maxsize' % (size, maxsize))

        msg = await self._reader.read_exactly(size)
        return msg

    def recv_bytes(self, *, maxsize=None):
        with self._reader.blocking() as reader:
            header = reader.read(4)
            if len(header) != 4:
                raise EOFError('Connection terminated')
            size,  = struct.unpack('!I', header)
            if maxsize is not None:
                if size > maxsize:
                    raise IOError('Message too large. %d bytes > %d maxsize' % (size, maxsize))

            msg = reader.read(size)
            return msg

    async def send(self, obj):
        '''
        Send an arbitrary Python object. Uses pickle to serialize.
        '''
        await self.send_bytes(pickle.dumps(obj))

    def send(self, obj):
        self.send_bytes(pickle.dumps(obj))

    async def recv(self):
        '''
        Receive a Python object. Uses pickle to unserialize.
        '''
        msg = await self.recv_bytes()
        return pickle.loads(msg)

    def recv(self):
        msg = self.recv_bytes()
        return pickle.loads(msg)

    async def _deliver_challenge(self, authkey):
        message = os.urandom(AUTH_MESSAGE_LENGTH)
        await self.send_bytes(CHALLENGE + message)
        digest = hmac.new(authkey, message, 'md5').digest()
        response = await self.recv_bytes(maxsize=256)
        if response == digest:
            await self.send_bytes(WELCOME)
        else:
            await self.send_bytes(FAILURE)
            raise AuthenticationError('digest received was wrong')

    def _deliver_challenge(self, authkey):
        message = os.urandom(AUTH_MESSAGE_LENGTH)
        self.send_bytes(CHALLENGE + message)
        digest = hmac.new(authkey, message, 'md5').digest()
        response = self.recv_bytes(maxsize=256)
        if response == digest:
            self.send_bytes(WELCOME)
        else:
            self.send_bytes(FAILURE)
            raise AuthenticationError('digest received was wrong')

    async def _answer_challenge(self, authkey):
        message = await self.recv_bytes(maxsize=256)
        assert message[:len(CHALLENGE)] == CHALLENGE, 'message = %r' % message
        message = message[len(CHALLENGE):]
        digest = hmac.new(authkey, message, 'md5').digest()
        await self.send_bytes(digest)
        response = await self.recv_bytes(maxsize=256)

        if response != WELCOME:
            raise AuthenticationError('digest sent was rejected')

    def _answer_challenge(self, authkey):
        message = self.recv_bytes(maxsize=256)
        assert message[:len(CHALLENGE)] == CHALLENGE, 'message = %r' % message
        message = message[len(CHALLENGE):]
        digest = hmac.new(authkey, message, 'md5').digest()
        self.send_bytes(digest)
        response = self.recv_bytes(maxsize=256)

        if response != WELCOME:
            raise AuthenticationError('digest sent was rejected')

    async def authenticate_server(self, authkey):
        await self._deliver_challenge(authkey)
        await self._answer_challenge(authkey)

    def authenticate_server(self, authkey):
        self._deliver_challenge(authkey)
        self._answer_challenge(authkey)

    async def authenticate_client(self, authkey):
        await self._answer_challenge(authkey)
        await self._deliver_challenge(authkey)

    def authenticate_client(self, authkey):
        self._answer_challenge(authkey)
        self._deliver_challenge(authkey)

class Listener(DualIO):
    def __init__(self, address, family=socket.AF_INET, backlog=1, authkey=None):
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        if family == socket.AF_INET:
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self._sock.bind(address)
        self._sock.listen(backlog)
        self._authkey = authkey

    async def accept(self):
        client, addr = await self._sock.accept()
        fileno = client.detach()
        ch = Channel(Stream(open(fileno, 'rb', buffering=0)),
                     Stream(open(fileno, 'wb', buffering=0, closefd=False)))
        if self._authkey:
            await ch.authenticate_server(self._authkey)
        return ch

    def accept(self):
        with self._sock.blocking() as sock:
            client, addr = sock.accept()
            fileno = client.detach()
            ch = Channel(Stream(open(fileno, 'rb', buffering=0)),
                         Stream(open(fileno, 'wb', buffering=0, closefd=False)))
            if self._authkey:
                ch.authenticate_server(self._authkey)
        return ch

    async def close(self):
        await self._sock.close()

    def close(self):
        with self._sock.blocking() as sock:
            sock.close()


def Client(address, family=socket.AF_INET, authkey=None):
    sock = socket.socket(family, socket.SOCK_STREAM)
    with sock.blocking() as _sock:
        _sock.connect(address)

        fileno = sock.detach()
        ch = Channel(Stream(open(fileno, 'rb', buffering=0)),
                     Stream(open(fileno, 'wb', buffering=0, closefd=False)))
        if authkey:
            ch.authenticate_client(authkey)
        return ch

@awaitable(Client)
async def Client(address, family=socket.AF_INET, authkey=None):
    sock = socket.socket(family, socket.SOCK_STREAM)
    await sock.connect(address)
    fileno = sock.detach()
    ch = Channel(Stream(open(fileno, 'rb', buffering=0)),
                 Stream(open(fileno, 'wb', buffering=0, closefd=False)))
    if authkey:
        await ch.authenticate_client(authkey)
    return ch
