# test_sync.py
#
# Different test scenarios designed to run under management of a kernel

from collections import deque
from curio import *
import pytest
import threading
import time
import asyncio

# ---- Synchronization primitives


class TestEvent:

    def test_event_get_wait(self, kernel):
        results = []
        async def event_setter(evt, seconds):
            results.append('sleep')
            await sleep(seconds)
            results.append('event_set')
            await evt.set()

        async def event_waiter(evt):
            results.append('wait_start')
            results.append(evt.is_set())
            await evt.wait()
            results.append('wait_done')
            results.append(evt.is_set())
            evt.clear()
            results.append(evt.is_set())

        async def main():
            evt = Event()
            t1 = await spawn(event_waiter, evt)
            t2 = await spawn(event_setter, evt, 1)
            await t1.join()
            await t2.join()

        kernel.run(main())
        assert results == [
            'wait_start',
            False,
            'sleep',
            'event_set',
            'wait_done',
            True,
            False
        ]

    def test_event_get_immediate(self, kernel):
        results = []
        async def event_setter(evt):
            results.append('event_set')
            await evt.set()

        async def event_waiter(evt, seconds):
            results.append('sleep')
            await sleep(seconds)
            results.append('wait_start')
            await evt.wait()
            results.append('wait_done')

        async def main():
            evt = Event()
            t1 = await spawn(event_waiter, evt, 1)
            t2 = await spawn(event_setter, evt)
            await t1.join()
            await t2.join()

        kernel.run(main())
        assert results == [
            'sleep',
            'event_set',
            'wait_start',
            'wait_done',
        ]

    def test_event_wait_cancel(self, kernel):
        results = []
        async def event_waiter(evt):
            results.append('event_wait')
            try:
                await evt.wait()
            except CancelledError:
                results.append('event_cancel')

        async def event_cancel(seconds):
            evt = Event()
            task = await spawn(event_waiter, evt)
            results.append('sleep')
            await sleep(seconds)
            results.append('cancel_start')
            await task.cancel()
            results.append('cancel_done')

        kernel.run(event_cancel(1))

        assert results == [
            'sleep',
            'event_wait',
            'cancel_start',
            'event_cancel',
            'cancel_done',
        ]

    def test_event_wait_timeout(self, kernel):
        results = []
        async def event_waiter(evt):
            results.append('event_wait')
            try:
                await timeout_after(0.5, evt.wait())
            except TaskTimeout:
                results.append('event_timeout')

        async def event_run(seconds):
            evt = Event()
            task = await spawn(event_waiter, evt)
            results.append('sleep')
            await sleep(seconds)
            results.append('sleep_done')
            await task.join()

        kernel.run(event_run(1))

        assert results == [
            'sleep',
            'event_wait',
            'event_timeout',
            'sleep_done',
        ]

    def test_event_wait_notimeout(self, kernel):
        results = []
        async def event_waiter(evt):
            results.append('event_wait')
            try:
                await timeout_after(1.0, evt.wait())
                results.append('got event')
            except TaskTimeout:
                results.append('event_timeout')

            evt.clear()
            try:
                await evt.wait()
                results.append('got event')
            except TaskTimeout:
                results.append('bad timeout')

        async def event_run():
            evt = Event()
            task = await spawn(event_waiter, evt)
            results.append('sleep')
            await sleep(0.25)
            results.append('event_set')
            await evt.set()
            await sleep(1.0)
            results.append('event_set')
            await evt.set()
            await task.join()

        kernel.run(event_run())
        assert results == [
            'sleep',
            'event_wait',
            'event_set',
            'got event',
            'event_set',
            'got event'
        ]



