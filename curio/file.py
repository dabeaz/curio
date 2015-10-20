# curio/file.py

import io
from .kernel import read_wait, write_wait

__all__ = ['File']

class File(object):
    '''
    Wrapper around a file-like object.  File must be in non-blocking mode already.
    '''
    def __init__(self, fileobj):
        assert isinstance(fileobj, io.RawIOBase), 'File object must be unbuffered binary'
        self._fileobj = fileobj
        self._fileno = fileobj.fileno()
        self._linebuffer = bytearray()

    def fileno(self):
        return self._fileno.fileno()

    async def _read(self, maxbytes=-1):
        while True:
            # In non-blocking mode, a file-like object might return None if no data is
            # available.  Alternatively, we'll catch BlockingIOError just to be safe.
            try:
                data = self._fileobj.read(maxbytes)
                if data is not None:
                    return data
            except BlockingIOError:
                pass
            await read_wait(self._fileobj)

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

    async def write(self, data, *, close_on_complete=False):
        nwritten = 0
        view = memoryview(data).cast('b')
        while view:
            try:
                nbytes = self._fileobj.write(view)
                if nbytes is None:
                    raise BlockingIOError()
                nwritten += nbytes
                view = view[nbytes:]
            except BlockingIOError:
                await write_wait(self._fileobj)

        if close_on_complete:
            self.close()

        return nwritten

    async def writelines(self, lines):
        for line in lines:
            await self.write(line)

    def flush(self):
        pass

    def __getattr__(self, name):
        return getattr(self._fileobj, name)

    async def __aenter__(self):
        self._fileobj.__enter__()
        return self

    async def __aexit__(self, *args):
        self._fileobj.__exit__(*args)
        
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

    def __enter__(self):
        self._fileobj.__enter__()
        return self

    def __exit__(self, *args):
        self._fileobj.__exit__(*args)

