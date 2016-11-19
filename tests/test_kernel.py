# test_kernel.py

import time
import pytest
from curio import *
kernel_clock = clock

def test_hello(kernel):
    results = []
    async def hello():
        results.append('hello')

    kernel.run(hello())
    assert results == [ 'hello' ]

def test_sleep(kernel):
    results = []
    async def main():
          results.append('start')
          await sleep(0.5)
          results.append('end')

    start = time.time()
    kernel.run(main())
    end = time.time()
    assert results == [
            'start',
            'end',
            ]
    elapsed = end-start
    assert elapsed > 0.5

def test_wakeat(kernel):
    results = []
    async def main():
          clock = await kernel_clock() + 0.5
          results.append('start')
          newclock = await wake_at(clock)
          results.append(round(newclock-clock, 1))

    start = time.time()
    kernel.run(main())
    end = time.time()
    assert results == [
            'start',
            0.0,
            ]
    elapsed = end-start
    assert elapsed > 0.5

def test_sleep_cancel(kernel):
    results = []

    async def sleeper():
        results.append('start')
        try:
            await sleep(1)
            results.append('not here')
        except CancelledError:
            results.append('cancelled')

    async def main():
        task = await spawn(sleeper())
        await sleep(0.5)
        await task.cancel()

    kernel.run(main())
    assert results == [
            'start',
            'cancelled',
            ]


def test_sleep_timeout(kernel):
    results = []

    async def sleeper():
        results.append('start')
        try:
            await timeout_after(0.5, sleep(1))
            results.append('not here')
        except TaskTimeout:
            results.append('timeout')

    async def main():
        task = await spawn(sleeper())
        await task.join()

    kernel.run(main())
    assert results == [
            'start',
            'timeout',
            ]

def test_sleep_timeout_absolute(kernel):
    results = []

    async def sleeper():
        results.append('start')
        try:
            await timeout_at((await kernel_clock()) + 0.5, sleep(1))
            results.append('not here')
        except TaskTimeout:
            results.append('timeout')

    async def main():
        task = await spawn(sleeper())
        await task.join()

    kernel.run(main())
    assert results == [
            'start',
            'timeout',
            ]

def test_sleep_ignore_timeout(kernel):
    results = []

    async def sleeper():
        results.append('start')
        if await ignore_after(0.5, sleep(1)) is None:
            results.append('timeout')

        async with ignore_after(0.5) as s:
            await sleep(1)

        if s.result is None:
            results.append('timeout2')


    async def main():
        task = await spawn(sleeper())
        await task.join()

    kernel.run(main())
    assert results == [
            'start',
            'timeout',
            'timeout2',
            ]



def test_sleep_ignore_timeout_absolute(kernel):
    results = []

    async def sleeper():
        results.append('start')
        if await ignore_at((await kernel_clock()) + 0.5, sleep(1)) is None:
            results.append('timeout')

        async with ignore_at((await kernel_clock()) + 0.5) as s:
            await sleep(1)

        if s.result is None:
            results.append('timeout2')


    async def main():
        task = await spawn(sleeper())
        await task.join()

    kernel.run(main())
    assert results == [
            'start',
            'timeout',
            'timeout2',
            ]

def test_sleep_notimeout(kernel):
    results = []

    async def sleeper():
        results.append('start')
        try:
            await timeout_after(1.5, sleep(1))
            results.append('here')
        except TaskTimeout:
            results.append('not here')

        await sleep(1)
        results.append('here2')

    async def main():
        task = await spawn(sleeper())
        await task.join()

    kernel.run(main())
    assert results == [
            'start',
            'here',
            'here2'
            ]

def test_task_join(kernel):
    results = []

    async def child():
        results.append('start')
        await sleep(0.5)
        results.append('end')
        return 37

    async def main():
        task = await spawn(child())
        await sleep(0.1)
        results.append('joining')
        r = await task.join()
        results.append(r)

    kernel.run(main())
    assert results == [
            'start',
            'joining',
            'end',
            37
            ]

def test_task_join_error(kernel):
    results = []

    async def child():
        results.append('start')
        int('bad')

    async def main():
        task = await spawn(child())
        await sleep(0.1)
        results.append('joining')
        try:
            r = await task.join()
            results.append(r)
        except TaskError as e:
            results.append('task fail')
            results.append(type(e))
            results.append(type(e.__cause__))

    kernel.run(main())
    assert results == [
            'start',
            'joining',
            'task fail',
            TaskError,
            ValueError,
            ]

def test_task_cancel(kernel):
    results = []

    async def child():
        results.append('start')
        try:
            await sleep(0.5)
            results.append('end')
        except CancelledError:
            results.append('cancelled')

    async def main():
        task = await spawn(child())
        results.append('cancel start')
        await sleep(0.1)
        results.append('cancelling')
        await task.cancel()
        results.append('done')

    kernel.run(main())
    assert results == [
            'cancel start',
            'start',
            'cancelling',
            'cancelled',
            'done',
            ]