class TestLock:

    def test_lock_sequence(self, kernel):
        results = []
        async def worker(lck, label):
            results.append(label + ' wait')
            results.append(lck.locked())
            async with lck:
                results.append(label + ' acquire')
                await sleep(0.25)
            results.append(label + ' release')

        async def main():
            lck = Lock()
            t1 = await spawn(worker, lck, 'work1')
            t2 = await spawn(worker, lck, 'work2')
            t3 = await spawn(worker, lck, 'work3')
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(main())
        assert results == [
            'work1 wait',
            False,
            'work1 acquire',
            'work2 wait',
            True,
            'work3 wait',
            True,
            'work1 release',
            'work2 acquire',
            'work2 release',
            'work3 acquire',
            'work3 release',
        ]

    def test_lock_acquire_cancel(self, kernel):
        results = []
        async def worker(lck):
            results.append('lock_wait')
            try:
                async with lck:
                    results.append('never here')
            except CancelledError:
                results.append('lock_cancel')

        async def worker_cancel(seconds):
            lck = Lock()
            async with lck:
                task = await spawn(worker, lck)
                results.append('sleep')
                await sleep(seconds)
                results.append('cancel_start')
                await task.cancel()
                results.append('cancel_done')

        kernel.run(worker_cancel(1))

        assert results == [
            'sleep',
            'lock_wait',
            'cancel_start',
            'lock_cancel',
            'cancel_done',
        ]

    def test_lock_acquire_timeout(self, kernel):
        results = []
        async def worker(lck):
            results.append('lock_wait')
            try:
                await timeout_after(0.5, lck.acquire())
                results.append('never here')
                await lck.release()
            except TaskTimeout:
                results.append('lock_timeout')

        async def worker_timeout(seconds):
            lck = Lock()
            async with lck:
                w = await spawn(worker, lck)
                results.append('sleep')
                await sleep(seconds)
                results.append('sleep_done')
                await w.join()

        kernel.run(worker_timeout(1))

        assert results == [
            'sleep',
            'lock_wait',
            'lock_timeout',
            'sleep_done',
        ]


class TestRLock:

    def test_rlock_reenter(self, kernel):
        results = []

        async def inner(lck, label):
            results.append(lck.locked())
            async with lck:
                results.append(label + ' inner acquired')
                results.append(label + ' inner releasing')

        async def worker(lck, label):
            results.append(lck.locked())
            results.append(label + ' wait')
            async with lck:
                results.append(label + ' acquired')
                await sleep(0.25)
                await inner(lck, label)
                results.append(label + ' releasing')

        async def worker_simple(lck):
            results.append('simple wait')
            async with lck:
                results.append('simple acquired')
                results.append('simple releasing')

        async def main():
            lck = RLock()
            t1 = await spawn(worker, lck, 'work1')
            t2 = await spawn(worker, lck, 'work2')
            t3 = await spawn(worker_simple, lck)
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(main())
        assert results == [
            False,
            'work1 wait',
            'work1 acquired',
            True,
            'work2 wait',
            'simple wait',
            True,
            'work1 inner acquired',
            'work1 inner releasing',
            'work1 releasing',
            'work2 acquired',
            True,
            'work2 inner acquired',
            'work2 inner releasing',
            'work2 releasing',
            'simple acquired',
            'simple releasing'
        ]

    def test_rlock_notowner(self, kernel):
        async def child1(lck):
            await lck.acquire()
            await sleep(0.25)
            await lck.release()

        async def child2(lck):
            await sleep(0.1)
            with pytest.raises(RuntimeError):
                await lck.release()

        async def main():
            lck = RLock()
            with pytest.raises(RuntimeError):
                await lck.release()

            t1 = await spawn(child1, lck)
            t2 = await spawn(child2, lck)
            await t1.join()
            await t2.join()

        kernel.run(main)


