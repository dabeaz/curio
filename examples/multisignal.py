# An example of receiving signals in curio, asyncio, and threads
# all at once using Curio's SignalSet functionality.

from curio.bridge import AsyncioLoop
from curio import *
import os
import signal
import threading

async def signal_task(label):
    async with SignalQueue(signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT) as s:
        while True:
            signo = await s.get()
            print(label, 'got:', signo)
            if signo == signal.SIGINT:
                print(label, 'Goodbye!')
                break

def signal_thread(label):
    with SignalQueue(signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT) as s:
        while True:
            signo = s.get()
            print(label, 'got:', signo)
            if signo == signal.SIGINT:
                print(label, 'Goodbye!')
                break

async def main():
    loop = AsyncioLoop()
    # Launch the *same* async function in curio and in asyncio (running in different threads)
    t1 = await spawn(signal_task, 'curio')
    t2 = await spawn(loop.run_asyncio(signal_task, 'asyncio'))

    # Launch an independent thread
    t3 = threading.Thread(target=signal_thread, args=('thread',))
    t3.start()
                       
    print('Send me signals on PID', os.getpid())

    await t1.join()
    await t2.join()
    await run_in_thread(t3.join)

if __name__ == '__main__':
    with enable_signals([signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT]):
        run(main())

    
    
