# A hello world program. From the Curio tutorial at
# https://curio.readthedocs.org/en/latest/tutorial.html
#
import curio
import signal
import os

async def countdown(n):
    while n > 0:
        print('T-minus', n)
        await curio.sleep(1)
        n -= 1

start_evt = curio.Event()

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

async def kid():
    while True:
        try:
            print('Can I play?')
            await start_evt.wait(timeout=1)
            break
        except TimeoutError:
            print('Wha!?!')
    try:
        print('Building the Millenium Falcon in Minecraft')
        total = 0
        for n in range(50):
             total += await curio.run_cpu_bound(fib, n)
    except curio.CancelledError:
        print('Fine. Saving my work.')

async def parent():
    print('Parent PID', os.getpid())
    kid_task = await curio.new_task(kid())
    await curio.sleep(5)
    print("Yes, go play")
    await start_evt.set()

    await curio.SignalSet(signal.SIGHUP).wait()

    print("Let's go")
    count_task = await curio.new_task(countdown(10))
    await count_task.join()
    print("We're leaving!")
    try:
        await kid_task.join(timeout=10)
    except TimeoutError:
        print('I warned you!')
        await kid_task.cancel()
    print("Leaving!")

if __name__ == '__main__':
    kernel = curio.Kernel(with_monitor=True)
    kernel.run(parent())
