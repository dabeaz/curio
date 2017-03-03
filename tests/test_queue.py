# test_queue.py

from collections import deque
from curio import *
import time
import threading

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
        'producer_join',
        'cons1 done',
        'cons2 done',
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
        'producer_join',
        ('cons1', 0),
        ('cons1', 1),
        ('cons1', 2),
        ('cons1', 3),
        'cons1 done',
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
        'producer_done',
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


def test_queue_sync(kernel):
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

    def produce_item(queue, item):
        queue.put(item)

    async def producer():
        queue = Queue()
        results.append('producer_start')
        await spawn(consumer(queue, 'cons1'))
        await spawn(consumer(queue, 'cons2'))
        await sleep(0.1)
        for n in range(4):
            produce_item(queue, n)
            await sleep(0.1)
        for n in range(2):
            produce_item(queue, None)
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
        'producer_join',
        'cons1 done',
        'cons2 done',
        'producer_done',
    ]


def test_priority_queue(kernel):
    results = []
    priorities = [4, 2, 1, 3]

    async def consumer(queue):
        while True:
            item = await queue.get()
            if item[1] is None:
                break
            results.append(item[1])
            await queue.task_done()
            await sleep(0.2)
        await queue.task_done()

    async def producer():
        queue = PriorityQueue()

        for n in priorities:
            await queue.put((n, n))

        await queue.put((10, None))

        await spawn(consumer(queue))

        await queue.join()

    kernel.run(producer())
    assert results == sorted(priorities)


def test_lifo_queue(kernel):
    results = []
    items = range(4)

    async def consumer(queue):
        while True:
            item = await queue.get()
            if item is None:
                break
            results.append(item)
            await queue.task_done()
            await sleep(0.2)
        await queue.task_done()

    async def producer():
        queue = LifoQueue()

        await queue.put(None)

        for n in items:
            await queue.put(n)

        await spawn(consumer(queue))

        await queue.join()

    kernel.run(producer())
    assert results == list(reversed(items))

def test_univ_queue_sync_async(kernel):
    result = [ ]
    async def consumer(q):
        while True:
            item = await q.get()
            if item is None:
                break
            result.append(item)
            await q.task_done()

    def producer(q):
        for i in range(10):
            q.put(i)
            time.sleep(0.1)
        q.join()
        assert True

    async def main():
        q = UniversalQueue()

        t1 = await spawn(consumer(q))
        t2 = threading.Thread(target=producer, args=(q,))
        t2.start()
        await run_in_thread(t2.join)
        await q.put(None)
        await t1.join()
        assert result == [0,1,2,3,4,5,6,7,8,9]
        await q.shutdown()

    kernel.run(main())

def test_univ_queue_async_sync(kernel):
    result = []
    def consumer(q):
        while True:
            item = q.get()
            if item is None:
                break
            result.append(item)
            q.task_done()

    async def producer(q):
        for i in range(10):
            await q.put(i)
            await sleep(0.1)
        await q.join()

    async def main():
        q = UniversalQueue()

        t1 = threading.Thread(target=consumer, args=(q,))
        t1.start()
        t2 = await spawn(producer(q))
        await t2.join()
        await q.put(None)
        await run_in_thread(t1.join)
        assert result == [0,1,2,3,4,5,6,7,8,9]
        await q.shutdown()

    kernel.run(main())

def test_univ_queue_cancel(kernel):
    result = [] 

    async def consumer(q):
        while True:
            try:
                item = await timeout_after(0.1, q.get())
            except TaskTimeout:
                continue
            if item is None:
                break
            result.append(item)
            await q.task_done()

    def producer(q):
        for i in range(10):
            q.put(i)
            time.sleep(0.2)
        q.join()

    async def main():
        q = UniversalQueue(maxsize=2)
        t1 = await spawn(consumer(q))
        t2 = threading.Thread(target=producer, args=(q,))
        t2.start()
        await run_in_thread(t2.join)
        await q.put(None)
        await t1.join()
        assert result == [0,1,2,3,4,5,6,7,8,9]
        await q.shutdown()

    kernel.run(main())

def test_univ_queue_multiple_consumer(kernel):
    result = []

    async def consumer(q):
        while True:
            item = await q.get()
            if item is None:
                break
            result.append(item)
            await q.task_done()

    def producer(q):
        for i in range(1000):
            q.put(i)
        q.join()

    async def main():
        q = UniversalQueue(maxsize=10)
        t1 = await spawn(consumer(q))
        t2 = await spawn(consumer(q))
        t3 = await spawn(consumer(q))
        t4 = threading.Thread(target=producer, args=(q,))
        t4.start()
        await run_in_thread(t4.join)
        await q.put(None)
        await q.put(None)
        await q.put(None)
        await t1.join()
        await t2.join()
        await t3.join()
        assert set(range(1000)) == set(result)
        await q.shutdown()

    kernel.run(main())


def test_univ_queue_multiple_kernels(kernel):
    result = []

    async def consumer(q):
        while True:
            item = await q.get()
            if item is None:
                break
            result.append(item)
            await q.task_done()

    def producer(q):
        for i in range(1000):
            q.put(i)
        q.join()

    async def main():
        q = UniversalQueue(maxsize=10)

        t1 = threading.Thread(target=run, args=(consumer(q),))
        t1.start()

        t2 = threading.Thread(target=run, args=(consumer(q),))
        t2.start()

        t3 = threading.Thread(target=run, args=(consumer(q),))
        t3.start()
        t4 = threading.Thread(target=producer, args=(q,))
        t4.start()

        await run_in_thread(t4.join)
        await q.put(None)
        await q.put(None)
        await q.put(None)
        
        t1.join()
        t2.join()
        t3.join()

        assert list(range(1000)) == sorted(result)
        await q.shutdown()

    kernel.run(main())



    



    



    

    
    


