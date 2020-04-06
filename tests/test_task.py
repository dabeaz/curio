# test_kernel.py
import sys
import time
import pytest
from curio import *
import sys


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
        await t.cancel()

    kernel.run(main)
    assert child_exit


def test_cancel_custom_exception(kernel):
    cancelled = False
    child_exit = False

    class MyException(Exception):
        pass

    async def child():
        nonlocal child_exit
        try:
            await sleep(10)
        except MyException:
            child_exit = True
            return
        child_exit = False

    async def main():
        t = await spawn(child)
        await t.cancel(exc=MyException)

    kernel.run(main)
    assert child_exit

def test_cancel_custom_exception_instance(kernel):
    cancelled = False
    child_exit = False

    class MyException(Exception):
        pass

    exc = MyException("Test")

    async def child():
        nonlocal child_exit
        try:
            await sleep(10)
        except MyException as e:
            child_exit = e is exc
            return
        child_exit = False

    async def main():
        t = await spawn(child)
        await t.cancel(exc=exc)

    kernel.run(main)
    assert child_exit

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
        assert g.results == [2, 4, 6]


    kernel.run(main())


def test_task_group_daemon(kernel):
    async def child(x, y):
        return x + y

    async def main():
        async with TaskGroup(wait=all) as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(child, 2, 2, daemon=True)
            t3 = await g.spawn(child, 3, "3", daemon=True)
            t4 = await g.spawn(sleep, 0.5, daemon=True)

        assert t1.result == 2
        assert g.results == [2]


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
        assert g.results == [2,4,6,8]

    kernel.run(main())

def test_task_any_cancel(kernel):
    evt = Event()
    async def child(x, y):
        return x + y

    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        async with TaskGroup(wait=any) as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(child2, 2, 2)
            t3 = await g.spawn(child2, 3, 3)

        assert t1.result == 2
        assert t1 == g.completed
        assert t2.cancelled
        assert t3.cancelled

    kernel.run(main())


def test_task_any_error(kernel):
    evt = Event()
    async def child(x, y):
        return x + y

    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        async with TaskGroup(wait=any) as g:
            t1 = await g.spawn(child, 1, '1')
            t2 = await g.spawn(child2, 2, 2)
            t3 = await g.spawn(child2, 3, 3)
        try:
            result = g.result
            assert False
        except TypeError:
            assert True
        else:
            assert False

        assert isinstance(g.exception, TypeError)
        assert t1.exception
        assert t2.cancelled
        assert t3.cancelled
        assert all(g.exceptions)

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
        assert g.results == []    # Explicit collection of results prevents collections on the group

    kernel.run(main())


def test_task_wait_none(kernel):
    evt = Event()
    async def child2(x, y):
        await evt.wait()
        return x + y

    async def main():
        async with TaskGroup(wait=None) as g:
            t2 = await g.spawn(child2, 2, 2)
            t3 = await g.spawn(child2, 3, 3)
        assert t2.cancelled
        assert t3.cancelled

    kernel.run(main())

def test_task_join_daemon(kernel):
    async def child(x, y):
        await sleep(0.1)
        return x + y

    async def main():
        async with TaskGroup(wait=all) as g:
            t2 = await g.spawn(child, 2, 2, daemon=True)
            t3 = await g.spawn(child, 3, 3)
            r = await t2.join()
        assert g.results == [6]

    kernel.run(main())


def test_task_group_error(kernel):
    evt = Event()
    async def child(x, y):
        result = x + y
        await evt.wait()

    async def main():
        async with TaskGroup() as g:
            t1 = await g.spawn(child, 1, 1)
            t2 = await g.spawn(child, 2, 2)
            t3 = await g.spawn(child, 3, 'bad')

        assert isinstance(t3.exception, TypeError)
        assert g.completed == t3
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
                assert False

            # These assert that the error has not cancelled other tasks
            with pytest.raises(RuntimeError):
                t2.result

            with pytest.raises(RuntimeError):
                t2.exception

            await evt.set()

        # Assert that other tasks ran to completion
        assert not t2.cancelled
        assert not t3.cancelled
        assert g.results == [4, 6]


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
            t0 = await g.spawn(child, 1, 1)
            t1 = await g.spawn(child, 2, 2)
            t2 = await g.spawn(waiter)
            t3 = await g.spawn(waiter)
            t = await g.next_done()
            assert t == t0
            r = await g.next_result()
            assert r == 4
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
         await t2.join()

         with pytest.raises(RuntimeError):
             await g.spawn_thread(time.sleep, 0)

    kernel.run(main())

