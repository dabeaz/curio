# An example of receiving signals in curio and threads
# all at once using Curio's SignalSet functionality.

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
    # Launch the async function in curio
    t1 = await spawn(signal_task, 'curio')

    # Launch an independent thread
    t2 = threading.Thread(target=signal_thread, args=('thread',))
    t2.start()
                       
    print('Send me signals on PID', os.getpid())

    await t1.join()
    await run_in_thread(t2.join)

if __name__ == '__main__':
    with enable_signals([signal.SIGUSR1, signal.SIGUSR2, signal.SIGINT]):
        run(main())

    
    
