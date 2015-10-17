# curio/test/kernel.py

import unittest
import time
from ..import *

# ---- Basic Kernel Functionality

class TestKernel(unittest.TestCase):
    def test_hello(self):
        kernel = get_kernel()
        results = []
        async def hello():
              results.append('hello')

        kernel.add_task(hello())
        kernel.run()
        self.assertEqual(results, [
                'hello'
                ])

    def test_sleep(self):
        kernel = get_kernel()
        results = []

        async def main():
              results.append('start')
              await sleep(0.5)
              results.append('end')

        kernel.add_task(main())
        start = time.time()
        kernel.run()
        end = time.time()
        self.assertEqual(results, [
                'start',
                'end',
                ])
        self.assertTrue((end-start) > 0.5)

    def test_sleep_cancel(self):
        kernel = get_kernel()
        results = []

        async def sleeper():
            results.append('start')
            try:
                await sleep(1)
                results.append('not here')
            except CancelledError:
                results.append('cancelled')

        async def main():
            task = await new_task(sleeper())
            await sleep(0.5)
            await task.cancel()

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'start',
                'cancelled',
                ])

    def test_task_join(self):
        kernel = get_kernel()
        results = []

        async def child():
            results.append('start')
            await sleep(0.5)
            results.append('end')
            return 37

        async def main():
            task = await new_task(child())
            await sleep(0.1)
            results.append('joining')
            r = await task.join()
            results.append(r)

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'start',
                'joining',
                'end',
                37
                ])

    def test_task_cancel(self):
        kernel = get_kernel()
        results = []

        async def child():
            results.append('start')
            try:
                await sleep(0.5)
                results.append('end')
            except CancelledError:
                results.append('cancelled')

        async def main():
            task = await new_task(child())
            results.append('cancel start')
            await sleep(0.1)
            results.append('cancelling')
            await task.cancel()
            results.append('done')

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'start',
                'cancel start',
                'cancelling',
                'cancelled',
                'done',
                ])

if __name__ == '__main__':
    unittest.main()
