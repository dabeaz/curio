# test_kernel.py

import time
import pytest
from curio import *
kernel_clock = clock
from curio import traps

def test_hello(kernel):

    async def hello():
        return 'hello'

    result = kernel.run(hello)
    assert result == 'hello'

def test_raise(kernel):
    class Error(Exception):
        pass

    async def boom():
        raise Error()

    try:
        kernel.run(boom)
        assert False, 'boom() did not raise'
    except Error as e:
        pass
    except:
        assert False, 'boom() raised wrong error'

def test_sleep(kernel):
    start = end = 0
    async def main():
        nonlocal start, end
        start = time.time()
        await sleep(0.5)
        end = time.time()

    kernel.run(main)
    elapsed = end - start
    assert elapsed > 0.5

def test_clock(kernel):
    async def main():
        start = await clock()
        await sleep(0.1)
        end = await clock()
        assert (end - start) >= 0.1
    kernel.run(main)

def test_sleep_cancel(kernel):
    cancelled = False

    async def sleeper():
        nonlocal cancelled
        try:
            await sleep(1)
            assert False
        except CancelledError:
            cancelled = True

    async def main():
        task = await spawn(sleeper)
        await sleep(0.1)
        await task.cancel()

    kernel.run(main)
    assert cancelled

def test_sleep_timeout(kernel):
    cancelled = True

    async def sleeper():
        nonlocal cancelled
        try:
            await timeout_after(0.1, sleep, 1)
            assert False
        except TaskTimeout:
            cancelled = True

    async def main():
        task = await spawn(sleeper)
        await task.join()

    kernel.run(main)
    assert cancelled

def test_sleep_ignore_timeout(kernel):
    async def sleeper():
        cancelled = False

        if await ignore_after(0.1, sleep(1)) is None:
            cancelled = True
        assert cancelled

        cancelled = False
        async with ignore_after(0.1) as s:
            await sleep(1)
        if s.result is None:
            cancelled = True

        assert cancelled

    async def main():
        task = await spawn(sleeper)
        await task.join()

    kernel.run(main)

def test_sleep_notimeout(kernel):
    async def sleeper():
        try:
            await timeout_after(0.5, sleep(0.1))
            assert True
        except TaskTimeout:
            assert False
        await sleep(0.5)
        assert True

    async def main():
        task = await spawn(sleeper)
        await task.join()

    kernel.run(main)

def test_task_join(kernel):
    async def child():
        return 37

    async def main():
        task = await spawn(child)
        r = await task.join()
        assert r == 37

    kernel.run(main)

def test_task_join_error(kernel):
    async def child():
        int('bad')

    async def main():
        task = await spawn(child)
        try:
            r = await task.join()
            assert False
        except TaskError as e:
            assert isinstance(e.__cause__, ValueError)

    kernel.run(main)

def test_task_cancel(kernel):
    cancelled = False
    async def child():
        nonlocal cancelled
        try:
            await sleep(0.5)
            assert False
        except CancelledError:
            cancelled = True

    async def main():
        task = await spawn(child)
        await task.cancel()
        assert cancelled

    kernel.run(main)

def test_task_cancel_poll(kernel):
    results = []

    async def child():
        async with disable_cancellation():
            await sleep(0.1)
            results.append('success')
            if await check_cancellation():
                results.append('cancelled')
            else:
                assert False

    async def main():
        task = await spawn(child)
        await task.cancel()
        results.append('done')

    kernel.run(main)
    assert results == ['success', 'cancelled', 'done']

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
        task = await spawn(child, e1, e2)
        await e1.wait()
        await task.cancel(blocking=False)
        await e2.set()
        try:
            await task.join()
        except TaskError as e:
            assert isinstance(e.__cause__, CancelledError)

    kernel.run(main)


def test_task_cancel_join(kernel):
    child_evt = Event()
    async def child():
        await child_evt.wait()
        assert False

    async def main():
        task = await spawn(child)
        await sleep(0)
        await task.cancel()

        # Try joining with a cancelled task. Should raise a TaskError
        try:
            await task.join()
        except TaskError as e:
            assert isinstance(e.__cause__, CancelledError)
        else:
            assert False
        assert True

    kernel.run(main)

