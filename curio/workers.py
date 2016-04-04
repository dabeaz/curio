# curio/workers.py
#
# Copyright (C) 2015
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# Functions for performing work outside of curio.  This includes running functions
# in thread pools, process pools, etc.

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing
from collections import deque

from .kernel import _future_wait, new_task, sleep, CancelledError
from .queue import Queue
from .sync import Event, Semaphore

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

_default_cpu_pool = None
def set_cpu_pool(pool):
    global _default_cpu_pool
    _default_cpu_pool = pool

async def run_cpu_bound(callable, *args, timeout=None):
    if _default_cpu_executor is None:
        set_cpu_executor(ProcessPoolExecutor())
    return await run_in_executor(_default_cpu_executor, callable, *args, timeout=timeout)

async def run_cpu_bound(callable, *args, timeout=None):
    if _default_cpu_pool is None:
        set_cpu_pool(ProcessPool())

    return await _default_cpu_pool.apply(callable, args)

class ProcessWorker(object):
    '''
    Managed process worker for running CPU-intensive tasks.  The main
    purpose of this class is to run workers with reliable
    cancellation/timeout semantics. Specifically, if a worker is
    cancelled, the underlying process is also killed.   This, as
    opposed to having it linger on running until work is complete.
    '''
    restart_limit = None

    def __init__(self):
        self.process = None
        self.nrequests = 0

    def __del__(self):
        if self.process:
            self.process.terminate()
            self.process = None

    def _launch(self):
        client_ch, server_ch = multiprocessing.Pipe()
        self.process = multiprocessing.Process(target=self.run_server, args=(server_ch,), daemon=True)
        self.process.start()
        server_ch.close()
        self.client_ch = Channel.from_Connection(client_ch)

    def run_server(self, ch):
        while True:
            func, args, kwargs = ch.recv()
            try:
                result = func(*args, **kwargs)
                ch.send((True, result))
            except Exception as e:
                ch.send((False, e))
            func = args = kwargs = None
    
    async def apply(self, func, args=(), kwargs={}):
        self.nrequests += 1
        if self.nrequests == self.restart_limit:
            print('Restarting')
            self.process.terminate()
            self.process = None
            self.nrequests = 1

        if self.process is None:
            self._launch()
        try:
            return await self.client_ch.rpc_client(func, args, kwargs)

        except (CancelledError, TimeoutError) as e:
            self.process.terminate()
            self.process = None
            self.nrequests = 0
            raise

class ProcessPool(object):
    def __init__(self, nworkers=None):
        if nworkers is None:
            nworkers = multiprocessing.cpu_count()
        self.nworkers = Semaphore(nworkers)
        self.workers = deque([ProcessWorker() for n in range(nworkers)])

    async def apply(self, func, args=(), kwargs={}):
         async with self.nworkers:
             worker = self.workers.popleft()
             try:
                 return await worker.apply(func, args, kwargs)
             finally:
                 self.workers.append(worker)

from .channel import Channel
