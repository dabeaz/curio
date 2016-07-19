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

def test_read_context(kernel):
    async def main():
        async with await aopen(os.path.join(dirname, 'testdata.txt'), 'r') as f:
            data = await f.read()
        assert data == 'line 1\nline 2\nline 3\n'
        assert f.closed

    kernel.run(main())

def test_readlines(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = await f.readlines()
        await f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

def test_readiter(kernel):
    async def main():
        f = await aopen(os.path.join(dirname, 'testdata.txt'), 'r')
        lines = []
        async for line in f:
            lines.append(line)
        await f.close()

        assert lines == ['line 1\n', 'line 2\n', 'line 3\n']

    kernel.run(main())

