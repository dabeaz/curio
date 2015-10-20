# curio/test/workers.py

import unittest
import time

from ..import *

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

class TestWorkers(unittest.TestCase):
    def test_cpu(self):
        kernel = get_kernel()
        results = []

        async def spin(n):
            while n > 0:
                results.append(n)
                await sleep(0.1)
                n -= 1
                
        async def cpu_bound(n):
             r = await run_cpu_bound(fib, n)
             results.append(('fib', r))

        kernel.add_task(spin(10))
        kernel.add_task(cpu_bound(36))
        kernel.run()

        self.assertEqual(results, [
                10, 9, 8, 7, 6, 5, 4, 3, 2, 1,
                ('fib', 14930352)
                ])

    def test_blocking(self):
        kernel = get_kernel()
        results = []

        async def spin(n):
            while n > 0:
                results.append(n)
                await sleep(0.1)
                n -= 1
                
        async def blocking(n):
             await run_blocking(time.sleep, n)
             results.append('sleep done')

        kernel.add_task(spin(10))
        kernel.add_task(blocking(2))
        kernel.run()

        self.assertEqual(results, [
                10, 9, 8, 7, 6, 5, 4, 3, 2, 1,
                'sleep done',
                ])


    def test_blocking_timeout(self):
        kernel = get_kernel()
        results = []

        async def spin(n):
            while n > 0:
                results.append(n)
                await sleep(0.1)
                n -= 1
                
        async def blocking(n):
             try:
                 await run_blocking(time.sleep, n, timeout=0.55)
             except TimeoutError:
                 results.append('timeout')

        kernel.add_task(spin(10))
        kernel.add_task(blocking(2))
        kernel.run()

        self.assertEqual(results, [
                10, 9, 8, 7, 6, 5, 'timeout', 4, 3, 2, 1
                ])



if __name__ == '__main__':
    unittest.main()
