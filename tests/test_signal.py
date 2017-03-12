# test_signal.py

import time
from curio import *
import signal
import os


def test_task_signal(kernel):
    results = []

    evt = Event()
    async def child():
        async with SignalQueue(signal.SIGUSR1, signal.SIGUSR2) as sig:
            await evt.set()
            signo = await sig.get()
            results.append(signo)
            signo = await sig.get()
            results.append(signo)

    async def main():
        task = await spawn(child())
        await evt.wait()
        results.append('sending USR1')
        os.kill(os.getpid(), signal.SIGUSR1)
        await sleep(0.1)
        results.append('sending USR2')
        os.kill(os.getpid(), signal.SIGUSR2)
        await sleep(0.1)
        results.append('done')

    kernel.run(main())
    assert results == [
        'sending USR1',
        signal.SIGUSR1,
        'sending USR2',
        signal.SIGUSR2,
        'done',
    ]


def test_task_signal_event(kernel):
    results = []

    SigUSR1 = SignalEvent(signal.SIGUSR1)
    SigUSR2 = SignalEvent(signal.SIGUSR2)
    async def child():
        await SigUSR1.wait()
        results.append(signal.SIGUSR1)
        await SigUSR2.wait()
        results.append(signal.SIGUSR2)

    async def main():
        task = await spawn(child())
        await sleep(0.1)
        results.append('sending USR1')
        os.kill(os.getpid(), signal.SIGUSR1)
        await sleep(0.1)
        results.append('sending USR2')
        os.kill(os.getpid(), signal.SIGUSR2)
        await sleep(0.1)
        results.append('done')

    kernel.run(main())
    assert results == [
        'sending USR1',
        signal.SIGUSR1,
        'sending USR2',
        signal.SIGUSR2,
        'done',
    ]


def test_task_signal_timeout(kernel):
    results = []

    async def child():
        async with SignalQueue(signal.SIGUSR1, signal.SIGUSR2) as sig:
            try:
                signo = await timeout_after(1.0, sig.get())
                results.append(signo)
            except TaskTimeout:
                results.append('timeout')

    async def main():
        task = await spawn(child())
        await task.join()
        results.append('done')

    kernel.run(main())
    assert results == [
        'timeout',
        'done',
    ]