class TestSemaphore:

    def test_sema_sequence(self, kernel):
        results = []
        async def worker(sema, label):
            results.append(label + ' wait')
            results.append(sema.locked())
            async with sema:
                assert sema.value == 0
                results.append(label + ' acquire')
                await sleep(0.25)
            results.append(label + ' release')

        async def main():
            sema = Semaphore()
            t1 = await spawn(worker, sema, 'work1')
            t2 = await spawn(worker, sema, 'work2')
            t3 = await spawn(worker, sema, 'work3')
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(main())

        assert results == [
            'work1 wait',
            False,
            'work1 acquire',
            'work2 wait',
            True,
            'work3 wait',
            True,
            'work1 release',
            'work2 acquire',
            'work2 release',
            'work3 acquire',
            'work3 release',
        ]

    def test_sema_sequence2(self, kernel):
        results = []
        async def worker(sema, label, seconds):
            results.append(label + ' wait')
            results.append(sema.locked())
            async with sema:
                results.append(label + ' acquire')
                await sleep(seconds)
            results.append(label + ' release')

        async def main():
            sema = Semaphore(2)
            t1 = await spawn(worker, sema, 'work1', 0.25)
            t2 = await spawn(worker, sema, 'work2', 0.30)
            t3 = await spawn(worker, sema, 'work3', 0.35)
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(main())
        assert results == [
            'work1 wait',            # Both work1 and work2 admitted
            False,
            'work1 acquire',
            'work2 wait',
            False,
            'work2 acquire',
            'work3 wait',
            True,
            'work1 release',
            'work3 acquire',
            'work2 release',
            'work3 release',
        ]

    def test_sema_acquire_cancel(self, kernel):
        results = []
        async def worker(lck):
            results.append('lock_wait')
            try:
                async with lck:
                    results.append('never here')
            except CancelledError:
                results.append('lock_cancel')

        async def worker_cancel(seconds):
            lck = Semaphore()
            async with lck:
                task = await spawn(worker, lck)
                results.append('sleep')
                await sleep(seconds)
                results.append('cancel_start')
                await task.cancel()
                results.append('cancel_done')

        kernel.run(worker_cancel(1))

        assert results == [
            'sleep',
            'lock_wait',
            'cancel_start',
            'lock_cancel',
            'cancel_done',
        ]

    def test_sema_acquire_timeout(self, kernel):
        results = []
        async def worker(lck):
            results.append('lock_wait')
            try:
                await timeout_after(0.5, lck.acquire())
                results.append('never here')
                await lck.release()
            except TaskTimeout:
                results.append('lock_timeout')

        async def worker_timeout(seconds):
            lck = Semaphore()
            async with lck:
                w = await spawn(worker, lck)
                results.append('sleep')
                await sleep(seconds)
                results.append('sleep_done')
                await w.join()

        kernel.run(worker_timeout(1))

        assert results == [
            'sleep',
            'lock_wait',
            'lock_timeout',
            'sleep_done',
        ]


