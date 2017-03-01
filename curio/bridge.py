# bridge.py
#
# Support for running asyncio coroutines from within curio.
# The curio->asyncio bridge runs a separate asyncio event loop in a different thread,
# which has coroutines submitted to it over the course of the kernel's lifetime.

import asyncio

from .traps import _get_kernel
from .sync import Event, abide

__all__ = ["acb"]


async def acb(coro):
    '''
    Runs a coroutine in the current event loop running alongside this kernel.
    '''
    kernel = await _get_kernel()
    finished_ev = Event()
    # How this works:
    # First, it schedules a new coroutine on the kernel's asyncio loop,
    # which will be running alongside.
    # Then, it will simply wait for the result in another thread (yay threading!)
    #
    # Possible improvements:
    #  1) Wrap the future in a Task which can be `.join`'d on rather than
    #     waiting on an event.
    #  2) Force the user to pass their own loop in, instead of having the kernel
    #     manage it.
    loop = kernel._asyncio_loop
    fut = asyncio.run_coroutine_threadsafe(coro, loop)

    return await abide(fut.result)
