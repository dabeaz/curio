# curio/kernel.py
#
# Main execution kernel.

__all__ = ['Kernel', 'run', 'BlockingTaskWarning']

# -- Standard Library

import socket
import heapq
import time
import os
import sys
import logging
import signal
from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, defaultdict
import warnings
import threading
import inspect
from abc import ABC, abstractmethod

# Logger where uncaught exceptions from crashed tasks are logged
log = logging.getLogger(__name__)

# -- Curio

from .errors import *
from .task import Task
from .traps import _read_wait, Traps
from .local import _enable_tasklocal_for, _copy_tasklocal

# Decorators that indicate the trap type.
#
# A nonblocking trap is one that executes immediately and returns a
# result back to the caller.  A blocking trap is one that suspends the
# currently executing task and switches to another.

def nonblocking(trap_func):
    trap_func.blocking = False
    return trap_func


def blocking(trap_func):
    trap_func.blocking = True
    return trap_func


class BlockingTaskWarning(RuntimeWarning):
    pass

# Dictionary that tracks the "safe" status of async generators with 
# respect to asynchronous finalization.  Normally this is automatically
# determined by looking at the code of async generators.  It can
# be overridden using the @safe_generator decorator below. 

_safe_async_generators = { }      # { code_objects: bool }

def safe_generator(func):
    _safe_async_generators[func.__code__] = True
    return func
        
# ----------------------------------------------------------------------
# Underlying kernel that drives everything
# ----------------------------------------------------------------------


