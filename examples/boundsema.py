# boundsema.py
#
# Curio can often be extended to implement more specialized forms
# of basic concurrency primitives.  For example, here is how
# you could implement a bound semaphore.

from curio import Semaphore

class BoundedSemaphore(Semaphore):

    def __init__(self, value=1):
        self._bound = value
        super().__init__(value)

    @property
    def bound(self):
        return self._bound

    async def release(self):
        if self._value >= self._bound:
            raise ValueError('BoundedSemaphore released too many times')
        await super().release()

