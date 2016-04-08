# curio/workers.py
#
# Copyright (C) 2015
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# Functions for performing work outside of curio.  This includes running functions
# in threads, processes, and executors from the concurrent.futures module.

import multiprocessing
import threading

from .kernel import _future_wait, CancelledError, _get_kernel
from .sync import Semaphore

__all__ = [ 'run_in_executor', 'run_blocking', 'run_cpu_bound' ]

async def run_in_executor(exc, callable, *args, timeout=None):
    '''
    Run callable(*args) in an executor such as ThreadPoolExecutor or
    ProcessPoolExecutor from the concurrent.futures module.  If a
    timeout is specified, the request will be aborted after that many
    seconds and a TimeoutError exception will be raised. Be aware that
    on timeout, any worker thread or process that was handling the
    request will continue to run to completion as a kind of zombie--
    possibly rendering the executor unusable for subsequent work.

    This function is provided for compatibility with concurrent.futures,
    but is not the recommend approach for running blocking or cpu-bound
    work in curio. Use the run_in_thread() or run_in_process() methods
    instead.
    '''
    future = exc.submit(callable, *args)
    await _future_wait(future, timeout=timeout)
    return future.result()

async def run_in_thread(callable, *args, timeout=None):
    '''
    Run callable(*args) in a separate thread and return the result.
    If a timeout is specified, the request will be aborted and a
    TimeoutError raised.  It's not possible to terminate threads so if
    a timeout or cancellation occurs, the associated worker will
    continue to run until completion as a kind of zombie.  In this
    case, the worker will be removed from the pool of available
    threads and terminated as soon as it completes.
    '''
    kernel = await _get_kernel()
    if not kernel._thread_pool:
        kernel._thread_pool = ThreadPool()
    return await kernel._thread_pool.apply(callable, args, timeout=timeout)

run_blocking = run_in_thread

MAX_WORKER_THREADS = 16


# The _FutureLess class is a stripped implementation of the
# concurrent.futures.Future class that has been custom-tailored for
# use by curio.  It is used by the ThreadWorker class below.  The main
# reason for using this instead of the normal Future class is that
# curio doesn't need most of the advanced features of Futures nor does
# it require all of the internal thread-synchronization and
# notification support.  By ditching that, the handoff between
# curio tasks and threads is streamlined.
class _FutureLess(object):
    __slots__ = ('_callback', '_exception', '_result')

    def set_result(self, result):
        self._result = result
        self._callback(self)

    def set_exception(self, exc):
        self._exception = exc
        self._callback(self)

    def result(self):
        try:
            return self._result
        except AttributeError:
            return self._exception
        
    def add_done_callback(self, func):
        self._callback = func

    def cancel(self):
        pass

# A ThreadWorker represents a thread that performs work on behalf of a
# curio task.  The execution model is purely synchronous and similar
# to a "hand off."  A curio task initiates work by executing the
# apply() method. This passes the request to a background thread that
# executes it.  While this takes place, the curio task blocks, waiting
# for a result to be set on an internal Future.
#
# The purely synchronous nature of the execution model simplfies the
# implementation considerably.  The background thread merely waits on
# an Event to know when to run.  Results are communicated back using 
# a Future instance from the built-in concurrent.futures module. There
# are no queues or other structures involved.
#
# A tricky situation arises when task cancellations/timeouts occur.
# The apply() method used by curio tasks is able to abort and return
# control without computing a result.  However, the background thread
# will continue to run until its task is complete.  There is no way
# to kill a thread once started.  So, if this happens, the worker
# becomes unavailable--possibly forever (for example, if the worker
# permanently blocks or never finishes for some reason).   Perhaps, the
# best option here is to call shutdown() on the worker and to remove
# it from further service.  Although the background thread won't stop
# right away, this will make the thread terminate when it finally does
# complete its work.

class ThreadWorker(object):
    '''
    Worker that executes a callable on behalf of a curio task in a separate thread.
    '''
    def __init__(self):
        self.thread = None
        self.start_evt = None
        self.lock = None
        self.request = None

    def _launch(self):
        self.start_evt = threading.Event()
        self.thread = threading.Thread(target=self.run_worker, daemon=True)
        self.thread.start()

    def run_worker(self):
        while True:
            self.start_evt.wait()
            self.start_evt.clear()
            # If there is no pending request, but we were signalled to
            # start, it means terminate.
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
        future = _FutureLess()
        self.request = (func, args, kwargs, future)

        # Wait for the result to be computed
        await _future_wait(future, timeout, self.start_evt)
        return future.result()

# A ThreadPool is a collection of ThreadWorkers used to perform
# work on behalf of curio tasks.

class ThreadPool(object):
    def __init__(self, nworkers=None):
        if nworkers is None:
            nworkers = MAX_WORKER_THREADS

        self.nworkers = Semaphore(nworkers)
        self.workers = [ThreadWorker() for n in range(nworkers)]
        
    def shutdown(self):
        for worker in self.workers:
            worker.shutdown()
        self.workers = None

    async def apply(self, func, args=(), kwargs={}, timeout=None):
         async with self.nworkers:
             worker = self.workers.pop()
             try:
                 return await worker.apply(func, args, kwargs, timeout=timeout)
             except (CancelledError, TimeoutError) as e:
                 # If a worker is timed out or cancelled, there is no
                 # way to forcefully terminate the backing worker
                 # thread. It will run to completion as some kind of
                 # zombie.  However, we can remove the worker from the
                 # pool of available workers and instruct it to shut
                 # down when it completes.  Meanwhile, we'll replace
                 # it with a fresh worker.
                 worker.shutdown()
                 worker = ThreadWorker()
                 raise
             finally:
                 self.workers.append(worker)

class ProcessWorker(object):
    '''
    Managed process worker for running CPU-intensive tasks.  The main
    purpose of this class is to run workers with reliable
    cancellation/timeout semantics. Specifically, if a worker is
    cancelled, the underlying process is also killed.   This, as
    opposed to having it linger on running until work is complete.
    '''

    def __init__(self):
        self.process = None
        self.client_ch = None

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
            self.nrequests = 0

    def run_server(self, ch):
        while True:
            func, args, kwargs = ch.recv()
            try:
                result = func(*args, **kwargs)
                ch.send((True, result))
            except Exception as e:
                ch.send((False, e))
            func = args = kwargs = None
    
    async def apply(self, func, args=(), timeout=None):
        if self.process is None or not self.process.is_alive():
            self._launch()

        with self.client_ch.timeout(timeout):
            return await self.client_ch.rpc_client(func, args, {})

class ProcessPool(object):
    def __init__(self, nworkers=None):
        if nworkers is None:
            nworkers = multiprocessing.cpu_count()
        self.nworkers = Semaphore(nworkers)
        self.workers = [ProcessWorker() for n in range(nworkers)]

    async def apply(self, func, args=(), timeout=None):
         async with self.nworkers:
             worker = self.workers.pop()
             try:
                 return await worker.apply(func, args, timeout)
             except (CancelledError, TimeoutError, ChannelRPCError) as e:
                 worker.shutdown()
                 worker = ProcessWorker()
                 raise
             finally:
                 self.workers.append(worker)

    def shutdown(self):
        for worker in self.workers:
            worker.shutdown()
        self.workers = None


async def run_cpu_bound(callable, *args, timeout=None):
    kernel = await _get_kernel()
    if not kernel._process_pool:
        kernel._process_pool = ProcessPool()
    return await kernel._process_pool.apply(callable, args, timeout)

from .channel import Channel, ChannelRPCError