class TestCondition:

    def test_cond_sequence(self, kernel):
        results = []
        async def consumer(cond, q, label):
            while True:
                async with cond:
                    if not q:
                        results.append(label + ' wait')
                        await cond.wait()
                    item = q.popleft()
                    if item is None:
                        break
                    results.append((label, item))
            results.append(label + ' done')

        async def producer(cond, q, count, nproducers):
            for n in range(count):
                async with cond:
                    q.append(n)
                    results.append(('producing', n))
                    await cond.notify()
                await sleep(0.1)

            for n in range(nproducers):
                async with cond:
                    q.append(None)
                    results.append(('ending', n))
                    await cond.notify()
                await sleep(0.1)

        async def main():
            cond = Condition(Lock())
            q = deque()
            t1 = await spawn(consumer, cond, q, 'cons1')
            t2 = await spawn(consumer, cond, q, 'cons2')
            t3 = await spawn(producer, cond, q, 4, 2)
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(main())

        assert results == [
            'cons1 wait',
            'cons2 wait',
            ('producing', 0),
            ('cons1', 0),
            'cons1 wait',
            ('producing', 1),
            ('cons2', 1),
            'cons2 wait',
            ('producing', 2),
            ('cons1', 2),
            'cons1 wait',
            ('producing', 3),
            ('cons2', 3),
            'cons2 wait',
            ('ending', 0),
            ('cons1 done'),
            ('ending', 1),
            ('cons2 done')
        ]

    def test_cond_wait_cancel(self, kernel):
        results = []
        async def worker(cond):
            try:
                async with cond:
                    results.append('cond_wait')
                    await cond.wait()
                    results.append('never here')
            except CancelledError:
                results.append('worker_cancel')

        async def worker_cancel(seconds):
            cond = Condition()
            task = await spawn(worker, cond)
            results.append('sleep')
            await sleep(seconds)
            results.append('cancel_start')
            await task.cancel()
            results.append('cancel_done')

        kernel.run(worker_cancel(1))

        assert results == [
            'sleep',
            'cond_wait',
            'cancel_start',
            'worker_cancel',
            'cancel_done',
        ]

    def test_cond_wait_timeout(self, kernel):
        results = []
        async def worker(cond):
            try:
                async with cond:
                    results.append('cond_wait')
                    await timeout_after(0.25, cond.wait())
                    results.append('never here')
            except TaskTimeout:
                results.append('worker_timeout')

        async def worker_cancel(seconds):
            cond = Condition()
            task = await spawn(worker, cond)
            results.append('sleep')
            await sleep(seconds)
            results.append('done')
            await task.join()

        kernel.run(worker_cancel(1))

        assert results == [
            'sleep',
            'cond_wait',
            'worker_timeout',
            'done'
        ]

    def test_cond_notify_all(self, kernel):
        results = []
        async def worker(cond):
            async with cond:
                results.append('cond_wait')
                await cond.wait()
                results.append('wait_done')

        async def worker_notify(seconds):
            cond = Condition()
            t1 = await spawn(worker, cond)
            t2 = await spawn(worker, cond)
            t3 = await spawn(worker, cond)
            results.append('sleep')
            await sleep(seconds)
            async with cond:
                results.append('notify')
                await cond.notify_all()
            results.append('done')
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(worker_notify(1))

        assert results == [
            'sleep',
            'cond_wait',
            'cond_wait',
            'cond_wait',
            'notify',
            'done',
            'wait_done',
            'wait_done',
            'wait_done',
        ]

    def test_cond_waitfor(self, kernel):
        results = []
        async def consumer(cond, q, label):
            async with cond:
                results.append(label + ' waitfor')
                await cond.wait_for(lambda: len(q) > 2)
                results.append((label, len(q)))
            results.append(label + ' done')

        async def producer(cond, q, count):
            for n in range(count):
                async with cond:
                    q.append(n)
                    results.append(('producing', n))
                    await cond.notify()
                await sleep(0.1)

        async def main():
            cond = Condition()
            q = deque()
            t1 = await spawn(consumer, cond, q, 'cons1')
            t2 = await spawn(consumer, cond, q, 'cons2')
            t3 = await spawn(producer, cond, q, 4)
            await t1.join()
            await t2.join()
            await t3.join()

        kernel.run(main())
        assert results == [
            'cons1 waitfor',
            'cons2 waitfor',
            ('producing', 0),
            ('producing', 1),
            ('producing', 2),
            ('cons1', 3),
            'cons1 done',
            ('producing', 3),
            ('cons2', 4),
            'cons2 done'
        ]

    def test_condition_error(self, kernel):
        async def main():
            c = Condition()
            with pytest.raises(RuntimeError):
                await c.notify()

            with pytest.raises(RuntimeError):
                await c.wait()

        kernel.run(main)

