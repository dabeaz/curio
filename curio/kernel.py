# curio/kernel.py
#
# Main execution kernel.  
#
# Curio is based on two overarching design principles that drive the code
# you'll find here. 
#
# 1. Environmental Isolation.  
#
#    Curio strictly separates the environment of async and synchronous
#    programming.  All asynchronous functionality is placed in
#    async-function definitions.  Async functions request the services
#    of the kernel using low-level yield statements (traps).  The
#    kernel is an opaque black-box from the perspective of synchronous
#    code.  There is only one available operation--run(coro) which
#    runs a new task.  There are no other mechanisms available for
#    controlling the kernel from synchronous code.  A good analogy
#    might be the distinction between user and protected mode in an
#    OS.  User programs run in user-mode and the operating system
#    kernel runs in protected mode.  The same thing happens here.
#    User programs in Curio can only run in async functions. Those
#    programs can request the services of the kernel.  However,
#    they're not granted any further access than that.
#    
# 2. Microkernels
#
#    The low-level kernel is meant to be small, fast, and minimally
#    featureful.  There are no publically exposed methods or
#    extension hooks (e.g., inheritance).  In fact, almost nothing
#    interesting happens here.  Instead, almost every useful part
#    of Curio gets implemented in async functions found elsewhere.
#    If you're trying to add new features to Curio, don't 
#    add them to the kernel. Think about how to create objects and
#    functions that operate at the async-function level instead.
#    See files such as sync.py or queue.py for examples.   
#
# No part of Curio has direct linkage to the Kernel class (it's
# not imported or used anywhere in the code base).   If you want,
# you can make a completely custom Kernel object and have the
# rest of Curio run on it.  You need to make sure you implement
# the required traps.


__all__ = ['Kernel', 'run' ]

# -- Standard Library

import socket
import heapq
import time
import os
import sys
import logging
from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, defaultdict
from contextlib import contextmanager
import threading

# Logger where uncaught exceptions from crashed tasks are logged
log = logging.getLogger(__name__)

# -- Curio

from .errors import *
from .task import Task
from .traps import _read_wait, Traps
from .local import LocalsActivation
from . import meta
from .debug import _create_debuggers

# ----------------------------------------------------------------------
# async-generator support.
#
# This context manager is used to manage the execution of async generators
# in Python 3.6.  In certain circumstances, they can't be used safely
# unless finalized properly.  This context manager installs some hooks
# for dealing with this in Curio.

@contextmanager
def _asyncgen_manager():
    if hasattr(sys, 'get_asyncgen_hooks'):
        old_asyncgen_hooks = sys.get_asyncgen_hooks()

        def _init_async_gen(agen):
            if not meta.is_safe_generator(agen) and not meta.finalize.is_finalized(agen):
                # Inspect the code of the generator to see if it might be safe 
                raise RuntimeError("Async generator with async finalization must be wrapped by\n"
                                   "async with curio.meta.finalize(agen) as agen:\n"
                                   "    async for n in agen:\n"
                                   "         ...\n"
                                   "See PEP 533 for further discussion.")

        sys.set_asyncgen_hooks(_init_async_gen)
    try:
        yield
    finally:
        if hasattr(sys, 'get_asyncgen_hooks'):
            sys.set_asyncgen_hooks(*old_asyncgen_hooks)


# ----------------------------------------------------------------------
# Underlying kernel that drives everything
# ----------------------------------------------------------------------