class Kernel(object):

    # Thread-local storage used to ensure one kernel per thread
    _local = threading.local()

    def __init__(self, *, selector=None, with_monitor=False, log_errors=True,
                 warn_if_task_blocks_for=None, with_asyncio_bridge=False, asyncio_loop=None):
        if selector is None:
            selector = DefaultSelector()

        self._selector = selector

        # Ready queue and task table
        self._ready = deque()
        self._tasks = {}                  

        # Coroutine runner and internal state
        self._runner = None
        self._crashed = False

        # Dict { signo: [ sigsets ] } of watched signals (initialized only if signals used)
        self._signal_sets = None
        self._default_signals = None      # Dict of default signal handlers

        # Attributes related to the loopback socket (only initialized if required)
        self._notify_sock = None
        self._wait_sock = None
        self._kernel_task_id = None

        # Wake queue for tasks restarted by external threads
        self._wake_queue = deque()

        # Sleeping task queue
        self._sleeping = []

        # Optional process/thread pools (see workers.py)
        self._thread_pool = None
        self._process_pool = None

        # Optional asyncio bridge
        self._asyncio_bridge = None
        self._asyncio_loop = None

        if with_asyncio_bridge:
            # Start the event loop in a separate thread.
            # This will be managed by the kernel `run` loop later on.
            import asyncio
            self._asyncio_loop = asyncio_loop or asyncio.new_event_loop()

            def _asyncio_thread(loop):
                def _suspended():
                    asyncio.set_event_loop(loop)
                    loop.run_forever()

                return _suspended

            self._asyncio_bridge = _asyncio_thread(self._asyncio_loop)

        # Optional settings
        self._warn_if_task_blocks_for = warn_if_task_blocks_for
        self._log_errors = log_errors
        self._monitor = None

        # If a monitor is specified, launch it
        if with_monitor or 'CURIOMONITOR' in os.environ:
            self._monitor = Monitor(self)

    def __del__(self):
        if self._selector is not None:
            raise RuntimeError(
                'Curio kernel not properly terminated.  Please use Kernel.run(shutdown=True)')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.run(shutdown=True)

    # Force the kernel to wake, possibly scheduling a task to run.
    # This method is called by threads running concurrently to the
    # curio kernel.  For example, it's triggered upon completion of
    # Futures created by thread pools and processes. It's inherently
    # dangerous for any kind of operation on the kernel to be
    # performed by a separate thread.  Thus, the *only* thing that
    # happens here is that the task gets appended to a deque and a
    # notification message is written to the kernel notification
    # socket.  append() and pop() operations on deques are thread safe
    # and do not need additional locking.  See
    # https://docs.python.org/3/library/collections.html#collections.deque
    # ----------
    def _wake(self, task=None, future=None):
        if self._selector:
            if task:
                self._wake_queue.append((task, future))
            self._notify_sock.send(b'\x00')

    def _init_loopback(self):
        self._notify_sock, self._wait_sock = socket.socketpair()
        self._wait_sock.setblocking(False)
        self._notify_sock.setblocking(False)
        return self._wait_sock.fileno()

    def _init_signals(self):
        self._signal_sets = defaultdict(list)
        self._default_signals = {}
        old_fd = signal.set_wakeup_fd(self._notify_sock.fileno())
        assert old_fd < 0, 'Signals already initialized %d' % old_fd

    def _signal_watch(self, sigset):
        for signo in sigset.signos:
            if not self._signal_sets[signo]:
                self._default_signals[signo] = signal.signal(signo, lambda signo, frame: None)
            self._signal_sets[signo].append(sigset)

    def _signal_unwatch(self, sigset):
        for signo in sigset.signos:
            if sigset in self._signal_sets[signo]:
                self._signal_sets[signo].remove(sigset)

            # If there are no active watchers for a signal, revert it back to default behavior
            if not self._signal_sets[signo]:
                signal.signal(signo, self._default_signals[signo])
                del self._signal_sets[signo]

    def _shutdown_resources(self):
        log.debug('Kernel %r shutting down', self)

        if self._selector:
            self._selector.close()
            self._selector = None

        if self._notify_sock:
            self._notify_sock.close()
            self._notify_sock = None
            self._wait_sock.close()
            self._wait_sock = None

        if self._signal_sets:
            signal.set_wakeup_fd(-1)
            self._signal_sets = None
            self._default_signals = None

        if self._thread_pool:
            self._thread_pool.shutdown()
            self._thread_pool = None

        if self._process_pool:
            self._process_pool.shutdown()
            self._process_pool = None

        if self._asyncio_loop:
            self._asyncio_loop.call_soon_threadsafe(self._asyncio_loop.stop)
            self._asyncio_loop = None

        if self._monitor:
            self._monitor.close()

    # Main Kernel Loop
    # ----------

    def run(self, corofunc=None, *args, shutdown=False, timeout=None):
        if inspect.iscoroutine(corofunc):
            coro = corofunc
        elif corofunc:
            if not meta.iscoroutinefunction(corofunc):
                raise TypeError('run() must be passed a coroutine or an async-function')
            coro = corofunc(*args)
        else:
            coro = None

        if coro and self._crashed:
            raise RuntimeError("Can't submit further tasks to a crashed kernel.")

        if getattr(self._local, 'running', False):
            raise RuntimeError('Only one Curio kernel per thread is allowed')
        self._local.running = True

        try:
            if not self._runner:
                if hasattr(sys, 'get_asyncgen_hooks'):
                    self._asyncgen_hooks = sys.get_asyncgen_hooks()
                self._runner = self._run_coro()
                self._runner.send(None)

            # Boot the asyncio worker thread, if applicable.
            if self._asyncio_loop and not self._asyncio_loop.is_running():
                self._local.asyncio_thread = threading.Thread(target=self._asyncio_bridge)
                self._local.asyncio_thread.start()

            # Submit the given coroutine (if any)
            try:
                if coro or not shutdown:
                    ret_val, ret_exc = self._runner.send((coro, timeout))
                else:
                    ret_val = ret_exc = None
            except BaseException as e:
                # If the underlying runner coroutine died for some reason,
                # then something bad happened.  Maybe a KeyboardInterrupt
                # an internal programming program.  We'll remove it and
                # mark the kernel as crashed.   It's still possible that someone
                # will attempt a kernel shutdown later.
                self._runner = None
                self._crashed = True
                if hasattr(sys, 'get_asyncgen_hooks'):
                    sys.set_asyncgen_hooks(*self._asyncgen_hooks)
                    self._asyncgen_hooks = None
                raise

            # If shutdown has been requested, run the shutdown process
            if shutdown:
                # For "reasons" related to task scheduling, the task
                # of shutting down all remaining tasks is best managed
                # by a launching a task dedicated to carrying out the task (sic)
                async def _shutdown_tasks(tocancel):
                    for task in tocancel:
                        try:
                            await task.cancel()
                        except Exception as e:
                            log.error('Exception %r ignored in curio shutdown' % e, exc_info=True)

                while self._tasks:
                    tocancel = [task for task in self._tasks.values()
                                if task.id != self._kernel_task_id]
                    tocancel.sort(key=lambda t: t.id)
                    if self._kernel_task_id:
                        tocancel.append(self._tasks[self._kernel_task_id])
                    for task in tocancel:
                        task.daemon = True
                    self._runner.send((_shutdown_tasks(tocancel), None))
                    self._kernel_task_id = None
                self._runner.close()
                del self._runner
                self._shutdown_resources()
                if hasattr(sys, 'set_asyncgen_hooks'):
                    sys.set_asyncgen_hooks(*self._asyncgen_hooks)

            if ret_exc:
                raise ret_exc
            else:
                return ret_val

        finally:
            self._local.running = False

    # Discussion:  This is the main kernel execution loop.   To better
    # support pause/resume functionality, it is also implemented as
    # a coroutine.  The above run_coro() method starts it and uses
    # the send() method to send in tasks to run.   By implementing it
    # as a coroutine, various set-up steps don't have to be repeated
    # on each invocation of run_coro().
    def _run_coro(self):
        '''
        Run the kernel
        '''
        assert self._selector is not None, 'Kernel has been shut down'

        njobs = 0

        # Motto:  "What happens in the kernel stays in the kernel"

        # ---- Kernel State
        current = None                          # Currently running task
        selector = self._selector               # Event selector
        ready = self._ready                     # Ready queue
        tasks = self._tasks                     # Task table
        sleeping = self._sleeping               # Sleeping task queue
        wake_queue = self._wake_queue           # External wake queue
        warn_if_task_blocks_for = self._warn_if_task_blocks_for

        # ---- Bound methods
        selector_register = selector.register
        selector_unregister = selector.unregister
        selector_modify = selector.modify
        selector_select = selector.select
        selector_getkey = selector.get_key

        ready_popleft = ready.popleft
        ready_append = ready.append
        time_monotonic = time.monotonic
        _wake = self._wake

        # ---- In-kernel task used for processing signals and futures

        # Initialize the loopback socket and launch the kernel task if needed
        def _init_loopback_task():
            self._init_loopback()
            task = Task(_kernel_task(), taskid=0, daemon=True)
            _reschedule_task(task)
            self._kernel_task_id = task.id
            self._tasks[task.id] = task

        # Internal task that monitors the loopback socket--allowing the kernel to
        # awake for non-I/O events.  Also processes incoming signals.  This only
        # launches if needed to wait for external events (futures, signals, etc.)
        async def _kernel_task():
            wake_queue_popleft = wake_queue.popleft
            wait_sock = self._wait_sock

            while True:
                await _read_wait(wait_sock)
                data = wait_sock.recv(1000)

                # Process any waking tasks.  These are tasks that have been awakened
                # externally to the event loop (e.g., by separate threads, Futures, etc.)
                while wake_queue:
                    task, future = wake_queue_popleft()
                    # If the future associated with wakeup no longer matches
                    # the future stored on the task, wakeup is abandoned.
                    # It means that a timeout or cancellation event occurred
                    # in the time interval between the call to self._wake()
                    # and the subsequent processing of the waking task
                    if future and task.future is not future:
                        continue
                    task.future = None
                    task.state = 'READY'
                    task.cancel_func = None
                    ready_append(task)

                # Any non-null bytes received here are assumed to be received signals.
                # See if there are any pending signal sets and unblock if needed
                if not self._signal_sets:
                    continue

                sigs = (n for n in data if n in self._signal_sets)
                for signo in sigs:
                    for sigset in self._signal_sets[signo]:
                        sigset.pending.append(signo)
                        if sigset.waiting:
                            _reschedule_task(sigset.waiting, value=signo)
                            sigset.waiting = None

        # ---- Task Support Functions

        # Create a new task. Putting it on the ready queue
        def _new_task(coro, daemon=False, taskid=None):
            nonlocal njobs
            task = Task(coro, daemon, taskid=taskid)
            tasks[task.id] = task
            if not daemon:
                njobs += 1
            _reschedule_task(task)
            return task

        # Reschedule a task, putting it back on the ready queue so that it can run.
        # value and exc specify a value or exception to send into the underlying
        # coroutine when it is rescheduled.
        def _reschedule_task(task, value=None, exc=None):
            ready_append(task)
            task.next_value = value
            task.next_exc = exc
            task.state = 'READY'
            task.cancel_func = None
            
        # Cleanup task.  This is called after the underlying coroutine has
        # terminated.  value and exc give the return value or exception of
        # the coroutine.  This wakes any tasks waiting to join.
        def _cleanup_task(task, value=None, exc=None):
            nonlocal main_task, main_value, main_exc, njobs
            task.next_value = value
            task.next_exc = exc
            task.timeout = None

            if not task.daemon:
                njobs -= 1

            if task.joining:
                for wtask in task.joining.pop(len(task.joining)):
                    _reschedule_task(wtask)
            task.terminated = True

            del tasks[task.id]

            # If the task just cleaned up was the main task, we set
            # its return values.  This will cause the kernel loop to yield
            if task == main_task:
                main_value = value
                main_exc = exc
                main_task = None

        # Set a timeout or sleep event on the current task
        def _set_timeout(clock, sleep_type='timeout'):
            item = (clock, current.id, sleep_type)
            heapq.heappush(sleeping, item)
            setattr(current, sleep_type, clock)

        # ---- I/O Support functions

        def _register_event(fileobj, event, task):
            try:
                key = selector_getkey(fileobj)
                mask, (rtask, wtask) = key.events, key.data
                if event == EVENT_READ and rtask:
                    raise CurioError("Multiple tasks can't wait to read on the same file descriptor %r" % fileobj)
                if event == EVENT_WRITE and wtask:
                    raise CurioError("Multiple tasks can't wait to write on the same file descriptor %r" % fileobj)
                selector_modify(fileobj, mask | event,
                                (task, wtask) if event == EVENT_READ else (rtask, task))
            except KeyError:
                selector_register(fileobj, event,
                                  (task, None) if event == EVENT_READ else (None, task))

        def _unregister_event(fileobj, event):
            key = selector_getkey(fileobj)
            mask, (rtask, wtask) = key.events, key.data
            mask &= ~event
            if not mask:
                selector_unregister(fileobj)
            else:
                selector_modify(fileobj, mask,
                                (None, wtask) if event == EVENT_READ else (rtask, None))

        # ---- Traps
        #
        # These implement the low-level functionality that is
        # triggered by coroutines.  They are never invoked directly
        # and there is no public API outside the kernel.  Instead,
        # coroutines use a statement such as
        #
        #   yield (_blocking_trap_io, sock, EVENT_READ, 'READ_WAIT')
        #
        # to invoke a specific trap.
        #
        # There are two calling conventions we use for implementing these:
        #
        # 1) Blocking trap handlers return the new values for
        #
        #       (task.state, task.cancel_func)
        #
        #    They don't have any way to pass values/exceptions back to the
        #    invoker.
        #
        # 2) Nonblocking trap handlers act like regular function calls -- whatever
        #    they return or raise will be passed back to the invoker.

        # Wait for I/O

        @blocking
        def _trap_io(fileobj, event, state):
            # See comment about deferred unregister in run().  If the requested
            # I/O operation is *different* than the last I/O operation that was
            # performed by the task, we need to unregister the last I/O resource used
            # and register a new one with the selector.
            if current._last_io != (fileobj, event):
                if current._last_io:
                    _unregister_event(*current._last_io)
                try:
                    _register_event(fileobj, event, current)
                except CurioError as e:
                    _reschedule_task(current, exc=e)
                    return (current.state, None)

            # This step indicates that we have managed any deferred I/O management
            # for the task.  Otherwise the run() method will perform an unregistration step.
            current._last_io = None
            return (state, lambda: _unregister_event(fileobj, event))

        # Wait on a Future
        @blocking
        def _trap_future_wait(future, event):
            if self._kernel_task_id is None:
                _init_loopback_task()

            current.future = future

            # Discussion: Each task records the future that it is
            # currently waiting on.  The completion callback below only
            # attempts to wake the task if its stored Future is exactly
            # the same one that was stored above.  Due to support for
            # cancellation and timeouts, it's possible that a task might
            # abandon its attempt to wait for a Future and go on to
            # perform other operations, including waiting for different
            # Future in the future (got it?).  However, a running thread
            # or process still might go on to eventually complete the
            # earlier work.  In that case, it will trigger the callback,
            # find that the task's current Future is now different, and
            # discard the result.

            future.add_done_callback(lambda fut, task=current: _wake(task, fut))

            # An optional threading.Event object can be passed and set to
            # start a worker thread.   This makes it possible to have a lock-free
            # Future implementation where worker threads only start after the
            # callback function has been set above.
            if event:
                event.set()

            return ('FUTURE_WAIT',
                    lambda task=current:
                        setattr(task, 'future', future.cancel() and None))

        # Add a new task to the kernel
        @nonblocking
        def _trap_spawn(coro, daemon, task_id):
            task = _new_task(coro, daemon | current.daemon, task_id)    # Inherits daemonic status from parent
            task.parentid = current.id
            _copy_tasklocal(current, task)
            return task

        # Reschedule one or more tasks from a kernel sync
        @nonblocking
        def _trap_sched_wake(sched, n):
            tasks = sched.pop(n)
            for task in tasks:
                _reschedule_task(task)

        # Join with a task
        @blocking
        def _trap_join_task(task):
            if task.terminated:
                return _trap_sleep(0, False)
            else:
                return _trap_sched_wait(task.joining, 'TASK_JOIN')

        # Cancel a task
        @nonblocking
        def _trap_cancel_task(task, exc=TaskCancelled, val=None):
            if task.cancelled:
                return

            task.cancelled = True

            # Cancelling a task also cancels any currently pending timeout.
            # If a task is being cancelled, the delivery of a timeout is
            # somewhat immaterial--the task is already being cancelled.
            task.timeout = None

            # Set the cancellation exception
            task.cancel_pending = exc(exc.__name__ if val is None else val)

            # If the task doesn't allow the delivery of a cancellation exception right now
            # we're done.  It's up to the task to check for it later
            if not task.allow_cancel:
                return

            # If the task doesn't have a cancellation function set, it means the task
            # is on the ready-queue.  It's not safe to deliver a cancellation exception
            # to it right now.  Instead, we simply return.  It will get cancelled
            # the next time it performs a blocking operation
            if not task.cancel_func:
                return

            # Cancel and reschedule the task
            task.cancel_func()
            _reschedule_task(task, exc=task.cancel_pending)
            task.cancel_pending = None

        # Wait on a scheduler primitive
        @blocking
        def _trap_sched_wait(sched, state):
            return (state, sched.add(current))

        # Sleep for a specified period. Returns value of monotonic clock.
        # absolute flag indicates whether or not an absolute or relative clock
        # interval has been provided
        @blocking
        def _trap_sleep(clock, absolute):
            # We used to have a special case where sleep periods <= 0 would
            # simply reschedule the task to the end of the ready queue without
            # actually putting it on the sleep queue first. But this meant
            # that if a task looped while calling sleep(0), it would allow
            # other *ready* tasks to run, but block ever checking for I/O or
            # timeouts, so sleeping tasks would never wake up. That's not what
            # we want; sleep(0) should mean "please give other stuff a chance
            # to run". So now we always go through the whole sleep machinery.
            if not absolute:
                clock += time_monotonic()
            _set_timeout(clock, 'sleep')
            return ('TIME_SLEEP',
                    lambda task=current: setattr(task, 'sleep', None))

        # Watch signals
        @nonblocking
        def _trap_sigwatch(sigset):
            # Initialize the signal handling part of the kernel if not done already
            # Note: This only works if running in the main thread
            if self._kernel_task_id is None:
                _init_loopback_task()

            if self._signal_sets is None:
                self._init_signals()

            self._signal_watch(sigset)

        # Unwatch signals
        @nonblocking
        def _trap_sigunwatch(sigset):
            self._signal_unwatch(sigset)

        # Wait for a signal
        @blocking
        def _trap_sigwait(sigset):
            sigset.waiting = current
            return ('SIGNAL_WAIT', lambda: setattr(sigset, 'waiting', None))

        # Set a timeout to be delivered to the calling task
        @nonblocking
        def _trap_set_timeout(timeout):
            old_timeout = current.timeout
            if timeout is None:
                # If no timeout period is given, leave the current timeout in effect
                pass
            else:
                _set_timeout(timeout)
                if old_timeout and current.timeout > old_timeout:
                    current.timeout = old_timeout

            return old_timeout

        # Clear a previously set timeout
        @nonblocking
        def _trap_unset_timeout(previous):
            # Here's an evil corner case.  Suppose the previous timeout in effect
            # has already expired?  If so, then we need to arrange for a timeout
            # to be generated.  However, this has to happen on the *next* blocking
            # call, not on this trap.  That's because the "unset" timeout feature
            # is usually done in the finalization stage of the previous timeout
            # handling.  If we were to raise a TaskTimeout here, it would get mixed
            # up with the prior timeout handling and all manner of head-explosion
            # will occur.

            now = time_monotonic()
            if previous and previous >= 0 and previous < now:
                # Perhaps create a TaskTimeout pending exception here.
                _set_timeout(previous)
            else:
                current.timeout = previous
                # But there's one other evil corner case.  It's possible that
                # a timeout could be reset while a TaskTimeout exception
                # is pending.  If that happens, it means that the task has
                # left the timeout block.   We should probably take away the
                # pending exception.
                if isinstance(current.cancel_pending, TaskTimeout):
                    current.cancel_pending = None

        # Return the running kernel
        @nonblocking
        def _trap_get_kernel():
            return self

        # Return the currently running task
        @nonblocking
        def _trap_get_current():
            return current

        # Return the current value of the kernel clock
        @nonblocking
        def _trap_clock():
            return time_monotonic()

        # Create the traps tables
        traps = [None] * len(Traps)
        for trap in Traps:
            traps[trap] = locals()[trap.name]

        # Initialize the loopback task (if not already initialized)
        if self._kernel_task_id is None:
            _init_loopback_task()

        # If there are tasks on the ready queue already, must cancel 
        # any prior pending I/O before re-entering the kernel loop
        for task in self._ready:
            if task._last_io:
                _unregister_event(*task._last_io)
                task._last_io = None

        # Return values for the send() method
        main_value = None
        main_exc = None
        main_task = None

        # Some support for async-generators
        def _init_async_gen(agen):
            from . import meta

            if agen.ag_code not in _safe_async_generators:
                _safe_async_generators[agen.ag_code] = meta._is_safe_generator(agen.ag_code)

            if not _safe_async_generators[agen.ag_code] and not agen in meta.finalize._finalized:
                # Inspect the code of the generator to see if it might be safe 
                raise RuntimeError("Async generator with async finalization must be wrapped by\n"
                                   "async with curio.meta.finalize(agen) as agen:\n"
                                   "    async for n in agen:\n"
                                   "         ...\n"
                                   "See PEP 533 for further discussion.")

        if hasattr(sys, 'set_asyncgen_hooks'):
            sys.set_asyncgen_hooks(_init_async_gen)
            
        # ------------------------------------------------------------
        # Main Kernel Loop
        # ------------------------------------------------------------
        while True:
            # If no main task is known, we yield in order to receive it
            if njobs == 0:
                coro, poll_timeout = yield (main_value, main_exc)
                main_value = main_exc = None
                main_task = _new_task(coro) if coro else None
                # If a task was created and a timeout was given, we impose a deadline on the task
                if main_task and poll_timeout:
                    current = main_task
                    _set_timeout(poll_timeout + time_monotonic())
                del coro

            # Wait for an I/O event (or timeout)
            if ready:
                timeout = 0
            elif sleeping:
                timeout = sleeping[0][0] - time_monotonic()
                if poll_timeout is not None and timeout > poll_timeout:
                    timeout = poll_timeout
            else:
                if njobs == 0:
                    timeout = poll_timeout
                else:
                    timeout = None

            try:
                events = selector_select(timeout)
            except OSError as e:
                # If there is nothing to select, windows throws an
                # OSError, so just set events to an empty list.
                log.error('Exception %r from selector_select ignored ' % e,
                          exc_info=True)
                events = []

            # Reschedule tasks with completed I/O
            for key, mask in events:
                rtask, wtask = key.data
                intfd = isinstance(key.fileobj, int)
                if mask & EVENT_READ:
                    # Discussion: If the associated fileobj is
                    # *not* a bare integer file descriptor, we
                    # keep a record of the last I/O event in
                    # _last_io and leave the task registered on
                    # the event loop.  If it performs the same I/O
                    # operation again, it will get a speed boost
                    # from not having to re-register its
                    # event. However, it's not safe to use this
                    # optimization with bare integer fds.  These
                    # fds often get reused and there is a
                    # possibility that a fd will get closed and
                    # reopened on a different resource without it
                    # being detected by the kernel.  For that case,
                    # its critical that we not leave the fd on the
                    # event loop.
                    rtask._last_io = None if intfd else (key.fileobj, EVENT_READ)
                    _reschedule_task(rtask)
                    mask &= ~EVENT_READ
                    rtask = None
                if mask & EVENT_WRITE:
                    wtask._last_io = None if intfd else (key.fileobj, EVENT_WRITE)
                    _reschedule_task(wtask)
                    mask &= ~EVENT_WRITE
                    wtask = None

                # Unregister the task if fileobj is not an integer fd (see
                # note above).
                if intfd:
                    if mask:
                        selector_modify(key.fileobj, mask, (rtask, wtask))
                    else:
                        selector_unregister(key.fileobj)

            # Process sleeping tasks (if any)
            if sleeping:
                current_time = time_monotonic()
                while sleeping and sleeping[0][0] <= current_time:
                    tm, taskid, sleep_type = heapq.heappop(sleeping)
                    # When a task wakes, verify that the timeout value matches that stored
                    # on the task. If it differs, it means that the task completed its
                    # operation, was cancelled, or is no longer concerned with this
                    # sleep operation.  In that case, we do nothing
                    if taskid in tasks:
                        task = tasks[taskid]
                        if sleep_type == 'sleep':
                            if tm == task.sleep:
                                task.sleep = None
                                _reschedule_task(task, value=current_time)
                        else:
                            if tm == task.timeout:
                                task.timeout = None
                                # If cancellation is allowed and the task is blocked, reschedule it
                                if task.allow_cancel and task.cancel_func:
                                    task.cancel_func()
                                    _reschedule_task(task, exc=TaskTimeout(current_time))
                                else:
                                    # Task is on the ready queue or can't be cancelled right now,
                                    # mark it as pending cancellation
                                    task.cancel_pending = TaskTimeout(current_time)

            # --------
            # Run ready tasks
            # --------
            # We only run the tasks that were already in the queue when we
            # started the loop. Any new tasks that are rescheduled onto the
            # ready queue while we're going will have to wait until the next
            # iteration of the outer loop, after we've checked for I/O and
            # sleepers. This avoids various potential pathologies that could
            # otherwise occur where tasks repeatedly reschedule themselves so
            # the queue never empties and we end up never checking for I/O.
            for _ in range(len(ready)):
                current = ready_popleft()
                try:
                    if warn_if_task_blocks_for:
                        task_start = time_monotonic()
                    current.state = 'RUNNING'
                    current.cycles += 1
                    with _enable_tasklocal_for(current):
                        if current.next_exc is None:
                            trap = current._send(current.next_value)
                            current.next_value = None
                        else:
                            trap = current._throw(current.next_exc)
                            current.next_exc = None

                        # If the trap is nonblocking, then handle it
                        # immediately without
                        # rescheduling. Nonblocking trap handlers have
                        # a different API than blocking trap handlers
                        # -- they just return or raise whatever the
                        # trap should return or raise.
                        trapfunc = traps[trap[0]]
                        while not trapfunc.blocking:
                            try:
                                next_value = trapfunc(*trap[1:])
                            except Exception as next_exc:
                                trap = current._throw(next_exc)
                            else:
                                trap = current._send(next_value)
                            trapfunc = traps[trap[0]]

                        # Execute a blocking trap
                        assert trapfunc.blocking

                        # If there is a cancellation pending and delivery is allowed,
                        # reschedule the task with the pending exception
                        if current.allow_cancel and current.cancel_pending:
                            _reschedule_task(current, exc=current.cancel_pending)
                            current.cancel_pending = None
                        else:
                            current.state, current.cancel_func = trapfunc(*trap[1:])

                except StopIteration as e:
                    if current.cancel_pending:
                        _cleanup_task(current, exc=current.cancel_pending)
                        current.state = 'CANCELLED'
                    else:
                        _cleanup_task(current, value=e.value)
                        current.state = 'TERMINATED'

                except (CancelledError, TaskExit) as e:
                    current.exc_info = sys.exc_info()
                    current.state = 'CANCELLED'
                    _cleanup_task(current, exc=e)

                except Exception as e:
                    current.exc_info = sys.exc_info()
                    current.state = 'CRASHED'
                    exc = TaskError('Task Crashed')
                    exc.__cause__ = e
                    _cleanup_task(current, exc=exc)
                    if self._log_errors:
                        log.error('Curio: Task Crash: %s' % current, exc_info=True)

                except:  # (SystemExit, KeyboardInterrupt):
                    _cleanup_task(current)
                    current.state = 'TERMINATED'
                    raise

                finally:
                    if warn_if_task_blocks_for:
                        duration = time_monotonic() - task_start
                        if duration > warn_if_task_blocks_for:
                            msg = ("Event loop blocked for {:0.1f} ms "
                                   "inside '{}' (task {})"
                                   .format(1000 * duration,
                                           current.coro.__qualname__,
                                           current.id))
                            warnings.warn(BlockingTaskWarning(msg))

                    # Unregister previous I/O request. Discussion follows:
                    #
                    # When a task performs I/O, it registers itself with the underlying
                    # I/O selector.  When the task is reawakened, it unregisters itself
                    # and prepares to run.  However, in many network applications, the
                    # task will perform a small amount of work and then go to sleep on
                    # exactly the same I/O resource that it was waiting on before. For
                    # example, a client handling task in a server will often spend most
                    # of its time waiting for incoming data on a single socket.
                    #
                    # Instead of always unregistering the task from the selector, we
                    # can defer the unregistration process until after the task goes
                    # back to sleep again.  If it happens to be sleeping on the same
                    # resource as before, there's no need to unregister it--it will
                    # still be registered from the last I/O operation.
                    #
                    # The code here performs the unregister step for a task that
                    # ran, but is now sleeping for a *different* reason than repeating the
                    # prior I/O operation.  There is coordination with code in _trap_io().

                    if current._last_io:
                        _unregister_event(*current._last_io)
                        current._last_io = None


def run(corofunc, *args, log_errors=True, with_monitor=False, selector=None,
        warn_if_task_blocks_for=None, timeout=None, **extra):
    '''
    Run the curio kernel with an initial task and execute until all
    tasks terminate.  Returns the task's final result (if any). This
    is a convenience function that should primarily be used for
    launching the top-level task of an curio-based application.  It
    creates an entirely new kernel, runs the given task to completion,
    and concludes by shutting down the kernel, releasing all resources used.

    Don't use this function if you're repeatedly launching a lot of
    new tasks to run in curio. Instead, create a Kernel instance and
    use its run() method instead.
    '''

    kernel = Kernel(selector=selector, with_monitor=with_monitor,
                    log_errors=log_errors,
                    warn_if_task_blocks_for=warn_if_task_blocks_for,
                    **extra)

    with kernel:
        return kernel.run(corofunc, *args, timeout=timeout)




from .monitor import Monitor
from . import meta
