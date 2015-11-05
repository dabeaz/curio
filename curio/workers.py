# curio/workers.py
#
# Copyright (C) 2015
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# Functions for performing work outside of curio.  This includes running functions
# in thread pools, process pools, etc.

from .kernel import _future_wait, new_task, sleep
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

__all__ = [ 'run_in_executor', 'run_blocking', 'run_cpu_bound', 'set_blocking_executor', 'set_cpu_executor' ]

_MAX_BLOCKING_THREADS = 16

_default_blocking_executor = None
_default_cpu_executor = None

def set_blocking_executor(exc):
    '''
    Set the executor used to execute code with the run_blocking() function.
    '''
    global _default_blocking_executor
    _default_blocking_executor = exc

def set_cpu_executor(exc):
    '''
    Set the executor used to execute code with the run_cpu_bound() function.
    '''
    global _default_cpu_executor
    _default_cpu_executor = exc

async def run_in_executor(exc, callable, *args, timeout=None):
    '''
    Run a callable in an executor (e.g., concurrent.futures.ThreadPoolExecutor) and return the result.
    '''
    future = exc.submit(callable, *args)
    await _future_wait(future, timeout=timeout)
    return future.result()

async def run_blocking(callable, *args, timeout=None):
    if _default_blocking_executor is None:
        set_blocking_executor(ThreadPoolExecutor(_MAX_BLOCKING_THREADS))
        
    return await run_in_executor(_default_blocking_executor, callable, *args, timeout=timeout)

async def run_cpu_bound(callable, *args, timeout=None):
    if _default_cpu_executor is None:
        set_cpu_executor(ProcessPoolExecutor())
    return await run_in_executor(_default_cpu_executor, callable, *args, timeout=timeout)

    
