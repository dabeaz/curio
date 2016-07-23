# several_tasks.py
import curio

async def countdown(n):
    while n > 0:
        print('T-minus', n)
        await curio.sleep(1)
        n -= 1

async def kid():
    print('Building the Millenium Falcon in Minecraft')
    await curio.sleep(1000)

async def parent():
    kid_task = await curio.spawn(kid())
    await curio.sleep(5)

    print("Let's go")
    count_task = await curio.spawn(countdown(10))
    await count_task.join()

    print("We're leaving!")
    await kid_task.join()
    print('Leaving')

if __name__ == '__main__':
    curio.run(parent())
