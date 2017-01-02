import curio

from getting_started import countdown

start_evt = curio.Event()

async def kid():
    print('Can I play?')
    await start_evt.wait()
    try:
        print('Building the Millenium Falcon in Minecraft')
        await curio.sleep(1000)
    except curio.CancelledError:
        print('Fine. Saving my work.')

async def parent():
    kid_task = await curio.spawn(kid())
    await curio.sleep(5)

    print('Yes, go play')
    await start_evt.set()
    await curio.sleep(5)

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
