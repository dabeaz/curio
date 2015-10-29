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

    def test_task_join_error(self):
        kernel = get_kernel()
        results = []

        async def child():
            results.append('start')
            int('bad')

        async def main():
            task = await new_task(child())
            await sleep(0.1)
            results.append('joining')
            try:
                r = await task.join()
                results.append(r)
            except TaskError as e:
                results.append('task fail')
                results.append(type(e))
                results.append(type(e.__cause__))

        kernel.add_task(main())
        kernel.run(log_errors=False)
        self.assertEqual(results, [
                'start',
                'joining',
                'task fail',
                TaskError,
                ValueError,
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
                 child_task = await new_task(child())
                 await sleep(0.5)
                 results.append('end parent')
            except CancelledError:
                await child_task.cancel()
                results.append('parent cancelled')
            
        async def grandparent():
            try:
                parent_task = await new_task(parent())
                await sleep(0.5)
                results.append('end grandparent')
            except CancelledError:
                await parent_task.cancel()
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

    def test_task_ready_cancel(self):
        # This tests a tricky corner case of a task cancelling another task that's also 
        # on the ready queue.

        kernel = get_kernel()
        results = []

        async def child():
            try:
                results.append('child sleep')
                await sleep(1.0)
                results.append('child fail')
            except CancelledError:
                results.append('child cancelled')

        async def parent():
            task = await new_task(child())
            results.append('parent sleep')
            await sleep(0.5)
            results.append('cancel start')
            await task.cancel()
            
        async def main():
            task = await new_task(parent())
            await sleep(0.1)
            time.sleep(1)      # Forced block of the event loop. Both tasks should awake when we come back
            await sleep(0.1)

        kernel.add_task(main())
        kernel.run()

        self.assertEqual(results, [
                'child sleep',
                'parent sleep',
                'cancel start',
                'child cancelled',
                ])

class TestSignal(unittest.TestCase):
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


    def test_task_signal_ignore(self):
        import signal, os
        kernel = get_kernel()
        results = []

        async def child():
            sig = SignalSet(signal.SIGUSR1, signal.SIGUSR2)
            async with sig:
                 signo = await sig.wait()
                 results.append(signo)
                 with sig.ignore():
                     await sleep(1)
                 results.append('here')

        async def main():
            task = await new_task(child())
            await sleep(0.1)
            results.append('sending USR1')
            os.kill(os.getpid(), signal.SIGUSR1)
            await sleep(0.5)
            results.append('sending USR1')
            os.kill(os.getpid(), signal.SIGUSR1)
            await sleep(0.1)
            await task.join()
            results.append('done')

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'sending USR1',
                signal.SIGUSR1,
                'sending USR1',
                'here',
                'done',
                ])

    def test_task_signal_timeout(self):
        import signal, os
        kernel = get_kernel()
        results = []

        async def child():
            async with SignalSet(signal.SIGUSR1, signal.SIGUSR2) as sig:
                try:
                    signo = await sig.wait(timeout=0.5)
                    results.append(signo)
                except TimeoutError:
                    results.append('timeout')

        async def main():
            task = await new_task(child())
            await task.join()
            results.append('done')

        kernel.add_task(main())
        kernel.run()
        self.assertEqual(results, [
                'timeout',
                'done',
                ])

if __name__ == '__main__':
    unittest.main()
