# getting_started.py
import curio

async def countdown(n):
    while n > 0:
        print('T-minus', n)
        await curio.sleep(1)
        n -= 1

if __name__ == '__main__':
    curio.run(countdown(10))
