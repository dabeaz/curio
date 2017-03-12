# test_file.py

import os.path
from curio import *
import pytest

dirname = os.path.dirname(__file__)
testinput = os.path.join(dirname, 'testdata.txt')


def test_read(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            data = await f.read()
            assert f.closed == False

        assert data == 'line 1\nline 2\nline 3\n'

    kernel.run(main())


def test_read1(kernel):
    async def main():
        async with aopen(testinput, 'rb') as f:
            data = await f.read1(1000)
        assert data == b'line 1\nline 2\nline 3\n'

    kernel.run(main())


def test_readinto(kernel):
    async def main():
        async with aopen(testinput, 'rb') as f:
            buf = bytearray(1000)
            n = await f.readinto(buf)
        assert buf[:n] == b'line 1\nline 2\nline 3\n'

    kernel.run(main())


def test_readinto1(kernel):
    async def main():
        async with aopen(testinput, 'rb') as f:
            buf = bytearray(1000)
            n = await f.readinto1(buf)
        assert buf[:n] == b'line 1\nline 2\nline 3\n'

    kernel.run(main())


def test_readline(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            lines = []
            while True:
                line = await f.readline()
                if not line:
                    break
                lines.append(line)

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())


def test_readlines(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            lines = await f.readlines()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())


def test_readiter(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            lines = []
            async for line in f:
                lines.append(line)

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

def test_read_anext(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            lines = []
            while True:
                line = await anext(f, '')
                if not line:
                    break
                lines.append(line)

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

def test_read_anext2(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            lines = []
            with pytest.raises(StopAsyncIteration):
                while True:
                    line = await anext(f)
                    lines.append(line)

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

def test_bad_usage(kernel):
    async def main():
        f = aopen(testinput, 'r')
        with pytest.raises(RuntimeError):
            await f.read()

wlines = ['line1\n', 'line2\n', 'line3\n']


def test_write(kernel):
    async def main():
        outname = os.path.join(dirname, 'tmp.txt')
        async with aopen(outname, 'w') as f:
            outdata = ''.join(wlines)
            await f.write(outdata)
            await f.flush()

        assert open(outname).read() == outdata

    kernel.run(main())


def test_writelines(kernel):
    async def main():
        outname = os.path.join(dirname, 'tmp.txt')
        async with aopen(outname, 'w') as f:
            await f.writelines(wlines)

        assert open(outname).readlines() == wlines

    kernel.run(main())


def test_seek_tell(kernel):
    async def main():
        async with aopen(testinput, 'rb') as f:
            await f.seek(10)
            n = await f.tell()
            assert n == 10
            data = await f.read()

        assert data == b'line 1\nline 2\nline 3\n'[10:]

    kernel.run(main())

def test_truncate(kernel):
    async def main():
        outname = os.path.join(dirname, 'tmp.txt')
        async with aopen(outname, 'wb') as f:
            await f.write(b'12345')
            await f.flush()
            assert await f.tell() == 5
            await f.truncate(2)
            await f.seek(2)
            await f.write(b'6789')
            await f.close()
        async with aopen(outname, 'rb') as f:
            data = await f.read()
            assert data == b'126789'

    kernel.run(main())

def test_sync_iter(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            try:
                for line in f:
                    pass

                assert False, 'sync-iteration should have failed'
            except SyncIOError:
                assert True

    kernel.run(main())


def test_sync_with(kernel):
    async def main():
        f = aopen(testinput, 'r')
        try:
            with f:
                pass
            assert False, 'sync-with should have failed'
        except AsyncOnlyError:
            assert True

    kernel.run(main())

def test_must_be_asynccontext(kernel):
    async def main():
        f = aopen(testinput, 'r')
        with pytest.raises(RuntimeError):
            data = await f.read()

    kernel.run(main())

def test_blocking(kernel):
    async def main():
        async with aopen(testinput, 'r') as f:
            with f.blocking() as sync_f:
                data = sync_f.read()

        assert data == 'line 1\nline 2\nline 3\n'

    kernel.run(main())

def test_file_misc(kernel):
    async def main():
        f = aopen(testinput, 'r')
        repr(f)
        with pytest.raises(SyncIOError):
            next(f)

    kernel.run(main())