class TestUniversalEvent:

    def test_uevent_get_wait(self, kernel):
        results = []
        async def event_setter(evt, seconds):
            results.append('sleep')
            await sleep(seconds)
            results.append('event_set')
            await evt.set()

        async def event_waiter(evt):
            results.append('wait_start')
            results.append(evt.is_set())
            await evt.wait()
            results.append('wait_done')
            results.append(evt.is_set())
            evt.clear()
            results.append(evt.is_set())

        async def main():
            evt = UniversalEvent()
            t1 = await spawn(event_waiter, evt)
            t2 = await spawn(event_setter, evt, 1)
            await t1.join()
            await t2.join()

        kernel.run(main())
        assert results == [
            'wait_start',
            False,
            'sleep',
            'event_set',
            'wait_done',
            True,
            False
        ]


    def test_uevent_get_twait(self, kernel):
        results = []
        async def event_setter(evt, seconds):
            results.append('sleep')
            await sleep(seconds)
            results.append('event_set')
            await evt.set()

        def event_waiter(evt):
            results.append('wait_start')
            results.append(evt.is_set())
            evt.wait()
            results.append('wait_done')
            results.append(evt.is_set())
            evt.clear()
            results.append(evt.is_set())

        async def main():
            evt = UniversalEvent()
            t1 = threading.Thread(target=event_waiter, args=(evt,))
            t1.start()
            t2 = await spawn(event_setter, evt, 1)
            await run_in_thread(t1.join)
            await t2.join()

        kernel.run(main())
        assert results == [
            'wait_start',
            False,
            'sleep',
            'event_set',
            'wait_done',
            True,
            False
        ]

    def test_uevent_get_asyncio_set(self, kernel):
        results = []
        async def event_setter(evt, seconds):
            results.append('sleep')
            await asyncio.sleep(seconds)
            results.append('event_set')
            await evt.set()

        async def event_waiter(evt):
            results.append('wait_start')
            results.append(evt.is_set())
            await evt.wait()
            results.append('wait_done')
            results.append(evt.is_set())
            evt.clear()
            results.append(evt.is_set())

        async def main():
            evt = UniversalEvent()
            t1 = await spawn(event_waiter, evt)
            await sleep(0.05)
            t2 = threading.Thread(target=asyncio.run, args=[event_setter(evt, 1)])
            t2.start()
            await t1.join()
            await run_in_thread(t2.join)

        kernel.run(main())
        assert results == [
            'wait_start',
            False,
            'sleep',
            'event_set',
            'wait_done',
            True,
            False
        ]


    def test_uevent_get_asyncio_wait(self, kernel):
        results = []
        async def event_setter(evt, seconds):
            results.append('sleep')
            await sleep(seconds)
            results.append('event_set')
            await evt.set()

        async def event_waiter(evt):
            results.append('wait_start')
            results.append(evt.is_set())
            await evt.wait()
            results.append('wait_done')
            results.append(evt.is_set())
            evt.clear()
            results.append(evt.is_set())

        async def main():
            evt = UniversalEvent()
            t1 = threading.Thread(target=asyncio.run, args=[event_waiter(evt)])
            t1.start()
            await sleep(0.1)
            t2 = await spawn(event_setter, evt, 1)
            await run_in_thread(t1.join)
            await t2.join()

        kernel.run(main())
        assert results == [
            'wait_start',
            False,
            'sleep',
            'event_set',
            'wait_done',
            True,
            False
        ]

class TestUniversalResult:
    def test_universal_result(self, kernel):
        
        def work(x, y, r):
            time.sleep(0.25)
            r.set_result(x+y)

        async def main(r1, r2):
            value = await r1.result()
            await r2.set_result(value)

        r1 = UniversalResult()
        r2 = UniversalResult()
        r3 = UniversalResult()
        threading.Thread(target=work, args=[2,3,r1]).start()
        threading.Thread(target=asyncio.run, args=[main(r1, r2)]).start()
        kernel.run(main, r2, r3)
        assert r3.result() == 5

def test_repr():
    # For test coverage
    for cls in [Lock, Event, Semaphore, Condition, RLock, UniversalEvent, UniversalResult ]:
        repr(cls())
