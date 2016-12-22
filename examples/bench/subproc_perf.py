# subproc_perf.py

from curio import *
from curio.subprocess import check_output
import time
import subprocess
import asyncio

COUNT = 1000

input = (b'aaa ' * 10 + b'\n') * 10000
cmd = ['cat']

async def main(n):
    for x in range(n):
        out = await check_output(cmd, input=input)
    assert out == input


def curio_test(n):
    start = time.time()
    run(main(n))
    end = time.time()
    print('curio:', end - start)


def subprocess_test(n):
    start = time.time()
    for x in range(n):
        out = subprocess.check_output(cmd, input=input)
    assert out == input
    end = time.time()
    print('subprocess:', end - start)


def asyncio_test(n):
    async def main(n):
        for x in range(n):
            proc = await asyncio.create_subprocess_exec(*cmd,
                                                        stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate(input=input)
            await proc.wait()
        assert stdout == input

    loop = asyncio.get_event_loop()
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(n)))
    end = time.time()
    print('asyncio:', end - start)


def uvloop_test(n):
    try:
        import uvloop
    except ImportError:
        return

    async def main(n):
        for x in range(n):
            proc = await asyncio.create_subprocess_exec(*cmd,
                                                        stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate(input=input)
            await proc.wait()
        assert stdout == input

    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(n)))
    end = time.time()
    print('uvloop:', end - start)

if __name__ == '__main__':
    curio_test(COUNT)
    subprocess_test(COUNT)
    asyncio_test(COUNT)
    uvloop_test(COUNT)