def test_task_cancel_not_blocking(kernel):
    async def child(e1, e2):
        await e1.set()
        try:
            await sleep(1000)
        except CancelledError:
            await e2.wait()
            raise

    async def main():
        e1 = Event()
        e2 = Event()
        task = await spawn(child(e1, e2))
        await e1.wait()
        await task.cancel(blocking=False)
        await e2.set()
        try:
            await task.join()
        except TaskError as e:
            assert isinstance(e.__cause__, CancelledError)

    kernel.run(main())

def test_task_cancel_join(kernel):
    results = []

    async def child():
        results.append('start')
        await sleep(0.5)
        results.append('end')

    async def main():
        task = await spawn(child())
        results.append('cancel start')
        await sleep(0.1)
        results.append('cancelling')
        await task.cancel()
        # Try joining with a cancelled task. Should raise a TaskError
        try:
            await task.join()
        except TaskError as e:
            if type(e.__cause__) == CancelledError:
                results.append('join cancel')
            else:
                results.append(str(e.__cause__))
        results.append('done')

    kernel.run(main())
    assert results == [
            'cancel start',
            'start',
            'cancelling',
            'join cancel',
            'done',
            ]


def test_task_cancel_join_wait(kernel):
    results = []

    async def child():
        results.append('start')
        await sleep(0.5)
        results.append('end')

    async def canceller(task):
        await sleep(0.1)
        results.append('cancel')
        await task.cancel()

    async def main():
        task = await spawn(child())
        results.append('cancel start')
        await spawn(canceller(task))
        try:
            results.append('join')
            await task.join()     # Should raise TaskError... with CancelledError as cause
        except TaskError as e:
            if type(e.__cause__) == CancelledError:
                results.append('join cancel')
            else:
                results.append(str(e.__cause__))
        results.append('done')

    kernel.run(main())
    assert results == [
            'cancel start',
            'join',
            'start',
            'cancel',
            'join cancel',
            'done',
            ]

def test_task_child_cancel(kernel):
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
             child_task = await spawn(child())
             await sleep(0.5)
             results.append('end parent')
        except CancelledError:
            await child_task.cancel()
            results.append('parent cancelled')

    async def grandparent():
        try:
            parent_task = await spawn(parent())
            await sleep(0.5)
            results.append('end grandparent')
        except CancelledError:
            await parent_task.cancel()
            results.append('grandparent cancelled')

    async def main():
        task = await spawn(grandparent())
        await sleep(0.1)
        results.append('cancel start')
        await sleep(0.1)
        results.append('cancelling')
        await task.cancel()
        results.append('done')

    kernel.run(main())

    assert results == [
            'start',
            'cancel start',
            'cancelling',
            'child cancelled',
            'parent cancelled',
            'grandparent cancelled',
            'done',
            ]

def test_task_ready_cancel(kernel):
    # This tests a tricky corner case of a task cancelling another task that's also 
    # on the ready queue.
    results = []

    async def child():
        try:
            results.append('child sleep')
            await sleep(1.0)
            results.append('child slept')
            await sleep(1.0)
            results.append('should not see this')
        except CancelledError:
            results.append('child cancelled')

    async def parent():
        task = await spawn(child())
        results.append('parent sleep')
        await sleep(0.5)
        results.append('cancel start')
        await task.cancel()
        results.append('cancel done')

    async def main():
        task = await spawn(parent())
        await sleep(0.1)
        time.sleep(1)      # Forced block of the event loop. Both tasks should awake when we come back
        await sleep(0.1)

    kernel.run(main())

    assert results == [
            'parent sleep',
            'child sleep',
            'cancel start',
            'child slept',
            'child cancelled',
            'cancel done'
            ]


def test_double_cancel(kernel):
    results = []

    async def sleeper():
        results.append('start')
        try:
            await sleep(1)
            results.append('not here')
        except CancelledError:
            results.append('cancel request')
            await sleep(1)
            results.append('cancelled')

    async def main():
        task = await spawn(sleeper())
        await sleep(0.5)
        try:
            await timeout_after(1, task.cancel())
        except TaskTimeout:
            results.append('retry')
            await task.cancel()    # This second cancel should not abort any operation in sleeper
            results.append('done cancel')

    kernel.run(main())
    assert results == [
            'start',
            'cancel request',
            'retry',
            'cancelled',
            'done cancel'
            ]

def test_nested_timeout(kernel):
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(1)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    # Parent should cause a timeout before the child.  
    # Results in a TimeoutCancellationError instead of a normal TaskTimeout
    async def child():
        try:
            await timeout_after(5, coro1())
            results.append('coro1 success')
        except TaskTimeout:
            results.append('coro1 timeout')
        except TimeoutCancellationError:
            results.append('coro1 timeout cancel')

        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            await timeout_after(1, child())
        except TaskTimeout:
            results.append('parent timeout')

    kernel.run(parent())
    assert results == [
            'coro1 start',
            'coro1 timeout cancel',
            'coro2 start',
            'parent timeout'
            ]


