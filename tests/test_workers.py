# test_workers.py

import pytest

import time
from curio import *

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

def test_cpu(kernel):
    results = []

    async def spin(n):
        while n > 0:
            results.append(n)
            await sleep(0.1)
            n -= 1

    async def cpu_bound(n):
         r = await run_in_process(fib, n)
         results.append(('fib', r))

    async def main():
         await spawn(spin(10))
         await spawn(cpu_bound(36))

    kernel.run(main())

    assert results == [
            10, 9, 8, 7, 6, 5, 4, 3, 2, 1,
            ('fib', 14930352)
            ]

def test_blocking(kernel):
    results = []

    async def spin(n):
        while n > 0:
            results.append(n)
            await sleep(0.1)
            n -= 1

    async def blocking(n):
         await run_in_thread(time.sleep, n)
         results.append('sleep done')

    async def main():
         await spawn(spin(10))
         await spawn(blocking(2))

    kernel.run(main())

    assert results == [
            10, 9, 8, 7, 6, 5, 4, 3, 2, 1,
            'sleep done',
            ]

@pytest.mark.parametrize('runner', [ run_in_thread, run_in_process ])
def test_worker_cancel(kernel, runner):
    results = []

    async def spin(n):
        while n > 0:
            results.append(n)
            await sleep(0.1)
            n -= 1

    async def blocking(n):
         task = await spawn(runner(time.sleep, n))
         await sleep(0.55)
         await task.cancel()
         try:
             await task.join()
         except TaskError as e:
             if isinstance(e.__cause__, CancelledError):
                 results.append('cancel')

    async def main():
         await spawn(spin(10))
         await spawn(blocking(5))

    kernel.run(main())

    assert results == [
            10, 9, 8, 7, 6, 5, 'cancel', 4, 3, 2, 1
            ]


@pytest.mark.parametrize('runner', [ run_in_thread, run_in_process ])
def test_worker_timeout(kernel, runner):
    results = []

    async def spin(n):
        while n > 0:
            results.append(n)
            await sleep(0.1)
            n -= 1

    async def blocking(n):
         try:
             result = await timeout_after(0.55, runner(time.sleep, n))
         except TaskTimeout:
             results.append('cancel')

    async def main():
         await spawn(spin(10))
         await spawn(blocking(5))

    kernel.run(main())

    assert results == [
            10, 9, 8, 7, 6, 5, 'cancel', 4, 3, 2, 1
            ]


def test_exception(kernel):
    results = []

    async def error():
         try:
             result = await run_in_thread(fib, '10')
             results.append('fail')
         except Exception as e:
             results.append(type(e))

    async def main():
         await error()

    kernel.run(main())

    assert results == [
        TypeError
            ]