def test_task_cancel_join_wait(kernel):
    evt = Event()

    async def child():
        await evt.wait()

    async def canceller(task):
        await task.cancel()

    async def main():
        task1 = await spawn(child)
        task2 = await spawn(canceller, task1)
        await task2.join()
        assert not evt.is_set()
        try:
            await task1.join()     # Should raise TaskError... with CancelledError as cause
            assert False
        except TaskError as e:
            assert isinstance(e.__cause__, CancelledError)
        else:
            assert False

    kernel.run(main)

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
            child_task = await spawn(child)
            await sleep(0.5)
            results.append('end parent')
        except CancelledError:
            await child_task.cancel()
            results.append('parent cancelled')

    async def grandparent():
        try:
            parent_task = await spawn(parent)
            await sleep(0.5)
            results.append('end grandparent')
        except CancelledError:
            await parent_task.cancel()
            results.append('grandparent cancelled')

    async def main():
        task = await spawn(grandparent)
        await sleep(0.1)
        results.append('cancel start')
        await sleep(0.1)
        results.append('cancelling')
        await task.cancel()
        results.append('done')

    kernel.run(main)

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
        task = await spawn(child)
        results.append('parent sleep')
        await sleep(0.5)
        results.append('cancel start')
        await task.cancel()
        results.append('cancel done')

    async def main():
        task = await spawn(parent)
        await sleep(0.1)
        time.sleep(1)      # Forced block of the event loop. Both tasks should awake when we come back
        await sleep(0.1)

    kernel.run(main)

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
        task = await spawn(sleeper)
        await sleep(0.5)
        try:
            await timeout_after(1, task.cancel())
        except TaskTimeout:
            results.append('retry')
            await task.cancel()    # This second cancel should not abort any operation in sleeper
            results.append('done cancel')

    kernel.run(main)
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
            await timeout_after(0.75, child())
        except TaskTimeout:
            results.append('parent timeout')

    kernel.run(parent)
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
            async with timeout_after(0.75):
                await child()
        except TaskTimeout:
            results.append('parent timeout')

    kernel.run(parent)
    assert results == [
        'coro1 start',
        'coro1 timeout cancel',
        'coro2 start',
        'parent timeout'
    ]

def test_nested_context_timeout2(kernel):
    async def coro1():
        try:
            async with timeout_after(10):
                await sleep(5)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def coro2():
        try:
            async with timeout_after(15):
                await coro1()
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def parent():
        try:
            async with timeout_after(0.1):
                await coro2()
        except Exception as e:
            assert isinstance(e, TaskTimeout)
        else:
            assert False

    kernel.run(parent)

def test_nested_context_timeout3(kernel):
    async def coro1():
        try:
            await timeout_after(10, sleep, 5)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def coro2():
        try:
            await timeout_after(15, coro1)
        except CancelledError as e:
            assert isinstance(e, TimeoutCancellationError)
            raise
        else:
            assert False

    async def parent():
        try:
            await timeout_after(0.1, coro2)
        except Exception as e:
            assert isinstance(e, TaskTimeout)
        else:
            assert False

    kernel.run(parent)

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

    kernel.run(parent)
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

    kernel.run(parent)
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

    kernel.run(parent)
    assert results == [
        'coro1 start',
#        'coro1 done',
#        'coro1 success',
#        'coro2 start',
        'parent timeout'
    ]


def test_task_run_error(kernel):
    results = []

    async def main():
        int('bad')

    try:
        kernel.run(main)
        assert False, "Exception not raised"
    except ValueError as e:
        pass
    except:
        assert False, "Wrong exception raised"

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
        loop_task = await spawn(loop_forever)
        await sleep(0)
        import curio.socket
        sock1, sock2 = curio.socket.socketpair()
        io1_task = await spawn(io1, sock1)
        io2_task = await spawn(io2, sock2)
        await io1_task.join()
        await io2_task.join()
        await loop_task.cancel()

    kernel.run(main)


def test_ping_pong_starvation(kernel):
    # It used to be that two of these tasks could starve out other tasks
    async def pingpong(inq, outq):
        while True:
            await outq.put(await inq.get())

    async def i_will_survive():
        for _ in range(10):
            await sleep(0)
        return "i survived!"

    async def main():
        q1 = Queue()
        q2 = Queue()
        await q1.put("something")
        pp1 = await spawn(pingpong, q1, q2)
        pp2 = await spawn(pingpong, q2, q1)
        iws = await spawn(i_will_survive)

        assert (await iws.join()) == "i survived!"
        await pp1.cancel()
        await pp2.cancel()

    kernel.run(main)

def test_task_cancel_timeout(kernel):
    # Test that cancellation also cancels timeouts
    results = []

    async def coro():
        try:
            await sleep(5)
        except CancelledError:
            results.append('cancelled')
            await sleep(1)
            results.append('done cancel')
            raise

    async def child():
        results.append('child')
        try:
            async with timeout_after(1):
                 await coro()
        except TaskTimeout:
            results.append('timeout')

    async def main():
        task = await spawn(child)
        await sleep(0.5)
        await task.cancel()

    kernel.run(main)
    assert results == [ 'child', 'cancelled', 'done cancel' ]

def test_reentrant_kernel(kernel):
    async def child():
        pass

    async def main():
        with pytest.raises(RuntimeError):
            kernel.run(child)

    kernel.run(main)

from curio.traps import *

