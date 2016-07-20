# test_file.py

import os.path
from curio import *

dirname = os.path.dirname(__file__)

def test_read(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        data = await f.read()
        await f.close()
        assert data == 'line 1\nline 2\nline 3\n'

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        data = f.read()
        f.close()
        assert data == 'line 1\nline 2\nline 3\n'

    syncmain()

def test_read_context(kernel):
    async def main():
        async with await aopen(os.path.join(dirname, 'testdata.txt'), 'r') as f:
            data = await f.read()
        assert data == 'line 1\nline 2\nline 3\n'
        assert f.closed

    kernel.run(main())

    def syncmain():
        with aopen(os.path.join(dirname, 'testdata.txt'), 'r') as f:
            data = f.read()
        assert data == 'line 1\nline 2\nline 3\n'
        assert f.closed

    syncmain()

def test_read1(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        data = await f.read1(1000)
        await f.close()
        assert data == b'line 1\nline 2\nline 3\n'

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        data = f.read1(1000)
        f.close()
        assert data == b'line 1\nline 2\nline 3\n'

    syncmain()

def test_readinto(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        buf = bytearray(1000)
        n = await f.readinto(buf)
        await f.close()
        assert buf[:n] == b'line 1\nline 2\nline 3\n'

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        buf = bytearray(1000)
        n = f.readinto(buf)
        f.close()
        assert buf[:n] == b'line 1\nline 2\nline 3\n'

    syncmain()

def test_readinto1(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        buf = bytearray(1000)
        n = await f.readinto1(buf)
        await f.close()
        assert buf[:n] == b'line 1\nline 2\nline 3\n'

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        buf = bytearray(1000)
        n = f.readinto1(buf)
        f.close()
        assert buf[:n] == b'line 1\nline 2\nline 3\n'

    syncmain()

def test_readline(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = []
        while True:
            line = await f.readline()
            if not line:
                break
            lines.append(line)
        await f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = []
        while True:
            line = f.readline()
            if not line:
                break
            lines.append(line)
        f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    syncmain()


def test_readlines(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = await f.readlines()
        await f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = f.readlines()
        f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    syncmain()


def test_readiter(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = []
        async for line in f:
            lines.append(line)
        await f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = []
        for line in f:
            lines.append(line)
        f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    syncmain()


wlines = ['line1\n', 'line2\n', 'line3\n']

def test_write(kernel):
    async def main():
        outname = os.path.join(dirname, 'tmp.txt')
        f = await aopen(outname, 'w')
        outdata = ''.join(wlines)
        await f.write(outdata)
        await f.flush()
        await f.close()
        assert open(outname).read() == outdata

    kernel.run(main())

    def syncmain():
        outname = os.path.join(dirname, 'tmp.txt')
        f = aopen(outname, 'w')
        outdata = ''.join(wlines)
        f.write(outdata)
        f.flush()
        f.close()
        assert open(outname).read() == outdata

    syncmain()

def test_writelines(kernel):
    async def main():
        outname = os.path.join(dirname, 'tmp.txt')
        f = await aopen(outname, 'w')
        await f.writelines(wlines)
        await f.close()
        assert open(outname).readlines() == wlines

    kernel.run(main())

    def syncmain():
        outname = os.path.join(dirname, 'tmp.txt')
        f = aopen(outname, 'w')
        f.writelines(wlines)
        f.close()
        assert open(outname).readlines() == wlines
        
    syncmain()


def test_seek_tell(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        await f.seek(10)
        n = await f.tell()
        assert n == 10
        data = await f.read()
        await f.close()
        assert data == b'line 1\nline 2\nline 3\n'[10:]

    kernel.run(main())

    def syncmain():
        f = aopen(os.path.join(dirname, 'testdata.txt'), 'rb')
        f.seek(10)
        n = f.tell()
        assert n == 10
        data = f.read()
        f.close()
        assert data == b'line 1\nline 2\nline 3\n'[10:]

    syncmain()

def test_sync_iter(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        try:
           for line in f:
               pass

           assert False, 'sync-iteration should have failed'
        except SyncIOError:
            assert True

    kernel.run(main())

def test_sync_with(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        try:
           with f:
               pass
           assert False, 'sync-with should have failed'
        except SyncIOError:
            assert True

    kernel.run(main())
    
