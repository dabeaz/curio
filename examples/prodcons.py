# prodcons.py

import curio

async def producer(queue):
    for n in range(10):
        await queue.put(n)
    await queue.join()
    print('Producer done')

async def consumer(queue):
    while True:
        item = await queue.get()
        print('Consumer got', item)
        await queue.task_done()

async def main():
    q = curio.Queue()
    prod_task = await curio.new_task(producer(q))
    cons_task = await curio.new_task(consumer(q))
    await prod_task.join()
    await cons_task.cancel()

if __name__ == '__main__':
    kernel = curio.Kernel()
    kernel.run(main())
