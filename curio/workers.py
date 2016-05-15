# curio/workers.py
#
# Functions for performing work outside of curio.  This includes
# running functions in threads, processes, and executors from the
# concurrent.futures module.

__all__ = [ 'run_in_executor', 'run_in_thread', 'run_in_process' ]

import multiprocessing
import threading

from .errors import CancelledError
from .traps import _future_wait, _get_kernel
from . import sync
from .channel import Channel

async def run_in_executor(exc, callable, *args, **kwargs):
    '''
    Run callable(*args, **kwargs) in an executor such as
    ThreadPoolExecutor or ProcessPoolExecutor from the
    concurrent.futures module.  Be aware that on cancellation, any
    worker thread or process that was handling the request will
    continue to run to completion as a kind of zombie-- possibly
    rendering the executor unusable for subsequent work.

    This function is provided for compatibility with
    concurrent.futures, but is not the recommend approach for running
    blocking or cpu-bound work in curio. Use the run_in_thread() or
    run_in_process() methods instead.
    '''
    future = exc.submit(callable, *args, **kwargs)
    await _future_wait(future)
    return future.result()

MAX_WORKER_THREADS = 64

async def run_in_thread(callable, *args, **kwargs):
    '''
    Run callable(*args) in a separate thread and return the result.
    It's not possible to terminate threads so if a cancellation
    occurs, the associated worker thread will continue to run until
    completion as a kind of zombie.  When this happens, the cancelled
    worker will be immediately replaced by a new worker thread that's
    able to process further requests.  The cancelled worker thread
    will terminate when the callable completes its work (the result is
    discarded in that case).

    Note: It is advisable that all callables submitted to threads
    have a bound on their execution time (e.g., timeout or some
    other mechanism).
    '''
    kernel = await _get_kernel()
    if not kernel._thread_pool:
        kernel._thread_pool = WorkerPool(ThreadWorker, MAX_WORKER_THREADS)
    return await kernel._thread_pool.apply(callable, args, kwargs)

MAX_WORKER_PROCESSES = multiprocessing.cpu_count()

async def run_in_process(callable, *args, **kwargs):
    '''
    Run callable(*args, **kwargs) in a separate process and return the
    result.  In the event of cancellation, the worker process is
    immediately terminated.

    The worker process is created using multiprocessing.Process().
    Communication with the process uses multiprocessing.Pipe() and an
    asynchronous message passing channel.  All function arguments and
    return values are seralized using the pickle module.  When
    cancelled, the Process.terminate() method is used to kill the
    worker process.  This results in a SIGTERM signal being sent to
    the process.

    The worker process is a separate isolated Python interpreter.
    Nothing should be assumed about its global state including shared
    variables, files, or connections.
    '''
    kernel = await _get_kernel()
    if not kernel._process_pool:
        kernel._process_pool = WorkerPool(ProcessWorker,
                                          MAX_WORKER_PROCESSES)

    return await kernel._process_pool.apply(callable, args, kwargs)

# The _FutureLess class is a custom "Future" implementation solely for
# use by curio. It is used by the ThreadWorker class below and
# provides only the minimal set of functionality needed to transmit a
# result back to the curio kernel.  Unlike the normal Future class,
# this version doesn't require any thread synchronization or
# notification support.  By eliminating that, the overhead associated
# with the handoff between curio tasks and threads is substantially
# faster.
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
            raise self._exception from None

    def add_done_callback(self, func):
        self._callback = func

    def cancel(self):
        pass

# A ThreadWorker represents a thread that performs work on behalf of a
# curio task.   A curio task initiates work by executing the
# apply() method. This passes the request to a background thread that
# executes it.  While this takes place, the curio task blocks, waiting
# for a result to be set on an internal Future.

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
        if self.start_evt:
            self.start_evt.set()

    async def apply(self, func, args=(), kwargs={}):
        '''
        Run the callable func in a separate thread and return the result.
        '''
        if self.thread is None:
            self._launch()

        # Set up a request for the worker thread
        future = _FutureLess()
        self.request = (func, args, kwargs, future)

        # Wait for the result to be computed.  Important: The
        # start_evt passed as an argument is used to make the
        # worker thread start processing.
        await _future_wait(future, self.start_evt)
        return future.result()

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

    async def apply(self, func, args=(), kwargs={}):
        if self.process is None or not self.process.is_alive():
            self._launch()

        msg = (func, args, kwargs)
        await self.client_ch.send(msg)
        success, result = await self.client_ch.recv()
        if success:
            return result
        else:
            raise result

# Pool of workers for carrying out jobs on behalf of curio tasks.
#
# A tricky situation arises when task cancellations/timeouts occur.
# The apply() method used by curio tasks is able to abort and return
# control without computing a result.  However, the background worker
# might continue to run until its task is complete.  When this happens
# the shutdown() method is triggered on the worker and it is removed
# from further service--to be replaced by a fresh worker.  For process
# workers, this results in a process termination.  For threads, the
# thread will continue to run until it completes, at which point it
# will terminate.

class WorkerPool(object):
    def __init__(self, workercls, nworkers):
        self.nworkers = sync.Semaphore(nworkers)
        self.workercls = workercls
        self.workers = [workercls() for n in range(nworkers)]

    def shutdown(self):
        for worker in self.workers:
            worker.shutdown()
        self.workers = None

    async def apply(self, func, args=(), kwargs={}):
        async with self.nworkers:
            worker = self.workers.pop()
            try:
                return await worker.apply(func, args, kwargs)
            except CancelledError:
                # If a worker is timed out or cancelled, we shut it
                # down and replace it with a fresh worker.
                worker.shutdown()
                worker = self.workercls()
                raise
            finally:
                self.workers.append(worker)

# Pool definitions should anyone want to use them directly
ProcessPool = lambda nworkers: WorkerPool(ProcessWorker, nworkers)
ThreadPool = lambda nworkers: WorkerPool(ThreadWorker, nworkers)
