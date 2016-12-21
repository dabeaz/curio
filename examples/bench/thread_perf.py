# thread.py
#
# Performance test of submitting work to a thread pool

import time
import curio
from concurrent.futures import ThreadPoolExecutor
import asyncio

COUNT = 25000


def curio_test():
    async def main():
        for n in range(COUNT):
            await curio.run_in_thread(time.sleep, 0)

    start = time.time()
    curio.run(main())
    end = time.time()
    print('Curio:', end - start)


def future_test():
    pool = ThreadPoolExecutor()

    def main():
        for n in range(COUNT):
            f = pool.submit(time.sleep, 0)
            f.result()
    start = time.time()
    main()
    end = time.time()
    print('concurrent.futures:', end - start)


def asyncio_test():
    pool = ThreadPoolExecutor()

    async def main(loop):
        for n in range(COUNT):
            await loop.run_in_executor(pool, time.sleep, 0)

    loop = asyncio.get_event_loop()
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(loop)))
    end = time.time()
    print('asyncio:', end - start)


def uvloop_test():
    try:
        import uvloop
    except ImportError:
        return

    pool = ThreadPoolExecutor()

    async def main(loop):
        for n in range(COUNT):
            await loop.run_in_executor(pool, time.sleep, 0)

    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(loop)))
    end = time.time()
    print('uvloop:', end - start)


if __name__ == '__main__':
    asyncio_test()
    uvloop_test()
    future_test()
    curio_test()
