# test_kernel.py

import time
import pytest
from curio import *

def test_cancel_noblock(kernel):
    cancelled = False
    child_exit = False

    async def child():
        nonlocal child_exit
        try:
            await sleep(10)
        finally:
            assert cancelled
            child_exit = True

    async def main():
        nonlocal cancelled
        t = await spawn(child)
        await t.cancel(blocking=False)
        cancelled = True

    kernel.run(main)
    assert child_exit

def test_task_schedule(kernel):
    n = 0
    async def child():
        nonlocal n
        assert n == 1
        n += 1
        await schedule()
        assert n == 3
        n += 1
        await schedule()

    async def parent():
        nonlocal n
        t = await spawn(child)
        assert n == 0
        n += 1
        await schedule()
        assert n == 2
        n += 1
        await schedule()
        assert n == 4

    kernel.run(parent)
    

def test_task_wait_no_cancel(kernel):
    results = []

    async def child(name, n):
        results.append(name + ' start')
        await sleep(n)
        results.append(name + ' end')
        return n

    async def main():
        task1 = await spawn(child, 'child1', 0.75)
        task2 = await spawn(child, 'child2', 0.5)
        task3 = await spawn(child, 'child3', 0.25)
        w = wait([task1, task2, task3])
        async for task in w:
            result = await task.join()
            results.append(result)

    kernel.run(main)
    assert results == [
        'child1 start',
        'child2 start',
        'child3 start',
        'child3 end',
        0.25,
        'child2 end',
        0.5,
        'child1 end',
        0.75
    ]


def test_task_wait_error(kernel):
    async def bad(x, y):
        return x + y

    async def main():
        task1 = await spawn(bad, 1, '1')
        task2 = await spawn(bad, 2, '2')
        task3 = await spawn(bad, 3, '3')
        w = wait([task1, task2, task3])
        async for task in w:
            try:
                result = await task.join()
            except TaskError as e:
                assert isinstance(e.__cause__, TypeError)
            else:
                assert False

    kernel.run(main)

def test_task_wait_cancel(kernel):
    results = []

    async def child(name, n):
        results.append(name + ' start')
        try:
            await sleep(n)
            results.append(name + ' end')
        except CancelledError:
            results.append(name + ' cancel')
        return n

    async def main():
        task1 = await spawn(child, 'child1', 0.75)
        task2 = await spawn(child, 'child2', 0.5)
        task3 = await spawn(child, 'child3', 0.25)
        w = wait([task1, task2, task3])
        async with w:
            task = await w.next_done()
            result = await task.join()
            results.append(result)

    kernel.run(main)
    assert results == [
        'child1 start',
        'child2 start',
        'child3 start',
        'child3 end',
        0.25,
        'child1 cancel',
        'child2 cancel'
    ]

def test_task_wait_iter(kernel):
    results = []

    async def child(name, n):
        results.append(name + ' start')
        try:
            await sleep(n)
            results.append(name + ' end')
        except CancelledError:
            results.append(name + ' cancel')
        return n

    async def main():
        task1 = await spawn(child, 'child1', 0.75)
        task2 = await spawn(child, 'child2', 0.5)
        task3 = await spawn(child, 'child3', 0.25)
        w = wait([task1, task2, task3])
        async with w:
            async for task in w:
                result = await task.join()
                results.append(result)

    kernel.run(main)
    assert results == [
        'child1 start',
        'child2 start',
        'child3 start',
        'child3 end',
        0.25,
        'child2 end',
        0.5,
        'child1 end',
        0.75
    ]


def test_task_wait_add(kernel):
    results = []

    async def child(name, n):
        results.append(name + ' start')
        try:
            await sleep(n)
            results.append(name + ' end')
        except CancelledError:
            results.append(name + ' cancel')
        return n

    async def main():
        task1 = await spawn(child, 'child1', 0.75)
        task2 = await spawn(child, 'child2', 0.5)
        w = wait([task1, task2])
        async with w:
            task = await w.next_done()
            result = await task.join()
            results.append(result)
            await w.add_task(await spawn(child, 'child3', 0.1))
            task = await w.next_done()
            result = await task.join()
            results.append(result)

    kernel.run(main)
    assert results == [
        'child1 start',
        'child2 start',
        'child2 end',
        0.5,
        'child3 start',
        'child3 end',
        0.1,
        'child1 cancel',
    ]

