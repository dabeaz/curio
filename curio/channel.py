# channel.py
#
# Support for a message passing channel that can send bytes or
# pickled Python objects.  Similar to the Connection class in the
# multiprocessing module.

import os
import pickle
import struct
import io
import hmac
import socket

from .kernel import _write_wait, _read_wait, CurioError

__all__ = ['Channel']

# Authentication parameters
AUTH_MESSAGE_LENGTH = 20
CHALLENGE = b'#CHALLENGE#'
WELCOME = b'#WELCOME#'
FAILURE = b'#FAILURE#'

class AuthenticationError(CurioError):
    pass

class Channel(object):
    '''
    A communication channel for sending size-prefixed messages of bytes
    or pickled Python objects.
    '''

    def __init__(self, fileno):
        self.fileno = fileno

    async def _recv_exactly(self, remaining):
        '''
        Receive an exact number of bytes (internal function)
        '''
        result = io.BytesIO()
        while remaining:
            try:
                chunk = os.read(self.fileno, remaining)
                result.write(chunk)
                remaining -= len(chunk)
            except BlockingIOError:
                await _read_wait(self.fileno)
        return result

    async def send_bytes(self, buf):
        '''
        Send a buffer of bytes as a single message
        '''
        size = len(buf)
        header = struct.pack('!I', size)
        if size >= 16384:
            while header:
                try:
                    nsent = os.write(self.fileno, header)
                    header = header[nsent:]
                except BlockingIOError:
                    await _write_wait(self.fileno)

        else:
            buf = header + bytes(buf)

        m = memoryview(buf)
        while m:
            try:
                nsent = os.write(self.fileno, m)
                m = m[nsent:]
            except BlockingIOError:
                await _write_wait(self.fileno)

    async def recv_bytes(self, *, maxsize=None):
        '''
        Receive a message of bytes as a single message.
        '''
        header = await self._recv_exactly(4)
        size,  = struct.unpack('!I', header.getvalue())
        if maxsize is not None:
            if size > maxsize:
                raise IOError('Message too large. %d bytes > %d maxsize' % (size, maxsize))

        msg = await self._recv_exactly(size)
        return msg.getvalue()

    async def send(self, obj):
        '''
        Send an arbitrary Python object. Uses pickle to serialize.
        '''
        await self.send_bytes(pickle.dumps(obj))

    async def recv(self):
        '''
        Receive a Python object. Uses pickle to unserialize.
        '''
        msg = await self.recv_bytes()
        return pickle.loads(msg)

    async def deliver_challenge(self, authkey):
        message = os.urandom(AUTH_MESSAGE_LENGTH)
        await self.send_bytes(CHALLENGE + message)
        digest = hmac.new(authkey, message, 'md5').digest()
        response = await self.recv_bytes(maxsize=256)
        if response == digest:
            await self.send_bytes(WELCOME)
        else:
            await self.send_bytes(FAILURE)
            raise AuthenticationError('digest received was wrong')

    async def answer_challenge(self, authkey):
        message = await self.recv_bytes(maxsize=256)
        assert message[:len(CHALLENGE)] == CHALLENGE, 'message = %r' % message
        message = message[len(CHALLENGE):]
        digest = hmac.new(authkey, message, 'md5').digest()
        await self.send_bytes(digest)
        response = await self.recv_bytes(maxsize=256)

        if response != WELCOME:
            raise AuthenticationError('digest sent was rejected')

    async def close(self):
        os.close(self.fileno)

class Listener(object):
    def __init__(self, address, family=socket.AF_INET, backlog=1, authkey=None):
        self._sock = socket.socket(family, socket.SOCK_STREAM)
        self._sock.bind(address)
        self._sock.listen(backlog)
        self._sock.setblocking(False)
        self._authkey = authkey

    async def accept(self):
        pass
    async def close(self):
        pass

def Client(address, family=socket.AF_INET, authkey=None):
    pass