def test_nested_context_timeout(kernel):
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(1)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    # Parent should cause a timeout before the child.  
    # Results in a TimeoutCancellationError instead of a normal TaskTimeout
    async def child():
        try:
            async with timeout_after(5):
                await coro1()
            results.append('coro1 success')
        except TaskTimeout:
            results.append('coro1 timeout')
        except TimeoutCancellationError:
            results.append('coro1 timeout cancel')

        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            async with timeout_after(1):
                await child()
        except TaskTimeout:
            results.append('parent timeout')

    kernel.run(parent())
    assert results == [
            'coro1 start',
            'coro1 timeout cancel',
            'coro2 start',
            'parent timeout'
            ]

def test_nested_timeout_uncaught(kernel):
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(5)
        results.append('coro1 done')

    async def child():
        # This will cause a TaskTimeout, but it's uncaught
        await timeout_after(1, coro1())

    async def parent():
        try:
            await timeout_after(10, child())
        except TaskTimeout:
            results.append('parent timeout')
        except UncaughtTimeoutError:
            results.append('uncaught timeout')

    kernel.run(parent())
    assert results == [
            'coro1 start',
            'uncaught timeout'
            ]


def test_nested_context_timeout_uncaught(kernel):
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(5)
        results.append('coro1 done')

    async def child():
        # This will cause a TaskTimeout, but it's uncaught
        async with timeout_after(1):
            await coro1()

    async def parent():
        try:
            async with timeout_after(10):
                await child()
        except TaskTimeout:
            results.append('parent timeout')
        except UncaughtTimeoutError:
            results.append('uncaught timeout')

    kernel.run(parent())
    assert results == [
            'coro1 start',
            'uncaught timeout'
            ]


def test_nested_timeout_none(kernel):
    results = []

    async def coro1():
        results.append('coro1 start')
        await sleep(2)
        results.append('coro1 done')

    async def coro2():
        results.append('coro2 start')
        await sleep(1)
        results.append('coro2 done')

    async def child():
        await timeout_after(None, coro1())
        results.append('coro1 success')
        await coro2()
        results.append('coro2 success')

    async def parent():
        try:
            await timeout_after(1, child())
        except TaskTimeout:
            results.append('parent timeout')

    kernel.run(parent())
    assert results == [
            'coro1 start',
            'coro1 done',
            'coro1 success',
            'coro2 start',
            'parent timeout'
            ]

def test_task_wait_no_cancel(kernel):
    results = []

    async def child(name, n):
        results.append(name + ' start')
        await sleep(n)
        results.append(name + ' end')
        return n

    async def main():
        task1 = await spawn(child('child1', 0.75))
        task2 = await spawn(child('child2', 0.5))
        task3 = await spawn(child('child3', 0.25))
        w = wait([task1, task2, task3])
        async for task in w:
             result = await task.join()
             results.append(result)

    kernel.run(main())
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
        task1 = await spawn(child('child1', 0.75))
        task2 = await spawn(child('child2', 0.5))
        task3 = await spawn(child('child3', 0.25))
        w = wait([task1, task2, task3])
        async with w:
             task = await w.next_done()
             result = await task.join()
             results.append(result)

    kernel.run(main())
    assert results == [
            'child1 start',
            'child2 start',
            'child3 start',
            'child3 end',
            0.25,
            'child1 cancel',
            'child2 cancel'
            ]

def test_task_run_error(kernel):
    results = []

    async def main():
        int('bad')

    try:
        kernel.run(main())
    except TaskError as e:
        assert isinstance(e.__cause__, ValueError)
    else:
        assert False

def test_defer_cancellation(kernel):
    async def cancel_me(e1, e2):
        with pytest.raises(CancelledError):
            async with defer_cancellation:
                try:
                    await e1.set()
                    await e2.wait()
                except CancelledError:
                    assert False

    async def main():
        e1 = Event()
        e2 = Event()
        task = await spawn(cancel_me(e1, e2))
        await e1.wait()
        await task.cancel(blocking=False)
        await e2.set()
        await task.join()

    kernel.run(main())


def test_sleep_0_starvation(kernel):
    # This task should not block other tasks from running, and should be
    # cancellable. We used to have a bug where neither were true...
    async def loop_forever():
        while True:
            print("Sleeping 0")
            await sleep(0)

    async def io1(sock):
        await sock.recv(1)
        await sock.send(b"x")
        await sock.recv(1)

    async def io2(sock):
        await sock.send(b"x")
        await sock.recv(1)
        await sock.send(b"x")

    async def main():
        loop_task = await spawn(loop_forever())
        await sleep(0)
        import curio.socket
        sock1, sock2 = curio.socket.socketpair()
        io1_task = await spawn(io1(sock1))
        io2_task = await spawn(io2(sock2))
        await io1_task.join()
        await io2_task.join()
        await loop_task.cancel()

    kernel.run(main())
