# process.py
#
# Performance test of submitting work to a process pool. 

import time
import curio
from multiprocessing import Pool
from concurrent.futures import ProcessPoolExecutor
import asyncio

COUNT = 10000

def fib(n):
    if n <= 2:
        return 1
    else:
        return fib(n-1) + fib(n-2)

def curio_test(x):
    async def main():
        for n in range(COUNT):
            r = await curio.run_in_process(fib, x)
    start = time.time()
    curio.run(main())
    end = time.time()
    print('Curio:', end-start)

def mp_test(x):
    pool = Pool()
    def main():
        for n in range(COUNT):
            r = pool.apply(fib, (x,))
    start = time.time()
    main()
    end = time.time()
    print('multiprocessing:', end-start)

def future_test(x):
    pool = ProcessPoolExecutor()
    def main():
        for n in range(COUNT):
            f = pool.submit(fib, x)
            r = f.result()
    start = time.time()
    main()
    end =  time.time()
    print('concurrent.futures:', end-start)

def asyncio_test(x):
    pool = ProcessPoolExecutor()
    async def main(loop):
        for n in range(COUNT):
            r = await loop.run_in_executor(pool, fib, x)

    loop = asyncio.get_event_loop()
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(loop)))
    end = time.time()
    print('asyncio:', end-start)

def uvloop_test(x):
    try:
        import uvloop
    except ImportError:
        return

    pool = ProcessPoolExecutor()
    async def main(loop):
        for n in range(COUNT):
            r = await loop.run_in_executor(pool, fib, x)

    loop = uvloop.new_event_loop()
    asyncio.set_event_loop(loop)
    start = time.time()
    loop.run_until_complete(asyncio.ensure_future(main(loop)))
    end = time.time()
    print('uvloop:', end-start)
    
if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        raise SystemExit('Usage: %s n' % sys.argv[0])
    x = int(sys.argv[1])
    asyncio_test(x)
    uvloop_test(x)
    future_test(x)
    mp_test(x)
    curio_test(x)




        
