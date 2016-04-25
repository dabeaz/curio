# process.py
#
# Performance test of submitting work to a process pool. 

import time
import curio
from multiprocessing import Pool
from concurrent.futures import ProcessPoolExecutor
import asyncio

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

def curio_test(x):
    async def main():
        for n in range(10000):
            r = await curio.run_in_process(fib, x)
    kernel = curio.Kernel()
    start = time.time()
    kernel.run(main())
    end = time.time()
    print('Curio:', end-start)

def mp_test(x):
    pool = Pool()
    def main():
        for n in range(10000):
            r = pool.apply(fib, (x,))
    start = time.time()
    main()
    end = time.time()
    print('multiprocessing:', end-start)

def future_test(x):
    pool = ProcessPoolExecutor()
    def main():
        for n in range(10000):
            f = pool.submit(fib, x)
            r = f.result()
    start = time.time()
    main()
    end =  time.time()
    print('concurrent.futures:', end-start)

def asyncio_test(x):
    pool = ProcessPoolExecutor()
    async def main(loop):
        for n in range(10000):
            r = await loop.run_in_executor(pool, fib, x)

    loop = asyncio.get_event_loop()
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(loop)))
    end = time.time()
    print('asyncio:', end-start)
    
if __name__ == '__main__':
    x = 1
    asyncio_test(x)
    future_test(x)
    mp_test(x)
    curio_test(x)




        
