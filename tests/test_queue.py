# test_queue.py

from collections import deque
from curio import *

def test_queue_simple(kernel):
    results = []
    async def consumer(queue, label):
          while True:
              item = await queue.get()
              if item is None:
                  break
              results.append((label, item))
              await queue.task_done()
          await queue.task_done()
          results.append(label + ' done')

    async def producer():
        queue = Queue()
        results.append('producer_start')
        await spawn(consumer(queue, 'cons1'))
        await spawn(consumer(queue, 'cons2'))
        await sleep(0.1)
        for n in range(4):
            await queue.put(n)
            await sleep(0.1)
        for n in range(2):
            await queue.put(None)
        results.append('producer_join')
        await queue.join()
        results.append('producer_done')

    kernel.run(producer())

    assert results == [
            'producer_start',
            ('cons1', 0),
            ('cons2', 1),
            ('cons1', 2),
            ('cons2', 3),
            'cons1 done',
            'cons2 done',
            'producer_join',
            'producer_done',
            ]

def test_queue_unbounded(kernel):
    results = []
    async def consumer(queue, label):
          while True:
              item = await queue.get()
              if item is None:
                  break
              results.append((label, item))
              await queue.task_done()
          await queue.task_done()
          results.append(label + ' done')

    async def producer():
        queue = Queue()
        results.append('producer_start')
        await spawn(consumer(queue, 'cons1'))
        await sleep(0.1)
        for n in range(4):
            await queue.put(n)
        await queue.put(None)
        results.append('producer_join')
        await queue.join()
        results.append('producer_done')

    kernel.run(producer())

    assert results == [
            'producer_start',
            ('cons1', 0),
            ('cons1', 1),
            ('cons1', 2),
            ('cons1', 3),
            'cons1 done',
            'producer_join',
            'producer_done',
            ]


def test_queue_bounded(kernel):
    results = []
    async def consumer(queue, label):
          while True:
              item = await queue.get()
              if item is None:
                  break
              results.append((label, item))
              await sleep(0.1)
              await queue.task_done()
          await queue.task_done()
          results.append(label + ' done')

    async def producer():
        queue = Queue(maxsize=2)
        results.append('producer_start')
        await spawn(consumer(queue, 'cons1'))
        await sleep(0.1)
        for n in range(4):
            await queue.put(n)
            results.append(('produced', n))
        await queue.put(None)
        results.append('producer_join')
        await queue.join()
        results.append('producer_done')

    kernel.run(producer())

    assert results == [
            'producer_start',
            ('cons1', 0),
            ('produced', 0),
            ('produced', 1),
            ('produced', 2),
            ('produced', 3),
            ('cons1', 1),
            'producer_join',
            ('cons1', 2),
            ('cons1', 3),
            'producer_done',
            'cons1 done',
            ]

def test_queue_get_cancel(kernel):
    # Make sure a blocking get can be cancelled
    results = []
    async def consumer():
          queue = Queue()
          try:
              results.append('consumer waiting')
              item = await queue.get()
              results.append('not here')
          except CancelledError:
              results.append('consumer cancelled')

    async def driver():
        task = await spawn(consumer())
        await sleep(0.5)
        await task.cancel()

    kernel.run(driver())
    assert results == [
            'consumer waiting',
            'consumer cancelled'
            ]

def test_queue_put_cancel(kernel):
    # Make sure a blocking put() can be cancelled
    results = []

    async def producer():
        queue = Queue(1)
        results.append('producer_start')
        await queue.put(0)
        try:
            await queue.put(1)
            results.append('not here')
        except CancelledError:
            results.append('producer_cancel')

    async def driver():
        task = await spawn(producer())
        await sleep(0.5)
        await task.cancel()

    kernel.run(driver())
    assert results == [
            'producer_start',
            'producer_cancel'
            ]

def test_queue_get_timeout(kernel):
    # Make sure a blocking get respects timeouts
    results = []
    async def consumer():
          queue = Queue()
          try:
              results.append('consumer waiting')
              item = await timeout_after(0.5, queue.get())
              results.append('not here')
          except TaskTimeout:
              results.append('consumer timeout')

    kernel.run(consumer())
    assert results == [
            'consumer waiting',
            'consumer timeout'
            ]

def test_queue_put_timeout(kernel):
    # Make sure a blocking put() respects timeouts
    results = []

    async def producer():
        queue = Queue(1)
        results.append('producer start')
        await queue.put(0)
        try:
            await timeout_after(0.5, queue.put(1))
            results.append('not here')
        except TaskTimeout:
            results.append('producer timeout')

    kernel.run(producer())
    assert results == [
            'producer start',
            'producer timeout'
            ]

