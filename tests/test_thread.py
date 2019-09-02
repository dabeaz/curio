# test_thread.py

import pytest
from curio import *
from curio.thread import AWAIT, async_thread, spawn_thread
from curio.file import aopen
import time
import pytest


def simple_func(x, y):
    AWAIT(sleep(0.5))     # Execute a blocking operation
    return x + y

@async_thread
def simple_func2(x, y):
    time.sleep(0.5)
    return x + y

async def simple_coro(x, y):
    await sleep(0.5)
    return x + y

def test_good_result(kernel):
    async def main():
        t = await spawn_thread(simple_func, 2, 3)
        result = await t.join()
        assert result == 5

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
    @async_thread
    def coro():
        result = AWAIT(simple_coro(2, 3))
        return result

    async def main():
        result = await coro()
        assert result == 5

    kernel.run(main)

def test_thread_bad_result(kernel):
    @async_thread
    def coro():
        with pytest.raises(TypeError):
            result = AWAIT(simple_coro(2, '3'))

    async def main():
        await coro()
            
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

    @async_thread
    def func():
        with pytest.raises(TaskTimeout):
            with timeout_after(1):
                AWAIT(sleep(2))

    async def main():
        await func()
        
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

# Tests the use of the spawn function on async thread functions.
# should run as a proper coroutine
            
def test_spawn_async_thread(kernel):
    results = []
    
    async def main():
        t = await spawn(simple_func2(2,3))
        results.append(1)
        results.append(await t.join())
        t = await spawn(simple_func2, 2, 3)
        results.append(2)
        results.append(await t.join())

    kernel.run(main)
    assert results == [1, 5, 2, 5]

def test_thread_context(kernel):
    results = []
    async def func(x, y):
        async with spawn_thread():
            time.sleep(0.5)
            results.append(AWAIT(simple_coro(x, y)))

    async def main():
        t = await spawn(func, 2, 3)
        await sleep(0.1)
        results.append(1)
        await t.join()

    kernel.run(main)
    assert results == [1, 5]

# This test is aimed at testing cancellation/timeouts in async threads
def test_thread_timeout(kernel):
    evt = Event()
    results = []

    @async_thread
    def worker1():
        AWAIT(evt.wait)
        results.append('worker1')

    async def worker2():
        async with spawn_thread():
            AWAIT(evt.wait)
            results.append('worker2')

    async def setter():
        await sleep(1)
        await evt.set()

    async def main():
        t = await spawn(setter)
        try:
            await timeout_after(0.1, worker1)
            results.append('bad')
        except TaskTimeout:
            results.append('timeout1')
        await t.join()
        evt.clear()
        t = await spawn(setter)
        try:
            await timeout_after(0.1, worker2)
            results.append('bad')
        except TaskTimeout:
            results.append('timeout2')

    kernel.run(main)
    assert results == ['timeout1', 'timeout2']

import threading

def test_async_thread_call(kernel):
    # Tests calling between async thread objects
    results = []
    
    @async_thread
    def func1(t):
        results.append('func1')
        results.append(t == threading.currentThread())

    @async_thread
    def func2():
        results.append('func2')
        # Calling an async_thread function from another async_thread function should
        # work like a normal synchronous function call
        func1(threading.currentThread())

    async def coro1():
        results.append('coro1')
        async with spawn_thread():
             # Calling an async_thread function from a thread context block should 
             # work like a normal sync function call
             func1(threading.currentThread())

    async def main():
        await func2()
        await coro1()
        
    kernel.run(main)
    assert results == ['func2', 'func1', True, 'coro1', 'func1', True]

def test_async_thread_async_thread_call(kernel):
    # Tests calling between async thread objects
    results = []
    
    @async_thread
    def func1(t):
        results.append('func1')
        results.append(t == threading.currentThread())

    @async_thread
    def func2():
        results.append('func2')
        # Awaiting on an async-thread function should work, but it should stay in the same thread
        AWAIT(func1, threading.currentThread())

    async def coro1():
        results.append('coro1')
        async with spawn_thread():
             # Calling an async_thread function from a thread context block should 
             # work like a normal sync function call
             func1(threading.currentThread())

    async def main():
        await func2()
        await coro1()
        
    kernel.run(main)
    assert results == ['func2', 'func1', True, 'coro1', 'func1', True]

