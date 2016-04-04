# curio/workers.py
#
# Copyright (C) 2015
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# Functions for performing work outside of curio.  This includes running functions
# in threads, processes, and executors from the concurrent.futures module.

from concurrent.futures import Future
import multiprocessing
import threading
from collections import deque

from .kernel import _future_wait, CancelledError
from .sync import Semaphore

__all__ = [ 'run_in_executor', 'run_blocking', 'run_cpu_bound' ]

async def run_in_executor(exc, callable, *args, timeout=None):
    '''
    Run a callable in an executor (e.g.,
    concurrent.futures.ThreadPoolExecutor) and return the result.
    '''
    future = exc.submit(callable, *args)
    await _future_wait(future, timeout=timeout)
    return future.result()

MAX_WORKER_THREADS = 16

# The thread/process pools used by curio are not safe to use across
# multiple instances of the Curio kernel or in separate execution
# threads.  As such, they're stored in thread-local storage. 
_pools = threading.local()

class ThreadWorker(object):
    '''
    Worker that executes a callable on behalf of a curio task in a separate thread.
    '''
    def __init__(self):
        self.thread = None
        self.start_evt = threading.Event()
        self.request = None

    def _launch(self):
        self.thread = threading.Thread(target=self.run_worker, daemon=True)
        self.thread.start()

    def run_worker(self):
        while True:
            # Discussion: This thread performs work on behalf of a single
            # curio task that is blocked waiting for a result. The control
            # flow is as follows:
            #
            #     1.  The apply() method below stores a request
            #     2.  An event (start_evt) is triggered.
            #     3.  The run_worker() method waits for the event
            #         and runs the requested callable.
            #     4.  The result is stored on a Future
            #
            self.start_evt.wait()
            self.start_evt.clear()

            # If there is no pending request, but we were signalled to
            # start, it means that we should quit
            if not self.request:
                return

            func, args, kwargs, future = self.request
            try:
                result = func(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

    def shutdown(self):
        self.request = None
        self.start_evt.set()

    async def apply(self, func, args=(), kwargs={}, timeout=None):
        '''
        Run the callable func in a separate thread and return the result.
        '''
        if self.thread is None:
            self._launch()

        # Set up a request for the worker thread
        future = Future()
        self.request = (func, args, kwargs, future)
        self.start_evt.set()

        # Wait for the result to be computed
        await _future_wait(future, timeout=timeout)
        return future.result()

class ThreadPool(object):
    def __init__(self, nworkers=None):
        if nworkers is None:
            nworkers = MAX_WORKER_THREADS

        self.nworkers = Semaphore(nworkers)
        self.workers = deque([ThreadWorker() for n in range(nworkers)])
        
    def __del__(self):
        for worker in self.workers:
            worker.shutdown()
        self.workers = None

    async def apply(self, func, args=(), kwargs={}, timeout=None):
         async with self.nworkers:
             worker = self.workers.popleft()
             try:
                 return await worker.apply(func, args, kwargs, timeout=timeout)
             except (CancelledError, TimeoutError) as e:
                 # If a worker is timed out or cancelled, there is no way to
                 # forcefully terminate the backing worker thread. It will
                 # run to completion.  However, we can remove the worker from
                 # the pool of available workers and instruct it to shut down
                 # when it completes.  Meanwhile, we'll replace it with a fresh
                 # worker.
                 worker.request = None
                 worker.start_evt.set()
                 worker = ThreadWorker()
                 raise
             finally:
                 self.workers.append(worker)

async def run_blocking(callable, *args, timeout=None):
    if not hasattr(_pools, 'blocking'):
        _pools.blocking = ThreadPool()
    return await _pools.blocking.apply(callable, args, timeout=timeout)


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
            self.shutdown()

    def _launch(self):
        client_ch, server_ch = multiprocessing.Pipe()
        self.process = multiprocessing.Process(target=self.run_server, args=(server_ch,), daemon=True)
        self.process.start()
        server_ch.close()
        self.client_ch = Channel.from_Connection(client_ch)

    def shutdown(self):
        if self.process:
            self.process.terminate()
            self.process = None

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

        if self.process is None or not self.process.is_alive():    # process not running
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

async def run_cpu_bound(callable, *args, timeout=None):
    if not hasattr(_pools, 'cpu'):
        _pools.cpu = ProcessPool()
    return await _pools.cpu.apply(callable, args)

from .channel import Channel
