# test_signal.py

import time
from curio import *
import signal, os

def test_task_signal(kernel):
    results = []

    async def child():
        async with SignalSet(signal.SIGUSR1, signal.SIGUSR2) as sig:
            signo = await sig.wait()
            results.append(signo)
            signo = await sig.wait()
            results.append(signo)

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

def test_task_signal_waitone(kernel):
    results = []

    async def child():
        sig = SignalSet(signal.SIGUSR1, signal.SIGUSR2)
        signo = await sig.wait()
        results.append(signo)
        signo = await sig.wait()
        results.append(signo)

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

def test_task_signal_ignore(kernel):
    results = []

    async def child():
        sig = SignalSet(signal.SIGUSR1, signal.SIGUSR2)
        async with sig:
             signo = await sig.wait()
             results.append(signo)
             with sig.ignore():
                 await sleep(1)
             results.append('here')

    async def main():
        task = await spawn(child())
        await sleep(0.1)
        results.append('sending USR1')
        os.kill(os.getpid(), signal.SIGUSR1)
        await sleep(0.5)
        results.append('sending USR1')
        os.kill(os.getpid(), signal.SIGUSR1)
        await sleep(0.1)
        await task.join()
        results.append('done')

    kernel.run(main())
    assert results == [
            'sending USR1',
            signal.SIGUSR1,
            'sending USR1',
            'here',
            'done',
            ]

def test_task_signal_timeout(kernel):
    results = []

    async def child():
        async with SignalSet(signal.SIGUSR1, signal.SIGUSR2) as sig:
            try:
                signo = await timeout_after(1.0, sig.wait())
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
