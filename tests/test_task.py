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

def test_task_group(kernel):
    async def child(x, y):
        return x + y

    async def main():
        async with TaskGroup() as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(child, 2, 2)
            t3 = await g.spawn(child, 3, 3)

        assert t1.result == 2
        assert t2.result == 4
        assert t3.result == 6

    kernel.run(main())

def test_task_group_existing(kernel):
    evt = Event()
    async def child(x, y):
        return x + y

    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        t1 = await spawn(child, 1, 1)
        t2 = await spawn(child2, 2, 2)
        t3 = await spawn(child2, 3, 3)
        t4 = await spawn(child, 4, 4)
        await t1.join()
        await t4.join()

        async with TaskGroup([t1, t2, t3]) as g:
            await evt.set()
            await g.add_task(t4)

        assert t1.result == 2
        assert t2.result == 4
        assert t3.result == 6
        assert t4.result == 8

    kernel.run(main())

def test_task_group_iter(kernel):
    async def child(x, y):
        return x + y

    async def main():
        results = set()
        async with TaskGroup() as g:
            await g.spawn(child, 1, 1)
            await g.spawn(child, 2, 2)
            await g.spawn(child, 3, 3)
            async for task in g:
                results.add(task.result)

        assert results == { 2, 4, 6 }

    kernel.run(main())


def test_task_group_error(kernel):
    evt = Event()
    async def child(x, y):
        result = x + y
        await evt.wait()

    async def main():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child, 1, 1)
                t2 = await g.spawn(child, 2, 2)
                t3 = await g.spawn(child, 3, 'bad')
        except TaskGroupError as e:
            assert TypeError in e.errors
            assert e.failed == [t3]
        else:
            assert False
        assert t1.cancelled
        assert t2.cancelled

    kernel.run(main())


def test_task_group_error_block(kernel):
    evt = Event()
    async def child(x, y):
        result = x + y
        await evt.wait()

    async def main():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child, 1, 1)
                t2 = await g.spawn(child, 2, 2)
                t3 = await g.spawn(child, 3, 3)
                raise RuntimeError()
        except RuntimeError:
            assert True
        else:
            assert False
        assert t1.cancelled
        assert t2.cancelled
        assert t3.cancelled

    kernel.run(main())

def test_task_group_join(kernel):
    evt = Event()
    async def child(x, y):
        result = x + y
        await evt.wait()
        return result

    async def main():
        async with TaskGroup() as g:
            t1 = await g.spawn(child, 1, 'foo')
            t2 = await g.spawn(child, 2, 2)
            t3 = await g.spawn(child, 3, 3)
            try:
                await t1.join()
            except TaskError as e:
                assert isinstance(e.__cause__, TypeError)
                assert isinstance(t1.exception, TypeError)
                with pytest.raises(TypeError):
                    t1.result
            else:
                assert Fail

            with pytest.raises(RuntimeError):
                t2.result

            with pytest.raises(RuntimeError):
                t2.exception

            await evt.set()

        assert not t2.cancelled
        assert not t3.cancelled

    kernel.run(main())

def test_task_group_multierror(kernel):
    evt = Event()
    async def child(exctype):
        if exctype:
            raise exctype('Died')
        await evt.wait()

    async def main():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child, RuntimeError)
                t2 = await g.spawn(child, ValueError)
                t3 = await g.spawn(child, None)
                await schedule()
                await evt.set()
        except TaskGroupError as e:
            assert e.errors == { RuntimeError, ValueError }
            assert e.failed == [t1, t2]
            assert list(e) == [t1, t2]
            str(e)
        else:
            assert False

    kernel.run(main())

def test_task_group_cancel(kernel):
    evt = Event()
    evt2 = Event()
    async def child():
        try:
            await evt.wait()
        except CancelledError:
            assert True
            raise
        else:
            raise False

    async def coro():
        try:
            async with TaskGroup() as g:
                t1 = await g.spawn(child)
                t2 = await g.spawn(child)
                t3 = await g.spawn(child)
                await evt2.set()
        except CancelledError:
            assert t1.cancelled
            assert t2.cancelled
            assert t3.cancelled
            raise
        else:
            assert False

    async def main():
        t = await spawn(coro)
        await evt2.wait()
        await t.cancel()

    kernel.run(main)


def test_task_group_timeout(kernel):
    evt = Event()
    async def child():
        try:
            await evt.wait()
        except TaskCancelled:
            assert True
            raise
        else:
            raise False

    async def coro():
        try:
            async with timeout_after(0.25):
                try:
                    async with TaskGroup() as g:
                        t1 = await g.spawn(child)
                        t2 = await g.spawn(child)
                        t3 = await g.spawn(child)
                except CancelledError:
                    assert t1.cancelled
                    assert t2.cancelled
                    assert t3.cancelled
                    raise
        except TaskTimeout:
            assert True
        else:
            assert False

    kernel.run(coro)


def test_task_group_cancel_remaining(kernel):
    evt = Event()
    async def child(x, y):
        return x + y

    async def waiter():
        await evt.wait()

    async def main():
        async with TaskGroup() as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(waiter)
            t3 = await g.spawn(waiter)
            t = await g.next_done()
            assert t == t1
            await g.cancel_remaining()

        assert t2.cancelled
        assert t3.cancelled

    kernel.run(main)

def test_task_group_use_error(kernel):
    async def main():
         async with TaskGroup() as g:
              t1 = await g.spawn(sleep, 0)
              with pytest.raises(RuntimeError):
                  await g.add_task(t1)

         with pytest.raises(RuntimeError):
             await g.spawn(sleep, 0)

         t2 = await spawn(sleep, 0)
         with pytest.raises(RuntimeError):
             await g.add_task(t2)

    kernel.run(main())
             
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

def test_taskgroup_misc(kernel):
    async def main():
         g = TaskGroup()
         await g.cancel_remaining()

         g = TaskGroup()
         await g.spawn(sleep, 0)
         await g.cancel_remaining()

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

