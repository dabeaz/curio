# thread.py
#
# Performance test of submitting work to a thread pool

import time
import curio
from concurrent.futures import ThreadPoolExecutor
import asyncio

def curio_test():
    async def main():
        for n in range(10000):
            await curio.run_in_thread(time.sleep, 0)
    kernel = curio.Kernel()
    start = time.time()
    kernel.run(main())
    end = time.time()
    print('Curio:', end-start)

def future_test():
    pool = ThreadPoolExecutor()
    def main():
        for n in range(10000):
            f = pool.submit(time.sleep, 0)
            r = f.result()
    start = time.time()
    main()
    end =  time.time()
    print('concurrent.futures:', end-start)

def asyncio_test():
    pool = ThreadPoolExecutor()
    async def main(loop):
        for n in range(10000):
            r = await loop.run_in_executor(pool, time.sleep, 0)

    loop = asyncio.get_event_loop()
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(loop)))
    end = time.time()
    print('asyncio:', end-start)
    
if __name__ == '__main__':
    asyncio_test()
    future_test()
    curio_test()




        
