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

    def test_task_child_cancel(self):
        kernel = get_kernel()
        results = []

        async def child():
            results.append('start')
            try:
                await sleep(0.5)
                results.append('end')
            except CancelledError:
                results.append('child cancelled')

        async def parent():
            try:
                 await new_task(child())
                 await sleep(0.5)
                 results.append('end parent')
            except CancelledError:
                results.append('parent cancelled')
            
        async def grandparent():
            try:
                await new_task(parent())
                await sleep(0.5)
                results.append('end grandparent')
            except CancelledError:
                results.append('grandparent cancelled')

        async def main():
            task = await new_task(grandparent())
            await sleep(0.1)
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
                'child cancelled',
                'parent cancelled',
                'grandparent cancelled',
                'done',
                ])


    def test_task_signal(self):
        import signal, os
        kernel = get_kernel()
        results = []

        async def child():
            async with SignalSet(signal.SIGUSR1, signal.SIGUSR2) as sig:
                signo = await sig.wait()
                results.append(signo)
                signo = await sig.wait()
                results.append(signo)

        async def main():
            task = await new_task(child())
            await sleep(0.1)
            results.append('sending USR1')
            os.kill(os.getpid(), signal.SIGUSR1)
            await sleep(0.1)
            results.append('sending USR2')
            os.kill(os.getpid(), signal.SIGUSR2)
            await sleep(0.1)
            results.append('done')

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'sending USR1',
                signal.SIGUSR1,
                'sending USR2',
                signal.SIGUSR2,
                'done',
                ])


    def test_task_signal_waitone(self):
        import signal, os
        kernel = get_kernel()
        results = []

        async def child():
            sig = SignalSet(signal.SIGUSR1, signal.SIGUSR2)
            signo = await sig.wait()
            results.append(signo)
            signo = await sig.wait()
            results.append(signo)

        async def main():
            task = await new_task(child())
            await sleep(0.1)
            results.append('sending USR1')
            os.kill(os.getpid(), signal.SIGUSR1)
            await sleep(0.1)
            results.append('sending USR2')
            os.kill(os.getpid(), signal.SIGUSR2)
            await sleep(0.1)
            results.append('done')

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'sending USR1',
                signal.SIGUSR1,
                'sending USR2',
                signal.SIGUSR2,
                'done',
                ])

if __name__ == '__main__':
    unittest.main()