def test_enable_cancellation_function(kernel):
    cancelled = False
    done = False

    async def child():
        nonlocal cancelled
        try:
            await sleep(1)
        except CancelledError:
            cancelled = True
            raise
            
    async def task():
        nonlocal done
        async with disable_cancellation():
            await sleep(1)
            await enable_cancellation(child())
            assert True

        with pytest.raises(CancelledError):
            await sleep(1)
        done = True

    async def main():
        t = await spawn(task)
        await sleep(0.1)
        await t.cancel()
      
    kernel.run(main)
    assert cancelled
    assert done


def test_defer_cancellation(kernel):
    async def cancel_me(e1, e2):
        with pytest.raises(CancelledError):
            async with disable_cancellation():
                await e1.set()
                await e2.wait()
            await check_cancellation()

    async def main():
        e1 = Event()
        e2 = Event()
        task = await spawn(cancel_me, e1, e2)
        await e1.wait()
        await task.cancel(blocking=False)
        await e2.set()
        await task.join()

    kernel.run(main)


def test_disable_cancellation_function(kernel):
    async def cancel_it(e1, e2):
        await e1.set()
        await e2.wait()

    async def cancel_me(e1, e2):
        with pytest.raises(CancelledError):
            await disable_cancellation(cancel_it(e1, e2))
            await check_cancellation()

    async def main():
        e1 = Event()
        e2 = Event()
        task = await spawn(cancel_me, e1, e2)
        await e1.wait()
        await task.cancel(blocking=False)
        await e2.set()
        await task.join()

    kernel.run(main)


def test_self_cancellation(kernel):
    async def suicidal_task():
        task = await current_task()
        await task.cancel(blocking=False)
        # Cancellation is delivered the next time we block
        with pytest.raises(CancelledError):
            await sleep(0)

    kernel.run(suicidal_task)

def test_illegal_enable_cancellation(kernel):
    async def task():
        with pytest.raises(RuntimeError):
             async with enable_cancellation():
                 pass

    kernel.run(task)

def test_illegal_disable_cancellation_exception(kernel):
    async def task():
        with pytest.raises(RuntimeError):
             async with disable_cancellation():
                 raise CancelledError()

    kernel.run(task)

def test_set_cancellation(kernel):
    async def main():
        await set_cancellation(CancelledError())
        assert not await check_cancellation(TaskTimeout)
        with pytest.raises(CancelledError):
            await sleep(1)

        await set_cancellation(CancelledError())
        async with disable_cancellation():
            # This should return the given exception and clear it
            assert isinstance(await check_cancellation(CancelledError), CancelledError)
            # Verify that cleared
            assert not await check_cancellation()

    kernel.run(main())

def test_wait_misc(kernel):
    async def main():
         w = wait([])
         await w.cancel_remaining()

         w = wait([])
         await w.add_task(await spawn(sleep, 0))
         await w.cancel_remaining()

    kernel.run(main)

async def producer(ch):
    c = await ch.accept(authkey=b'peekaboo')
    for i in range(10):
        await c.send(i)
    await c.send(None)   # Sentinel

def test_aside_basic(kernel):
    import os
    os.environ['PYTHONPATH'] = os.path.dirname(__file__)
    results = [ ]

    async def consumer(ch):
        c = await ch.connect(authkey=b'peekaboo')
        while True:
            msg = await c.recv()
            if msg is None:
                break
            results.append(msg)

    async def main():
        ch = Channel(('localhost', 30000))
        t1 = await aside(producer, ch)
        t2 = await spawn(consumer, ch)
        await t1.join()
        await t2.join()

    kernel.run(main)
    del os.environ['PYTHONPATH']
    assert results == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_aside_cancel(kernel):
    import os
    os.environ['PYTHONPATH'] = os.path.dirname(__file__)
    results = [ ]

    async def consumer(ch, t):
        c = await ch.connect(authkey=b'peekaboo')
        while True:
            msg = await c.recv()
            if msg == 5:
                await t.cancel()
                break
            results.append(msg)

    async def main():
        ch = Channel(('localhost', 30000))
        t1 = await aside(producer, ch)
        t2 = await spawn(consumer, ch, t1)
        with pytest.raises(TaskError):
            await t1.join()
        await t2.join()

    kernel.run(main)
    del os.environ['PYTHONPATH']
    assert results == [0, 1, 2, 3, 4]

