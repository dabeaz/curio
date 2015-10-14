# queue.py

import unittest
from collections import deque

from ..import *

# ---- Queuing

class TestQueue(unittest.TestCase):
    def test_queue_simple(self):
        kernel = get_kernel()
        results = []
        async def consumer(queue, label):
              while True:
                  item = await queue.get()
                  if item is None:
                      break
                  results.append((label, item))
                  queue.task_done()
              queue.task_done()
              results.append(label + ' done')

        async def producer():
            queue = Queue()
            results.append('producer_start')
            kernel.add_task(consumer(queue, 'cons1'))
            kernel.add_task(consumer(queue, 'cons2'))
            await sleep(0.1)
            for n in range(4):
                await queue.put(n)
                await sleep(0.1)
            for n in range(2):
                await queue.put(None)
            results.append('producer_join')
            await queue.join()
            results.append('producer_done')

        kernel.add_task(producer())
        kernel.run()
        self.assertEqual(results, [
                'producer_start',
                ('cons1', 0),
                ('cons2', 1),
                ('cons1', 2),
                ('cons2', 3),
                'producer_join',
                'cons1 done',
                'cons2 done',
                'producer_done'
                ])

    def test_queue_unbounded(self):
        kernel = get_kernel()
        results = []
        async def consumer(queue, label):
              while True:
                  item = await queue.get()
                  if item is None:
                      break
                  results.append((label, item))
                  queue.task_done()
              queue.task_done()
              results.append(label + ' done')

        async def producer():
            queue = Queue()
            results.append('producer_start')
            kernel.add_task(consumer(queue, 'cons1'))
            await sleep(0.1)
            for n in range(4):
                await queue.put(n)
            await queue.put(None)
            results.append('producer_join')
            await queue.join()
            results.append('producer_done')

        kernel.add_task(producer())
        kernel.run()
        self.assertEqual(results, [
                'producer_start',
                'producer_join',
                ('cons1', 0),
                ('cons1', 1),
                ('cons1', 2),
                ('cons1', 3),
                'cons1 done',
                'producer_done'
                ])


    def test_queue_bounded(self):
        kernel = get_kernel()
        results = []
        async def consumer(queue, label):
              while True:
                  item = await queue.get()
                  if item is None:
                      break
                  results.append((label, item))
                  await sleep(0.1)
                  queue.task_done()
              queue.task_done()
              results.append(label + ' done')

        async def producer():
            queue = Queue(maxsize=2)
            results.append('producer_start')
            kernel.add_task(consumer(queue, 'cons1'))
            await sleep(0.1)
            for n in range(4):
                await queue.put(n)
                results.append(('produced', n))
            await queue.put(None)
            results.append('producer_join')
            await queue.join()
            results.append('producer_done')

        kernel.add_task(producer())
        kernel.run()
        self.assertEqual(results, [
                'producer_start',
                ('produced', 0),
                ('produced', 1),
                ('cons1', 0),
                ('produced', 2),
                ('cons1', 1),
                ('produced', 3),
                ('cons1', 2),
                'producer_join',
                ('cons1', 3),
                'cons1 done',
                'producer_done'
                ])

if __name__ == '__main__':
    unittest.main()
