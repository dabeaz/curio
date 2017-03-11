from curio import meta
from curio import *
import time

def test_blocking(kernel):
    @meta.blocking
    def func():
        return 1

    async def main():
         r = await func()
         assert r == 1

    assert func() == 1

    kernel.run(main)

@meta.cpubound
def cpufunc():
    return 1

def test_cpubound(kernel):
    async def main():
         r = await cpufunc()
         assert r == 1

    assert cpufunc() == 1
    kernel.run(main)


    
