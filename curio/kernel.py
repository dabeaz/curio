# curio/kernel.py
#
# Main execution kernel.

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
from abc import ABC, abstractmethod

# Logger where uncaught exceptions from crashed tasks are logged
log = logging.getLogger(__name__)

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

# KernelSyncBase is an abstract base class used to support synchronization
# primitives such as Events, Locks, Semaphores, etc.  There are different
# kinds of synchronization and policies that one might implement. This
# is merely specifying the expected kernel-side API.


class KernelSyncBase(ABC):

    @abstractmethod
    def __len__(self):
        pass

    @abstractmethod
    def add(self, task):
        '''
        Adds a new task.  This method *must* return a zero-argument
        callable that can be used to remove the just added task
        '''
        pass

    @abstractmethod
    def pop(self, ntasks=1):
        '''
        Pop one or more task.  Returns a list of the removed tasks.
        '''
        pass

# Kernel-level task synchronization primitives.  These are not
# for end-users.  They're used to implement higher-level primitives.
# See the curio/sync.py file.

# Kernel queue with soft-delete on task cancellation


class KSyncQueue(KernelSyncBase):

    def __init__(self):
        self._queue = deque()
        self._actual_len = 0

    def __len__(self):
        return self._actual_len

    def add(self, task):
        item = [task]
        self._queue.append(item)
        self._actual_len += 1

        def remove():
            item[0] = None
            self._actual_len -= 1
        return remove

    def pop(self, ntasks=1):
        tasks = []
        while ntasks > 0:
            task, = self._queue.popleft()
            if task:
                tasks.append(task)
                ntasks -= 1
        self._actual_len -= len(tasks)
        return tasks

# Kernel event with delete on cancellation


class KSyncEvent(KernelSyncBase):

    def __init__(self):
        self._tasks = set()

    def __len__(self):
        return len(self._tasks)

    def add(self, task):
        self._tasks.add(task)
        return lambda: self._tasks.remove(task)

    def pop(self, ntasks=1):
        return [self._tasks.pop() for _ in range(ntasks)]

# ----------------------------------------------------------------------
# Underlying kernel that drives everything
# ----------------------------------------------------------------------


class Kernel(object):

    def __init__(self, *, selector=None, with_monitor=False, log_errors=True,
                 warn_if_task_blocks_for=None):
        if selector is None:
            selector = DefaultSelector()

        self._selector = selector
        self._ready = deque()             # Tasks ready to run
        self._tasks = {}                 # Task table

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

        if self._monitor:
            self._monitor.close()

    # Main Kernel Loop
    # ----------
    def run(self, coro=None, *, shutdown=False):
        '''
        Run the kernel until no more non-daemonic tasks remain.  If
        shutdown is True, the kernel cleans up after itself after all
        tasks complete.
        '''

        assert self._selector is not None, 'Kernel has been shut down'

        # Motto:  "What happens in the kernel stays in the kernel"

        # ---- Kernel State
        current = None                          # Currently running task
        selector = self._selector               # Event selector
        ready = self._ready                     # Ready queue
        tasks = self._tasks                     # Task table
        sleeping = self._sleeping               # Sleeping task queue
        wake_queue = self._wake_queue           # External wake queue
        warn_if_task_blocks_for = self._warn_if_task_blocks_for

        # ---- Number of non-daemonic tasks running
        njobs = sum(not task.daemon for task in tasks.values())

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
        def _new_task(coro, daemon=False):
            nonlocal njobs
            task = Task(coro, daemon)
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
            nonlocal njobs
            task.next_value = value
            task.next_exc = exc
            task.timeout = None

            if not task.daemon:
                njobs -= 1

            if task.joining:
                for wtask in task.joining.pop(len(task.joining)):
                    _reschedule_task(wtask)
                task.joining = None
            task.terminated = True

            del tasks[task.id]

        # For "reasons" related to task scheduling, the task
        # of shutting down all remaining tasks is best managed
        # by a launching a task dedicated to carrying out the task (sic)
        async def _shutdown_tasks(tocancel):
            for task in tocancel:
                try:
                    await task.cancel()
                except Exception as e:
                    log.error('Exception %r ignored in curio shutdown' % e, exc_info=True)

        # Shut down the kernel. All remaining tasks are run through a cancellation
        # process so that they can cleanup properly.  After that, internal
        # resources are cleaned up.
        def _shutdown():
            nonlocal njobs
            while tasks:
                tocancel = [task for task in tasks.values() if task.id != self._kernel_task_id]

                # Cancel all non-daemonic tasks first
                tocancel.sort(key=lambda task: task.daemon)

                # Cancel the kernel loopback task last
                if self._kernel_task_id is not None:
                    tocancel.append(tasks[self._kernel_task_id])

                if tocancel:
                    _new_task(_shutdown_tasks(tocancel))
                    self.run()

                self._kernel_task_id = None

            # Cleanup other resources
            self._shutdown_resources()

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
        def _trap_spawn(coro, daemon):
            task = _new_task(coro, daemon)
            task.parentid = current.id
            _copy_tasklocal(current, task)
            return task

        # Reschedule one or more tasks from a kernel sync
        @nonblocking
        def _trap_ksync_reschedule_tasks(ksync, n):
            tasks = ksync.pop(n)
            for task in tasks:
                _reschedule_task(task)

        # Trap that returns a function for rescheduling tasks from synchronous code
        @nonblocking
        def _trap_ksync_reschedule_function(ksync):
            def _reschedule(n):
                tasks = ksync.pop(n)
                for task in tasks:
                    _reschedule_task(task)
            return _reschedule

        # Join with a task
        @blocking
        def _trap_join_task(task):
            if task.terminated:
                return _trap_sleep(0, False)
            else:
                if task.joining is None:
                    task.joining = KSyncQueue()
                return _trap_wait_ksync(task.joining, 'TASK_JOIN')

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

        # Wait on a queue
        @blocking
        def _trap_wait_ksync(ksync, state):
            return (state, ksync.add(current))

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
                _set_timeout(previous)
            else:
                current.timeout = previous

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

        # If a coroutine was given, add it as the first task
        maintask = _new_task(coro) if coro else None

        # If there's no main-task and shutdown requested, perform the shutdown
        if maintask is None and shutdown:
            _shutdown()
            return

        # ------------------------------------------------------------
        # Main Kernel Loop
        # ------------------------------------------------------------
        while njobs > 0:
            # Wait for an I/O event (or timeout)
            if ready:
                timeout = 0
            elif sleeping:
                timeout = sleeping[0][0] - time_monotonic()
            else:
                timeout = None
            events = selector_select(timeout)

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

        # If kernel shutdown has been requested, issue a cancellation request to all remaining tasks
        if shutdown:
            _shutdown()

        if maintask:
            if maintask.next_exc:
                raise maintask.next_exc
            else:
                return maintask.next_value
        else:
            return None


def run(coro, *, log_errors=True, with_monitor=False, selector=None,
        warn_if_task_blocks_for=None, **extra):
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
        result = kernel.run(coro)
    return result

__all__ = ['Kernel', 'run', 'BlockingTaskWarning']

from .monitor import Monitor
