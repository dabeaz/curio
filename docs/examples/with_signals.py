import signal, os

import curio

from task_synchronization import countdown, kid, start_evt

async def parent():
    print('Parent PID', os.getpid())
    kid_task = await curio.spawn(kid())
    await curio.sleep(5)

    print('Yes, go play')
    await start_evt.set()

    await curio.SignalSet(signal.SIGHUP).wait()

    print("Let's go")
    count_task = await curio.spawn(countdown(10))
    await count_task.join()
    print("We're leaving!")
    try:
        await curio.timeout_after(10, kid_task.join())
    except curio.TaskTimeout:
        print('I warned you!')
        await kid_task.cancel()
    print('Leaving!')

if __name__ == '__main__':
    curio.run(parent())