def test_pending_cancellation(kernel):
    async def main():
        self = await _get_current()
        self.cancel_pending = CancelledError()

        with pytest.raises(CancelledError):
            await _read_wait(None)

        self.cancel_pending = CancelledError()        
        with pytest.raises(CancelledError):
            await _future_wait(None)

        self.cancel_pending = CancelledError()
        with pytest.raises(CancelledError):
            await _scheduler_wait(None, None)

        self.cancel_pending = TaskTimeout()
        try:
            await _unset_timeout(None)
            assert True
        except TaskTimeout:
            assert False
            
    kernel.run(main)

from functools import partial

def test_single_stepping(kernel):
    value = 0
    async def child():
        nonlocal value
        await sleep(0)
        value = 1
        await sleep(0.1)
        value = 2

    task = kernel.run(partial(spawn, child, daemon=True))
    while value < 1:
        kernel.run()
    assert True
    time.sleep(0.2)
    kernel.run()
    assert value == 2

def test_io_registration(kernel):
    # Tests some tricky corner cases of the kernel that are difficult
    # to get to under normal socket usage
    import socket
    s1, s2 = socket.socketpair()
    s1.setblocking(False)
    s2.setblocking(False)
    
    # Fill the send buffer
    while True:
        try:
            s1.send(b'x'*100000)
        except BlockingIOError:
            break

    async def reader1():
        await traps._read_wait(s1.fileno())
        data = s1.recv(100)
        assert data == b'hello'

    async def writer1():
        await traps._write_wait(s1.fileno())
        assert False

    async def writer2():
        with pytest.raises(WriteResourceBusy):
            await traps._write_wait(s1.fileno())

    async def main():
        t0 = await spawn(reader1)
        t1 = await spawn(writer1)
        t2 = await spawn(writer2)
        await t2.join()
        await t1.cancel()
        s2.send(b'hello')
        await t0.join()
        s1.close()
        s2.close()

    kernel.run(main)

from functools import partial

def test_coro_partial(kernel):
    async def func(x, y, z):
        assert x == 1
        assert y == 2
        assert z == 3
        return True
        
    async def main():
        assert await func(1, 2, 3)
        assert await ignore_after(1, func(1,2,3))
        assert await ignore_after(1, func, 1, 2, 3)
        assert await ignore_after(1, partial(func, 1, 2), 3)
        assert await ignore_after(1, partial(func, z=3), 1, 2)

        # Try spawns
        t = await spawn(func(1,2,3))
        assert await t.join()

        t = await spawn(func, 1, 2, 3)
        assert await t.join()

        t = await spawn(partial(func, 1, 2), 3)
        assert await t.join()

        t = await spawn(partial(func, z=3), 1, 2)
        assert await t.join()

    kernel.run(main)

def test_custom_cancel(kernel):
    class CustomCancelled(CancelledError):
        pass

    evt = Event()
    async def child():
        try:
            await evt.wait()
        except CustomCancelled:
            assert True
        except:
            assert False
        else:
            assert False

    async def main():
        t = await spawn(child)
        await t.cancel(exc=CustomCancelled)
    
    kernel.run(main)

def test_timeout_badness(kernel):
    import time
    async def main():
        async with timeout_after(0.1):
            time.sleep(0.2)   # Timeout will take too long. Should issue a warning.

        # Execution should make it here.  There were no blocking operations to cancel.
        # It makes no sense to issue a cancellation on the next operation because we're
        # Likely out of the timeout block
        assert True

    kernel.run(main)

def test_kernel_no_shutdown():
    # Code coverage test
    k = Kernel()
    del k

    with Kernel() as k:
        pass

    with pytest.raises(RuntimeError):
        k.run()


def test_kernel_exit():
    # Code coverage test
    async def main():
        raise SystemExit()

    with pytest.raises(SystemExit):
         with Kernel() as k:
             k.run(main)


def test_kernel_badtrap():
    # Code coverage test
    async def main():
        from curio.traps import _kernel_trap
        await _kernel_trap('bogus', 1)

    with pytest.raises(KeyError):
         with Kernel() as k:
             k.run(main)

def test_kernel_multischedule(kernel):
    async def sleeper():
        try:
            async with timeout_after(0.5):
                await sleep(0.25)
        except TaskTimeout:
            assert False

        await sleep(0.1)    # Should not crash!
        return True

    async def main():
        import time
        t = await spawn(sleeper)
        await sleep(0.1)
        time.sleep(1)     # Force time clock to elapse past both the sleep and outer timeout
        r = await t.join()
        assert r

    kernel.run(main)

def test_kernel_debug():
    from curio.debug import schedtrace, traptrace
    async def hello():
        await sleep(0)

    with Kernel(debug=[schedtrace,traptrace]) as k:
         k.run(hello)

    with Kernel(debug=True) as k:
         k.run(hello)

    with Kernel(debug=schedtrace) as k:
         k.run(hello)

    with Kernel(debug=schedtrace(filter='none')) as k:
        k.run(hello)

        


            
