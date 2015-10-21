# A hello world program

import curio

async def countdown(n):
    while n > 0:
        print('T-minus', n)
        await curio.sleep(1)
        n -= 1
    print("We're leaving!")

async def kid():
    await curio.sleep(2)
    print('Just a minute!')
    await curio.sleep(4)
    print('I need to finish building this Millenium Falcon in Minecraft')
    await curio.sleep(5)
    print('ARGH!')

if __name__ == '__main__':
    kernel = curio.Kernel()
    kernel.add_task(countdown(10))
    kernel.add_task(kid())
    kernel.run()
