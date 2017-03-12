# test_thread.py

import pytest
from curio import *
from curio.thread import AWAIT, AsyncThread, async_thread, async_context, async_iter
from curio.file import aopen

def simple_func(x, y):
    AWAIT(sleep(0.5))     # Execute a blocking operation
    return x + y

async def simple_coro(x, y):
    await sleep(0.5)
    return x + y

def test_good_result(kernel):
    async def main():
        t = AsyncThread(target=simple_func, args=(2, 3))
        await t.start()
        result = await t.join()
        assert result == 5

    kernel.run(main())

def test_bad_result(kernel):
    async def main():
        t = AsyncThread(target=simple_func, args=(2, '3'))
        await t.start()
        try:
            result = await t.join()
            assert False
        except TaskError as e:
            assert isinstance(e.__cause__, TypeError)
            assert True

    kernel.run(main())

def test_cancel_result(kernel):
    async def main():
        t = AsyncThread(target=simple_func, args=(2, 3))
        await t.start()
        await sleep(0.25)
        await t.cancel()
        try:
            result = await t.join()
            assert False
        except TaskError as e:
            assert isinstance(e.__cause__, TaskCancelled)
            assert True

    kernel.run(main())

def test_thread_good_result(kernel):
    def main():
        result = AWAIT(simple_coro(2, 3))
        assert result == 5

    kernel.run(async_thread(main)())

def test_thread_bad_result(kernel):
    def main():
        with pytest.raises(TypeError):
            result = AWAIT(simple_coro(2, '3'))

    kernel.run(async_thread(main)())

def test_thread_cancel_result(kernel):
    def func():
        with pytest.raises(TaskCancelled):
            result = AWAIT(simple_coro(2, 3))

    async def main():
        t = await spawn(async_thread(func))
        await sleep(0.25)
        await t.cancel()

    kernel.run(main())

def test_thread_sync(kernel):
    results = []
    def func(lock):
        with lock:
            results.append('func')

    async def main():
        lock = Lock()
        async with lock:
            results.append('main')
            t = await spawn(async_thread(func), lock)
            await sleep(0.5)
            results.append('main done')
        await t.join()
        
    kernel.run(main())
    assert results == [ 'main', 'main done', 'func' ]


def test_thread_timeout(kernel):
    def func():
        with pytest.raises(TaskTimeout):
            with timeout_after(1):
                AWAIT(sleep(2))

    kernel.run(async_thread(func)())


def test_thread_disable_cancellation(kernel):
    def func():
        with disable_cancellation():
            AWAIT(sleep(1))
            assert True

            with enable_cancellation():
                AWAIT(sleep(2))

            assert isinstance(AWAIT(check_cancellation()), TaskTimeout)

        with pytest.raises(TaskTimeout):
            AWAIT(sleep(2))

    async def main():
        t = await spawn(async_thread(func))
        await sleep(0.5)
        await t.cancel()

    kernel.run(main())

import os
dirname = os.path.dirname(__file__)
testinput = os.path.join(dirname, 'testdata.txt')

def test_thread_read(kernel):
    def func():
        with aopen(testinput, 'r') as f:
            data = AWAIT(f.read())
            assert f.closed == False

        assert data == 'line 1\nline 2\nline 3\n'

    async def main():
        t = await spawn(async_thread(func))
        await t.join()

    kernel.run(main())

import curio.subprocess as subprocess
import sys

def test_subprocess_popen(kernel):
    def func():
        with subprocess.Popen([sys.executable, '-c', 'print("hello")'], stdout=subprocess.PIPE) as p:
            data = AWAIT(p.stdout.read())
            assert data == b'hello\n'

    async def main():
        t = await spawn(async_thread(func))
        await t.join()

    kernel.run(main())
    
def test_async_context_iter(kernel):

    ran = False

    @async_thread(daemon=True)
    def func():
        nonlocal ran
        f = aopen(testinput, 'r')
        result = []
        with async_context(f) as g:
            for line in async_iter(g):
                result.append(line)

        assert result == ['line 1\n', 'line 2\n', 'line 3\n']
        ran = True

    async def main():
        await func()
        assert ran


    AWAIT(kernel.run(main()))


            
                 