def test_task_group_empty(kernel):
    async def main():
        async with TaskGroup() as g:
            pass

        assert g.exception is None
        assert g.exceptions == []
        assert g.results == []
        with pytest.raises(RuntimeError):
             g.result

    kernel.run(main())

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

def test_explicit_raise_cancel_disable(kernel):
    async def cancel_me(e1, e2):
        with pytest.raises(CancelledError):
            async with disable_cancellation():
                async with disable_cancellation():
                    await e1.set()
                    await e2.wait()
                    raise TaskCancelled()
                # Even if TaskCancelled is raised explicitly, it should not propagate out.
                # Instead, it gets defer until cancellation is enabled
                assert await check_cancellation()
                assert True
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

def test_disable_cancellation_explicit_raise(kernel):
    async def task():
        with pytest.raises(CancelledError):
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

def test_contextvars():
    import contextvars
    x = contextvars.ContextVar('x', default=0)
    from curio.task import ContextTask
    events = []
    async def countdown(n):
        x.set(n)
        while x.get() > 0:
            events.append(x.get())
            x.set(x.get() - 1)
            await sleep(0)

    async def main():
        async with TaskGroup() as g:
            await g.spawn(countdown, 3)
            await g.spawn(countdown, 6)

    with Kernel(taskcls=ContextTask) as kernel:
        kernel.run(main)

    assert events == [3,6,2,5,1,4,3,2,1]

def test_task_group_result(kernel):
    async def child(x, y):
        return x + y

    async def main():
        async with TaskGroup(wait=any) as g:
            await g.spawn(child, 1, 1)
            await g.spawn(child, 2, 2)
            await g.spawn(child, 3, 3)

        assert g.result == 2

    kernel.run(main())

# Smoke test on diagnostic functions (for code coverage)
def test_task_diag(kernel):
    async def child():
        await sleep(0.25)

    async def main():
        t = await spawn(child)
        s = str(t)
        s = t.where()
        s = t.traceback()
        del t

    kernel.run(main())

def test_late_join(kernel):
    async def child():
        pass

    async def main():
        t = await spawn(child)
        await sleep(0.1)
        await t.cancel()
        assert t.joined
        assert t.terminated
        assert not t.cancelled

    kernel.run(main)


def test_task_group_join_done(kernel):
    async def add(x, y):
        return x + y

    async def task():
        async with TaskGroup(wait=all) as w:
            await w.spawn(add, 1, 1)
            await w.spawn(add, 2, 2)
            t3 = await w.spawn(add, 3, 3)
            r3 = await t3.join()
            assert r3 == 6

        assert w.results == [2, 4]

    kernel.run(task)

def test_errors(kernel):
    # Test for premature result in task  group
    async def f():
        g = TaskGroup()
        with pytest.raises(RuntimeError):
            r = g.result
        with pytest.raises(RuntimeError):
            e = g.exception
        with pytest.raises(RuntimeError):
            r = g.results
        with pytest.raises(RuntimeError):
            r = g.exceptions

        with pytest.raises(RuntimeError):
            r = await g.next_result()

        await g.join()

    kernel.run(f)

def test_diag(kernel):
    # Test ability to get stack traces from different contexts
    from curio.task import _get_stack

    # Normal generator
    def gen(n):
        yield n

    def gen2(n):
        yield from gen(n)

    # Async generator
    async def agen(n):
        yield (await sleep(0.1))

    g = gen(0)
    next(g)
    w = _get_stack(g)

    g = gen2(0)
    next(g)
    w = _get_stack(g)

    async def f():
        a = agen(0)
        w = _get_stack(a)
        await a.asend(None)

    g = f()
    g.send(None)
    w = _get_stack(g)
