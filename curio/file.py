# curio/file.py

import os
from types import coroutine

__all__ = ['File']

class File(object):
    '''
    Wrapper around file objects.  Proof of concept. Needs to be redone
    '''
    def __init__(self, fileno):

        if not isinstance(fileno, int):
            fileno = fileno.fileno()

        self._fileno = fileno
        os.set_blocking(fileno, False)
        self._linebuffer = bytearray()
        self.closed = False

    def fileno(self):
        return self._fileno

    @coroutine
    def read(self, maxbytes):
        while True:
            try:
                return os.read(self._fileno, maxbytes)
            except BlockingIOError:
                yield 'trap_read_wait', self

    async def readline(self):
        while True:
            nl_index = self._linebuffer.find(b'\n')
            if nl_index >= 0:
                resp = bytes(self._linebuffer[:nl_index+1])
                del self._linebuffer[:nl_index+1]
                return resp
            data = await self.read(1000)
            if not data:
                resp = bytes(self._linebuffer)
                del self._linebuffer[:]
                return resp
            self._linebuffer.extend(data)

    @coroutine
    def write(self, data):
        nwritten = 0
        while data:
            try:
                nbytes = os.write(self._fileno, data)
                nwritten += nbytes
                data = data[nbytes:]
            except BlockingIOError:
                yield 'trap_write_wait', self

        return nwritten

    async def writelines(self, lines):
        for line in lines:
            await self.write(line)

    def close(self):
        os.close(self._fileno)
        self.closed = True

    async def flush(self):
        pass