class Kernel(object):
    '''
    Curio run-time kernel.  selector argument to init specifies a
    different I/O selector.  debug argument specifies a list of
    debugger objects to apply. For example:

        from curio.debug import schedtrace, traptrace
        k = Kernel(debug=[schedtrace, traptrace])

    Use the kernel run() method to submit work.
    '''

    def __init__(self, *, selector=None, debug=None, activations=None):
        self._running = False

        # Functions to call at shutdown
        self._shutdown_funcs = []

        # I/O Selector setup
        self._selector = selector if selector else DefaultSelector()
        self._call_at_shutdown(self._selector.close)

        # Ready queue and task table
        self._ready = deque()
        self._tasks = {}                  

        # Coroutine runner and internal state
        self._runner = None
        self._crashed = False

        # Attributes related to the loopback socket (only initialized if required)
        self._notify_sock = None
        self._wait_sock = None
        self._kernel_task_id = None

        # Wake queue for tasks restarted by external threads
        self._wake_queue = deque()

        # Sleeping task queue
        self._sleeping = []

        # Activations
        self._activations = activations if activations else []
        self._activations.insert(0, LocalsActivation())
        
        # Debugging (activations in disguise)
        if debug:
            self._activations.extend(_create_debuggers(debug))

    def __del__(self):
        if self._shutdown_funcs is not None:
            raise RuntimeError(
                'Curio kernel not properly terminated.  Please use Kernel.run(shutdown=True)')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.run(shutdown=True)

    def _call_at_shutdown(self, func):
        self._shutdown_funcs.append(func)


    # ----------
    # Submit a new task to the kernel

    def run(self, corofunc=None, *args, shutdown=False, timeout=None):
        if self._running:
            raise RuntimeError('Curio kernel already running')

        if meta.curio_running():
            raise RuntimeError('Only one Curio kernel per thread is allowed')

        if corofunc and self._crashed:
            raise RuntimeError("Can't submit further tasks to a crashed kernel.")

        if corofunc:
            coro = meta.instantiate_coroutine(corofunc, *args)
        else:
            coro = None

        with _asyncgen_manager():
            meta.set_running_flag(True)
            self._running = True
            try:
                if not self._runner:
                    self._runner = self._run_coro()
                    self._runner.send(None)

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
                    raise

                # If shutdown has been requested, run the shutdown process
                if shutdown:
                    # For "reasons" related to task scheduling, the task
                    # of shutting down all remaining tasks is best managed
                    # by a launching a task dedicated to carrying out the task (sic)
                    async def _shutdown_tasks(tocancel):
                        for task in tocancel:
                            await task.cancel()

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

                    log.debug('Kernel %r shutting down', self)

                    # Call registered shutdown functions
                    for func in self._shutdown_funcs:
                        func()
                    self._shutdown_funcs = None

                if ret_exc:
                    raise TaskError('Task Crashed') from ret_exc
                else:
                    return ret_val

            finally:
                meta.set_running_flag(False)
                self._running = False

    # ------------------------------------------------------------
    # Main kernel runtime
    #
    # This is the main kernel execution environment.  To better support
    # pause/resume functionality, it is implemented as a coroutine.
    # The above run() method starts it and uses the send() method to
    # send in tasks to run.  By implementing it as a coroutine,
    # various set-up steps don't have to be repeated on each
    # invocation of run().
    #
    # At first glance, this function is going to look giant and
    # insane. It is implementing the kernel runtime as a self-contained
    # black box.  There is no external API.  The only possible 
    # communication is via traps defined in curio/traps.py.  
    # It's best to think of this as a "program within a program".  

    def _run_coro(kernel):

        # Motto:  "What happens in the kernel stays in the kernel"

        njobs = 0

        # ---- Kernel State
        current = None                          # Currently running task
        selector = kernel._selector             # Event selector
        ready = kernel._ready                   # Ready queue
        tasks = kernel._tasks                   # Task table
        sleeping = kernel._sleeping             # Sleeping task queue
        wake_queue = kernel._wake_queue         # External wake queue

        # ---- Bound methods
        selector_register = selector.register
        selector_unregister = selector.unregister
        selector_modify = selector.modify
        selector_select = selector.select
        selector_getkey = selector.get_key

        ready_popleft = ready.popleft
        ready_append = ready.append
        time_monotonic = time.monotonic

        # ------------------------------------------------------------
        # In-kernel task used for processing futures.
        #
        # Internal task that monitors the loopback socket--allowing the kernel to
        # awake for non-I/O events. 

        async def _kernel_task():
            wake_queue_popleft = wake_queue.popleft
            wait_sock = kernel._wait_sock

            while True:
                await _read_wait(wait_sock)
                data = wait_sock.recv(1000)

                # Process any waking tasks.  These are tasks that have
                # been awakened externally to the event loop (e.g., by
                # separate threads, Futures, etc.)
                while wake_queue:
                    task, future = wake_queue_popleft()
                    # If the future associated with wakeup no longer
                    # matches the future stored on the task, wakeup is
                    # abandoned.  It means that a timeout or
                    # cancellation event occurred in the time interval
                    # between the call to _wake() and the
                    # subsequent processing of the waking task
                    if future and task.future is not future:
                        continue
                    task.future = None
                    task.state = 'READY'
                    task.cancel_func = None
                    ready_append(task)

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
        def _wake(task=None, future=None):
            if task:
                wake_queue.append((task, future))
            kernel._notify_sock.send(b'\x00')

        def _init_loopback():
            kernel._notify_sock, kernel._wait_sock = socket.socketpair()
            kernel._wait_sock.setblocking(False)
            kernel._notify_sock.setblocking(False)
            kernel._call_at_shutdown(kernel._notify_sock.close)
            kernel._call_at_shutdown(kernel._wait_sock.close)

        # ------------------------------------------------------------
        # Task management functions.
        #

        # Create a new task. Putting it on the ready queue
        def _new_task(coro, daemon=False):
            nonlocal njobs
            task = Task(coro, daemon)
            tasks[task.id] = task
            if not daemon:
                njobs += 1
            _reschedule_task(task)
            return task

        # Reschedule a task, putting it back on the ready queue.
        def _reschedule_task(task, value=None, exc=None):
            ready_append(task)
            task.next_value = value
            task.next_exc = exc
            task.state = 'READY'
            task.cancel_func = None

        # Suspend the current task
        def _suspend_task(state, cancel_func):
            nonlocal current
            current.state = state
            current.cancel_func = cancel_func
            
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

            current = None

        # Check if task has pending cancellation
        def _check_cancellation():
            if current.allow_cancel and current.cancel_pending:
                current.next_exc = current.cancel_pending
                current.next_value = current.cancel_pending = None
                return True
            else:
                return False

        # finalize task.  Called after the task has run to completion
        def _finalize_task(task, value=None, exc=None):
            nonlocal njobs
            task.next_value = value
            task.next_exc = exc
            task.timeout = None

            if not task.daemon:
                njobs -= 1

            # Wake any joining tasks
            for wtask in task.joining.pop(len(task.joining)):
                _reschedule_task(wtask)

            task.terminated = True
            del tasks[task.id]

        # Set a timeout or sleep event on the current task
        def _set_timeout(clock, sleep_type='timeout'):
            item = (clock, current.id, sleep_type)
            heapq.heappush(sleeping, item)
            setattr(current, sleep_type, clock)

        # ------------------------------------------------------------
        # I/O Support functions
        #

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

        # ------------------------------------------------------------
        # Traps
        #
        # These implement the low-level functionality that is
        # triggered by user-level code.  They are never invoked directly
        # and there is no public API outside the kernel.  Instead,
        # coroutines use a statement such as
        #
        #   yield (_blocking_trap_io, sock, EVENT_READ, 'READ_WAIT')
        #
        # to invoke a specific trap.
        # ------------------------------------------------------------

        # ----------------------------------------
        # Wait for I/O
        def _trap_io(fileobj, event, state):
            if _check_cancellation():
                return

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
                    current.next_exc = e
                    current.next_value = None
                    return

            # This step indicates that we have managed any deferred I/O management
            # for the task.  Otherwise, I/O will be unregistered.
            current._last_io = None
            _suspend_task(state, lambda: _unregister_event(fileobj, event))

        # ----------------------------------------
        # Wait on a Future
        def _trap_future_wait(future, event):
            if _check_cancellation():
                return

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

            _suspend_task('FUTURE_WAIT',
                          lambda task=current:
                              setattr(task, 'future', future.cancel() and None))

        # ----------------------------------------
        # Add a new task to the kernel
        def _trap_spawn(coro, daemon):
            task = _new_task(coro, daemon | current.daemon)    # Inherits daemonic status from parent
            task.parentid = current.id
            current.next_value = task

        # ----------------------------------------
        # Cancel a task
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

        # ----------------------------------------
        # Wait on a scheduler primitive
        def _trap_sched_wait(sched, state):
            if _check_cancellation():
                return
            _suspend_task(state, sched.add(current))

        # ----------------------------------------
        # Reschedule one or more tasks from a scheduler primitive
        def _trap_sched_wake(sched, n):
            tasks = sched.pop(n)
            for task in tasks:
                _reschedule_task(task)

        # ----------------------------------------
        # Return the current value of the kernel clock
        def _trap_clock():
            current.next_value = time_monotonic()

        # ----------------------------------------
        # Sleep for a specified period. Returns value of monotonic clock.
        # absolute flag indicates whether or not an absolute or relative clock
        # interval has been provided
        def _trap_sleep(clock, absolute):
            if _check_cancellation():
                return

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
            _suspend_task('TIME_SLEEP', 
                          lambda task=current: setattr(task, 'sleep', None))

        # ----------------------------------------
        # Set a timeout to be delivered to the calling task
        def _trap_set_timeout(timeout):
            old_timeout = current.timeout
            if timeout is None:
                # If no timeout period is given, leave the current timeout in effect
                pass
            else:
                _set_timeout(timeout)
                if old_timeout and current.timeout > old_timeout:
                    current.timeout = old_timeout

            current.next_value = old_timeout

        # ----------------------------------------
        # Clear a previously set timeout
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

        # ----------------------------------------
        # Return the running kernel
        def _trap_get_kernel():
            current.next_value = kernel

        # ----------------------------------------
        # Return the currently running task
        def _trap_get_current():
            current.next_value = current

        # ------------------------------------------------------------
        # Final setup.
        # ------------------------------------------------------------

        # Create the traps tables
        kernel._traps = traps = [None] * len(Traps)
        for trap in Traps:
            traps[trap] = locals()[trap.name]

        # Initialize the loopback task (if not already initialized)
        if kernel._kernel_task_id is None:
            _init_loopback()
            kernel._kernel_task_id = _new_task(_kernel_task(), daemon=True).id

        # If there are tasks on the ready queue already, must cancel 
        # any prior pending I/O before re-entering the kernel loop
        for task in kernel._ready:
            if task._last_io:
                _unregister_event(*task._last_io)
                task._last_io = None

        # Initialize activations
        _activations = [ act() if (isinstance(act, type) and issubclass(act, ActivationBase)) else act
                         for act in kernel._activations ]
        kernel._activations = _activations

        for act in _activations:
            act.activate(kernel)

        # Main task (if any)
        main_task = None

        # ------------------------------------------------------------
        # TaskExecutor
        #
        # This context manager supervises the execution cycle of a single
        # task, allowing for monitoring, cleanup actions, and other things.
        # ------------------------------------------------------------

        class TaskExecutor:

            def __init__(self, task):
                self.task = task

            def __enter__(self):
                task = self.task
                for a in _activations:
                    a.running(task)

                task.state = 'RUNNING'
                task.cycles += 1
                return self

            def __exit__(self, ty, val, tb):
                task = self.task
                if task._last_io:
                    _unregister_event(*task._last_io)
                    task._last_io = None

                # If pending exceptions, task must be finalized
                if ty:
                    _finalize_task(task)
                    task.state = 'TERMINATED'

                for a in _activations:
                    a.suspended(task, val)

        # ------------------------------------------------------------
        # Main Kernel Loop
        # ------------------------------------------------------------
        while True:

            # ------------------------------------------------------------
            # Wait for work if nothing to run
            # ------------------------------------------------------------

            if njobs == 0:
                if main_task:
                    main_task._joined = True
                coro, poll_timeout = (yield (main_task.next_value, main_task.next_exc)) if main_task else (yield (None, None))
                main_task = _new_task(coro) if coro else None
                # If a task was created and a timeout was given, we impose a deadline on the task
                if main_task and poll_timeout:
                    current = main_task
                    _set_timeout(poll_timeout + time_monotonic())
                del coro

            # ------------------------------------------------------------
            # I/O Polling/Waiting
            # ------------------------------------------------------------

            if ready:
                timeout = 0
            elif sleeping:
                timeout = sleeping[0][0] - time_monotonic()
                if poll_timeout is not None and timeout > poll_timeout:
                    timeout = poll_timeout
            else:
                timeout = None if njobs else poll_timeout

            try:
                events = selector_select(timeout)
            except OSError as e:     # pragma: no cover
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


            # ------------------------------------------------------------
            # Time handling (sleep/timeouts
            # ------------------------------------------------------------

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

            # ------------------------------------------------------------
            # Run ready tasks
            # ------------------------------------------------------------

            for _ in range(len(ready)):
                current = ready_popleft()
                try:
                    with TaskExecutor(task=current) as executor:
                        # The current task runs traps until it suspends
                        while current:
                            if current.next_exc is None:
                                trap = current._send(current.next_value)
                                current.next_value = None
                            else:
                                trap = current._throw(current.next_exc)
                                current.next_exc = None

                            # Run the trap function. These never raise exceptions
                            # unless there's a fatal programming error in the kernel itself
                            try:
                                traps[trap[0]](*trap[1:])
                            except Exception as e:
                                raise KernelExit('Fatal Kernel Error') from e

                # Exception is raised during coroutine execution, the task
                # terminated. Set final return code and break out
                except StopIteration as e:
                    current.next_value = e.value

                except Exception as e:
                    current.next_exc = e

def run(corofunc, *args, with_monitor=False, selector=None,
        debug=None, activations=None, timeout=None, **extra):
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

    kernel = Kernel(selector=selector, debug=debug, activations=activations,
                    **extra)


    # Check if a monitor has been requested
    if with_monitor or 'CURIOMONITOR' in os.environ:   # pragma: no cover
        from .monitor import Monitor
        m = Monitor(kernel)
        kernel._call_at_shutdown(m.close)

    with kernel:
        return kernel.run(corofunc, *args, timeout=timeout)


from .monitor import Monitor

