# test_thread.py

import pytest
from curio import *
from curio.thread import AWAIT, spawn_thread, is_async_thread
from curio.file import aopen
import time
import pytest


def simple_func(x, y):
    assert is_async_thread()
    AWAIT(sleep(0.25))     # Execute a blocking operation
    AWAIT(sleep, 0.25)     # Alternative
    return x + y

async def simple_coro(x, y):
    await sleep(0.5)
    return x + y

def test_good_result(kernel):
    async def main():
        t = await spawn_thread(simple_func, 2, 3)
        result = await t.join()
        assert result == 5
        assert t.result == 5
        assert t.exception is None

    kernel.run(main)

def test_bad_result(kernel):
    async def main():
        t = await spawn_thread(simple_func, 2, '3')
        try:
            result = await t.join()
            assert False
        except TaskError as e:
            assert isinstance(e.__cause__, TypeError)
            assert True
        else:
            assert False

        try:
            result = await t.result
            assert False
        except TypeError as e:
            assert True
        else:
            assert False

    kernel.run(main)

def test_cancel_result(kernel):
    async def main():
        t = await spawn_thread(simple_func, 2, 3)
        await sleep(0.25)
        await t.cancel()
        try:
            result = await t.join()
            assert False
        except TaskError as e:
            assert isinstance(e.__cause__, TaskCancelled)
            assert True
    kernel.run(main)

def test_thread_good_result(kernel):
    def coro():
        result = AWAIT(simple_coro(2, 3))
        return result

    async def main():
        t = await spawn_thread(coro)
        result = await t.join()
        assert result == 5

    kernel.run(main)

def test_thread_bad_result(kernel):
    def coro():
        with pytest.raises(TypeError):
            result = AWAIT(simple_coro(2, '3'))

    async def main():
        t = await spawn_thread(coro)
        await t.join()

    kernel.run(main)

def test_thread_cancel_result(kernel):
    def func():
        with pytest.raises(TaskCancelled):
            result = AWAIT(simple_coro(2, 3))

    async def main():
        t = await spawn_thread(func)
        await sleep(0.25)
        await t.cancel()

    kernel.run(main)

def test_thread_sync(kernel):
    results = []
    def func(lock):
        with lock:
            results.append('func')

    async def main():
        lock = Lock()
        async with lock:
            results.append('main')
            t = await spawn_thread(func, lock)
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

    async def main():
        t = await spawn_thread(func)
        await t.join()

    kernel.run(main)


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
        t = await spawn_thread(func)
        await sleep(0.5)
        await t.cancel()

    kernel.run(main)

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
        t = await spawn_thread(func)
        await t.join()

    kernel.run(main)

import curio.subprocess as subprocess
import sys

@pytest.mark.skipif(sys.platform.startswith('win'),
                    reason='Broken on windows')
def test_subprocess_popen(kernel):
    def func():
        with subprocess.Popen([sys.executable, '-c', 'print("hello")'], stdout=subprocess.PIPE) as p:
            data = AWAIT(p.stdout.read())
            assert data == b'hello\n'

    async def main():
        t = await spawn_thread(func)
        await t.join()

    kernel.run(main)

def test_task_group_thread(kernel):
    results = []
    async def add(x, y):
        return x + y

    def task():
        task1 = AWAIT(spawn(add, 1, 1))
        task2 = AWAIT(spawn(add, 2, 2))
        task3 = AWAIT(spawn(add, 3, 3))
        w = TaskGroup([task1, task2, task3])
        with w:
            for task in w:
                result = AWAIT(task.join())
                results.append(result)

    async def main():
        t = await spawn_thread(task)
        await t.join()

    kernel.run(main)
    assert results == [2, 4, 6]

def test_task_group_spawn_thread(kernel):
    def add(x, y):
        return x + y

    async def task():
        async with TaskGroup(wait=all) as w:
            await w.spawn_thread(add, 1, 1)
            await w.spawn_thread(add, 2, 2)
            t3 = await w.spawn_thread(add, 3, 3)
            r3 = await t3.join()
            assert r3 == 6

        assert w.results == [2, 4]

    kernel.run(task)

def test_await_passthrough(kernel):
    import time
    def add(x, y):
        AWAIT(time.sleep(0.1))
        AWAIT(time.sleep, 0.1)
        return x + y
    async def main():
        t = await spawn_thread(add, 2, 3)
        await t.wait()
        assert t.result == 5
    kernel.run(main)

def test_errors(kernel):
    # spawn_thread used on a coroutine
    async def main():
        with pytest.raises(TypeError):
            t = await spawn_thread(simple_coro, 2, 3)

    kernel.run(main)

    # AWAIT used on coroutine outside of async-thread
    with pytest.raises(AsyncOnlyError):
        AWAIT(simple_coro(2,3))

    # Premature result
    async def f():
        t = await spawn_thread(simple_func, 2, 3)
        assert t.state != 'TERMINATED'
        with pytest.raises(RuntimeError):
            r = t.result
        with pytest.raises(RuntimeError):
            e = t.exception

    kernel.run(f)

    # Launching a thread with no target
    async def g():
        from curio.thread import AsyncThread
        t = AsyncThread()
        with pytest.raises(RuntimeError):
            await t.start()

    kernel.run(g)


