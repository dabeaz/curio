# kernel.py
# 
# Copyright (C) 2015-2016
# David Beazley (Dabeaz LLC), http://www.dabeaz.com
# All rights reserved.
#
# This is the core of curio.   Definitions for tasks, signal sets, and the kernel
# are here.

import socket
import heapq
import time
import os
import sys
import logging
import signal

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE
from collections import deque, defaultdict
from types import coroutine
from contextlib import contextmanager

# Logger where uncaught exceptions from crashed tasks are logged
log = logging.getLogger(__name__)

# kqueue is the datatype used by the kernel for all of its queuing functionality.
# Any time a task queue is needed, use this type instead of directly hard-coding the
# use of a deque.  This will make sure the code continues to work even if the
# queue type is changed later.

kqueue = deque

# --- Curio specific exceptions

class CurioError(Exception):
    pass

class CancelledError(CurioError):
    pass

class TaskTimeout(CurioError):
    pass

class TaskError(CurioError):
    pass

class _CancelRetry(Exception):
    pass

# Task class wraps a coroutine, but provides other information about 
# the task itself for the purposes of debugging, scheduling, timeouts, etc.

class Task(object):
    __slots__ = ('id', 'daemon',  'coro', 'send', 'throw', 'cycles', 'state',
                 'cancel_func', 'future', 'sleep', 'timeout', 'exc_info', 'next_value',
                 'next_exc', 'joining', 'terminated', '_last_io', '__weakref__',
                 )
    _lastid = 1
    def __init__(self, coro, daemon=False):
        self.id = Task._lastid   
        Task._lastid += 1
        self.coro = coro          # Underlying generator/coroutine
        self.send = coro.send     # Bound coroutine methods
        self.throw = coro.throw
        self.daemon = daemon      # Daemonic flag
        self.cycles = 0           # Execution cycles completed
        self.state = 'INITIAL'    # Execution state
        self.cancel_func = None   # Cancellation function
        self.future = None        # Pending Future (if any)
        self.sleep = None         # Pending sleep (if any)
        self.timeout = None       # Pending timeout (if any)
        self.exc_info = None      # Exception info (if any on crash)
        self.next_value = None    # Next value to send on execution
        self.next_exc = None      # Next exception to send on execution
        self.joining = None       # Optional set of tasks waiting to join with this one
        self.terminated = False   # Terminated?
        self._last_io = None      # Last I/O operation performed

    def __repr__(self):
        return 'Task(id=%r, %r, state=%r)' % (self.id, self.coro, self.state)

    def __str__(self):
        return self.coro.__qualname__

    def __del__(self):
        self.coro.close()

    async def join(self):
        '''
        Waits for a task to terminate.  Returns the return value (if any)
        or raises a TaskError if the task crashed with an exception.
        '''
        await _join_task(self)
        if self.exc_info:
            raise TaskError('Task crash') from self.exc_info[1]
        else:
            return self.next_value

    async def cancel(self, *, exc=CancelledError):
        '''
        Cancels a task.  Does not return until the task actually terminates.
        Returns True if the task was actually cancelled. False is returned
        if the task was already completed.
        '''
        if self.terminated:
            return False
        else:
            await _cancel_task(self, exc)
            return True

# The SignalSet class represents a set of Unix signals being monitored. 
class SignalSet(object):
    def __init__(self, *signos):
        self.signos = signos             # List of all signal numbers being tracked
        self.pending = deque()           # Pending signals received
        self.waiting = None              # Task waiting for the signals (if any)
        self.watching = False            # Are the signals being watched right now?
    
    async def __aenter__(self):
        assert not self.watching
        await _sigwatch(self)
        self.watching = True
        return self

    async def __aexit__(self, *args):
        await _sigunwatch(self)
        self.watching = False

    async def wait(self):
        '''
        Wait for a single signal from the signal set to arrive.
        '''
        if not self.watching:
            async with self:
                return await self.wait()

        while True:
            if self.pending:
                return self.pending.popleft()
            await _sigwait(self)

    @contextmanager
    def ignore(self):
        '''
        Context manager. Temporarily ignores all signals in the signal set. 
        '''
        try:
            orig_signals = [ (signo, signal.signal(signo, signal.SIG_IGN)) for signo in self.signos ]
            yield
        finally:
            for signo, handler in orig_signals:
                signal.signal(signo, handler)

# ----------------------------------------------------------------------
# Underlying kernel that drives everything
# ----------------------------------------------------------------------

class Kernel(object):
    def __init__(self, *, selector=None, with_monitor=False):
        if selector is None:
            selector = DefaultSelector()
        self._selector = selector
        self._ready = kqueue()            # Tasks ready to run
        self._tasks = { }                 # Task table
        self._signal_sets = None          # Dict { signo: [ sigsets ] } of watched signals (initialized only if signals used)
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

        # Optional crash handler callback
        self._crash_handler = None

        # If a monitor is specified, launch it
        if with_monitor or 'CURIOMONITOR' in os.environ:
            Monitor(self)

    def __del__(self):
        if self._kernel_task_id:
            self._notify_sock.close()
            self._wait_sock.close()
            self._kernel_task_id = None
        if self._thread_pool:
            self._thread_pool.shutdown()
        if self._process_pool:
            self._process_pool.shutdown()

    # Main Kernel Loop
    # ----------
    def run(self, coro=None, *, pdb=False, log_errors=True, shutdown=False):
        '''
        Run the kernel until no more non-daemonic tasks remain.
        If pdb is True, pdb is launched when a task crash occurs.
        If log_errors is True, uncaught exceptions in tasks are logged.
        If shutdown is True, the kernel cleans up after itself after all tasks complete.
        '''
        
        # Motto:  "What happens in the kernel stays in the kernel"

        # ---- Kernel State
        current = None                          # Currently running task
        selector = self._selector               # Event selector
        ready = self._ready                     # Ready queue
        tasks = self._tasks                     # Task table
        sleeping = self._sleeping               # Sleeping task queue
        wake_queue = self._wake_queue           # External wake queue

        # ---- Number of non-daemonic tasks running
        njobs = sum(not task.daemon for task in tasks.values())
        
        # ---- Bound methods
        selector_register = selector.register
        selector_unregister = selector.unregister
        selector_select = selector.select
        ready_popleft = ready.popleft
        ready_append = ready.append
        ready_appendleft = ready.appendleft
        time_monotonic = time.monotonic

        # ---- In-kernel task used for processing signals and futures

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
            self._notify_sock.send(b'\x00')

        # Initialize the loopback socket and launch the kernel task if needed
        def _init_loopback():
            self._notify_sock, self._wait_sock = socket.socketpair()
            self._wait_sock.setblocking(False)
            self._notify_sock.setblocking(False)
            task = Task(_kernel_task())
            _reschedule_task(task)
            self._kernel_task_id = task.id

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

                sigs = (signal.Signals(n) for n in data if n in self._signal_sets)
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

        # Cancel a task. This causes a CancelledError exception to raise in the
        # underlying coroutine.  The coroutine can elect to catch the exception
        # and continue to run to perform cleanup actions.  However, it would 
        # normally terminate shortly afterwards.   This method is also used to 
        # raise timeouts.
        def _cancel_task(task, exc=CancelledError):
            if task.terminated:
                return True

            if not task.cancel_func:
                # All tasks set a cancellation function when they
                # block.  If there is no cancellation function set. It
                # means that the task finished whatever it might have
                # been working on and it's sitting in the ready queue
                # ready to run.  This presents a rather tricky corner
                # case of cancellation. First, it means that the task
                # successfully completed whatever it was waiting to
                # do, but it has not yet communicated the result back.
                # This could be something critical like acquiring a
                # lock.  Because of that, can't just arbitrarily nuke
                # the task.  Instead, we have to let it be rescheduled
                # and properly process the result of the successfully
                # completed operation.  The return of False here means
                # that cancellation failed and that it should be
                # retried.  Public facing API calls that cancel tasks
                # need to check this return value and retry.
                return False

            # Detach the task from where it might be waiting at this moment
            task.cancel_func()

            # Reschedule it with a pending exception
            _reschedule_task(task, exc=exc(exc.__name__))
            return True

        # Cleanup task.  This is called after the underlying coroutine has
        # terminated.  value and exc give the return value or exception of
        # the coroutine.  This wakes any tasks waiting to join.
        def _cleanup_task(task, value=None, exc=None):
            nonlocal njobs
            task.next_value = value
            task.next_exc = exc
            task.timeout = None

            if not task.daemon:
                njobs -=1

            if task.joining:
                for wtask in task.joining:
                    _reschedule_task(wtask) 
                task.joining = None
            task.terminated = True

            del tasks[task.id]

        # Shut down the kernel, cleaning up resources and cancelling
        # still-running daemon tasks
        def _shutdown():
            nonlocal njobs
            for task in sorted(tasks.values(), key=lambda t: t.id, reverse=True):
                if task.id == self._kernel_task_id:
                    continue

                # If the task is daemonic, force it to non-daemon status and cancel it
                if task.daemon:
                    njobs += 1
                    task.daemon = False

                assert _cancel_task(task)

            # Run all of the daemon tasks through cancellation
            if ready:
                self.run()

            # Cancel the kernel loopback task (if any)
            task = tasks.pop(self._kernel_task_id, None)
            if task:
                task.cancel_func()
                self._notify_sock.close()
                self._notify_sock = None
                self._wait_sock.close()
                self._wait_sock = None
                self._kernel_task_id = None

            # Remove the signal handling file descriptor (if any)
            if self._signal_sets:
                signal.set_wakeup_fd(-1)
                self._signal_sets = None
                self._default_signals = None

        # Set a timeout or sleep event on the current task
        def _set_timeout(seconds, sleep_type='timeout'):
            timeout = time_monotonic() + seconds
            item = (timeout, current.id, sleep_type)
            heapq.heappush(sleeping, item)
            setattr(current, sleep_type, timeout)

        # ---- Traps
        #
        # These implement the low-level functionality that is
        # triggered by coroutines.  They are never invoked directly
        # and there is no public API outside the kernel.  Instead,
        # coroutines use a statement such as
        #   
        #   yield ('_trap_io', sock, EVENT_READ, 'READ_WAIT')
        #
        # to invoke a specific trap.

        # Wait for I/O
        def _trap_io(_, fileobj, event, state):
            # See comment about deferred unregister in run().  If the requested
            # I/O operation is *different* than the last I/O operation that was
            # performed by the task, we need to unregister the last I/O resource used
            # and register a new one with the selector.  
            if current._last_io != (state, fileobj):
                if current._last_io:
                    selector_unregister(current._last_io[1])
                selector_register(fileobj, event, current)

            # This step indicates that we have managed any deferred I/O management
            # for the task.  Otherwise the run() method will perform an unregistration step.
            current._last_io = None
            current.state = state
            current.cancel_func = lambda: selector_unregister(fileobj)

        # Wait on a Future
        def _trap_future_wait(_, future, event):
            if not self._kernel_task_id:
                _init_loopback()

            current.state = 'FUTURE_WAIT'
            current.cancel_func = (lambda task=current: 
                                   setattr(task, 'future', future.cancel() and None))
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
            future.add_done_callback(lambda fut, task=current: 
                                     _wake(task, fut) if task.future is fut else None)

            # An optional threading.Event object can be passed and set to
            # start a worker thread.   This makes it possible to have a lock-free
            # Future implementation where worker threads only start after the
            # callback function has been set above.
            if event:
                event.set()

        # Add a new task to the kernel
        def _trap_spawn(_, coro, daemon):
            task = _new_task(coro, daemon)
            _reschedule_task(current, value=task)

        # Reschedule one or more tasks from a queue
        def _trap_reschedule_tasks(_, queue, n, value, exc):
            while n > 0:
                _reschedule_task(queue.popleft(), value=value, exc=exc)
                n -= 1
            _reschedule_task(current)

        # Join with a task
        def _trap_join_task(_, task):
            if task.terminated:
                _reschedule_task(current, value=task.next_value, exc=task.next_exc)
            else:
                if task.joining is None:
                    task.joining = kqueue()
                _trap_wait_queue(_, task.joining, 'TASK_JOIN')

        # Cancel a task
        def _trap_cancel_task(_, task, exc):
            if task == current:
                _reschedule_task(current, exc=CurioError("A task can't cancel itself"))
                return

            if _cancel_task(task, exc):
                _trap_join_task(_, task)

            else:
                # Fail with a _CancelRetry exception to indicate that the cancel
                # request should be attempted again.  This happens in the case
                # that a cancellation request is issued against a task that
                # ready to run in the ready queue.
                _reschedule_task(current, exc=_CancelRetry())

        # Wait on a queue
        def _trap_wait_queue(_, queue, state):
            queue.append(current)
            current.state = state
            current.cancel_func = lambda current=current: queue.remove(current)

        # Sleep for a specified period
        def _trap_sleep(_, seconds):
            if seconds > 0:
                _set_timeout(seconds, 'sleep')
                current.state = 'TIME_SLEEP'
                current.cancel_func = lambda task=current: setattr(task, 'sleep', None)
            else:
                _reschedule_task(current)

        # Watch signals
        def _trap_sigwatch(_, sigset):
            # Initialize the signal handling part of the kernel if not done already
            # Note: This only works if running in the main thread
            if self._signal_sets is None:
                self._signal_sets = defaultdict(list)
                self._default_signals = { }
                if not self._kernel_task_id:
                    _init_loopback()
                old_fd = signal.set_wakeup_fd(self._notify_sock.fileno())     
                assert old_fd < 0, 'Signals already initialized %d' % old_fd

            for signo in sigset.signos:
                if not self._signal_sets[signo]:
                    self._default_signals[signo] = signal.signal(signo, lambda signo, frame:None)
                self._signal_sets[signo].append(sigset)

            _reschedule_task(current)

        # Unwatch signals
        def _trap_sigunwatch(_, sigset):
            for signo in sigset.signos:
                if sigset in self._signal_sets[signo]:
                    self._signal_sets[signo].remove(sigset)

                # If there are no active watchers for a signal, revert it back to default behavior
                if not self._signal_sets[signo]:
                    signal.signal(signo, self._default_signals[signo])
                    del self._signal_sets[signo]
            _reschedule_task(current)

        # Wait for a signal
        def _trap_sigwait(_, sigset):
            sigset.waiting = current
            current.state = 'SIGNAL_WAIT'
            current.cancel_func = lambda: setattr(sigset, 'waiting', None)

        # Set a timeout to be delivered to the calling task
        def _trap_set_timeout(_, seconds):
            old_timeout = current.timeout
            if seconds:
                _set_timeout(seconds)
            else:
                current.timeout = None
            current.next_value = old_timeout
            ready_appendleft(current)

        # Clear a previously set timeout
        def _trap_unset_timeout(_, previous):
            current.timeout = previous
            current.next_value = None
            ready_appendleft(current)

        # Return the running kernel
        def _trap_get_kernel(_):
            ready_appendleft(current)
            current.next_value = self

        # Return the currently running task
        def _trap_get_current(_):
            ready_appendleft(current)
            current.next_value = current

        # Create the traps table
        traps = { name: trap 
                  for name, trap in locals().items()
                  if name.startswith('_trap_') }
        
        # If a coroutine was given, add it as the first task
        maintask = _new_task(coro) if coro else None

        # ------------------------------------------------------------
        # Main Kernel Loop
        # ------------------------------------------------------------
        while njobs > 0:
            # --------
            # Poll for I/O as long as there is nothing to run
            # --------
            while not ready:
                # Wait for an I/O event (or timeout)
                timeout = (sleeping[0][0] - time_monotonic()) if sleeping else None
                events = selector_select(timeout)

                # Reschedule tasks with completed I/O
                for key, mask in events:
                    task = key.data
                    # Please see comment regarding deferred_unregister in run()
                    task._last_io = (task.state, key.fileobj)
                    task.state = 'READY'
                    task.cancel_func = None
                    ready_append(task)

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
                                    _reschedule_task(task)
                            else:
                                if tm == task.timeout:
                                    task.timeout = None
                                    _cancel_task(task, exc=TaskTimeout)

            # --------
            # Run ready tasks
            # --------
            while ready:
                current = ready_popleft()
                try:
                    current.state = 'RUNNING'
                    current.cycles += 1
                    if current.next_exc is None:
                        trap = current.send(current.next_value)
                    else:
                        trap = current.throw(current.next_exc)
                        current.next_exc = None

                    # Execute the trap
                    traps[trap[0]](*trap) 

                except StopIteration as e:
                    _cleanup_task(current, value = e.value)

                except CancelledError as e:
                    current.exc_info = sys.exc_info()
                    current.state = 'CANCELLED'
                    _cleanup_task(current)

                except Exception as e:
                    current.exc_info = sys.exc_info()
                    current.state = 'CRASHED'
                    exc = TaskError('Task Crashed')
                    exc.__cause__ = e
                    _cleanup_task(current, exc=exc)
                    if log_errors:
                        log.error('Curio: Task Crash: %s' % current, exc_info=True)

                    if self._crash_handler:
                        self._crash_handler(current)

                    if pdb:
                        import pdb as _pdb
                        _pdb.post_mortem(current.exc_info[2])

                except SystemExit:
                    _cleanup_task(current)
                    raise

                finally:
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
                        selector_unregister(current._last_io[1])
                        current._last_io = None
                    
        # If kernel shutdown has been requested, issue a cancellation request to all remaining tasks
        if shutdown:
            _shutdown()

        return maintask.next_value if maintask else None

# ----------------------------------------------------------------------
# Coroutines corresponding to the kernel traps.  These functions
# provide the bridge from tasks to the underlying kernel. This is the
# only place with the explicit @coroutine decorator needs to be used.
# All other code in curio and in user-tasks should use async/await
# instead.  Direct use by users is allowed, but if you're working with
# these traps directly, there is probably a higher level interface
# that simplifies the problem you're trying to solve (e.g., Socket,
# File, objects, etc.)
# ----------------------------------------------------------------------

@coroutine
def _read_wait(fileobj):
    '''
    Wait until reading can be performed.
    '''
    yield ('_trap_io', fileobj, EVENT_READ, 'READ_WAIT')

@coroutine
def _write_wait(fileobj):
    '''
    Wait until writing can be performed.
    '''
    yield ('_trap_io', fileobj, EVENT_WRITE, 'WRITE_WAIT')

@coroutine
def _future_wait(future, event=None):
    '''
    Wait for the future of a Future to be computed.
    '''
    yield ('_trap_future_wait', future, event)

@coroutine
def _sleep(seconds):
    '''
    Sleep for a given number of seconds. Sleeping for 0 seconds
    simply forces the current task to yield to the next task (if any).
    '''
    yield ('_trap_sleep', seconds)

@coroutine
def _spawn(coro, daemon):
    '''
    Create a new task
    '''
    return (yield '_trap_spawn', coro, daemon)

@coroutine
def _cancel_task(task, exc=CancelledError):
    '''
    Cancel a task.  Causes a CancelledError exception to raise in the task.
    '''
    while True:
        try:
            yield ('_trap_cancel_task', task, exc)
            return
        except _CancelRetry:
            pass

@coroutine
def _join_task(task):
    '''
    Wait for a task to terminate.
    '''
    yield ('_trap_join_task', task)

@coroutine
def _wait_on_queue(queue, state):
    '''
    Put the task to sleep on a kernel queue.
    '''
    yield ('_trap_wait_queue', queue, state)

@coroutine
def _reschedule_tasks(queue, n=1, value=None, exc=None):
    '''
    Reschedule one or more tasks waiting on a kernel queue.
    '''
    yield ('_trap_reschedule_tasks', queue, n, value, exc)

@coroutine
def _sigwatch(sigset):
    '''
    Start monitoring a signal set
    '''
    yield ('_trap_sigwatch', sigset)

@coroutine
def _sigunwatch(sigset):
    '''
    Stop watching a signal set
    '''
    yield ('_trap_sigunwatch', sigset)

@coroutine
def _sigwait(sigset):
    '''
    Wait for a signal to arrive.
    '''
    yield ('_trap_sigwait', sigset)

@coroutine
def _get_kernel():
    '''
    Get the kernel executing the task.
    '''
    result = yield ('_trap_get_kernel',)
    return result

@coroutine
def _get_current():
    '''
    Get the currently executing task
    '''
    result = yield ('_trap_get_current',)
    return result

@coroutine
def _set_timeout(seconds):
    '''
    Set a timeout for the current task.  
    '''
    result = yield ('_trap_set_timeout', seconds)
    return result

@coroutine
def _unset_timeout(previous):
    '''
    Restore the previous timeout for the current task.
    '''
    yield ('_trap_unset_timeout', previous)

# ----------------------------------------------------------------------
# Public-facing syscalls.  These coroutines wrap a low-level coroutine
# with an extra layer involving an async/await function.  The main
# reason for doing this is that the user will get proper warning
# messages if they forget to use the required 'await' keyword.
# -----------------------------------------------------------------------

async def sleep(seconds):
    '''
    Sleep for a specified number of seconds.
    '''
    await _sleep(seconds)

async def spawn(coro, *, daemon=False):
    '''
    Create a new task.
    '''
    return await _spawn(coro, daemon)

class _TimeoutAfter(object):
    def __init__(self, seconds, ignore=False, timeout_result=None):
        self._seconds = seconds
        self._ignore = ignore
        self._timeout_result = timeout_result
        self.result = True

    async def __aenter__(self):
        self._prior = await _set_timeout(self._seconds)
        return self

    async def __aexit__(self, ty, val, tb):
        await _unset_timeout(self._prior)
        if ty == TaskTimeout:
            self.result = self._timeout_result
            if self._ignore:
                return True

async def _timeout_after_func(seconds, coro, ignore=False, timeout_result=None):
    '''
    Runs a coroutine with a timeout applied.
    '''
    prior = await _set_timeout(seconds)
    try:
        return await coro
    except TaskTimeout:
        if not ignore:
            raise
        return timeout_result
    finally:
        await _unset_timeout(prior)

def timeout_after(seconds, coro=None):
    '''
    Raise a TaskTimeout exception in the calling task after seconds
    have elapsed.  This function may be used in two ways. You can
    apply it to a single coroutine:

         await timeout_after(seconds, coro(args))

    or you can use it as an asynchronous context manager:

         async with timeout_after(seconds):
             await coro1(args)
             await coro2(args)
             ...
    '''
    if coro is None:
        return _TimeoutAfter(seconds)
    else:
        return _timeout_after_func(seconds, coro)

def stop_after(seconds, coro=None, *, timeout_result=None):
    '''
    Stop the enclosed task or block of code after seconds have
    elapsed.  No exception is raised on time expiration. There are
    two ways to use this function. You can call a single coroutine
    like this:
    
        if stop_after(5, coro(args)) is None:
            # A timeout occurred
            ...

    If the time period expires, None is returned. The value can be
    changed by passing the timeout_result keyword argument.

    Alternatively, you can use this function as an async context
    manager like this:

        async with stop_after(5) as r:
            await coro1(args)
            await coro2(args)
            ...
        if r.result is None:
            # A timeout occurred

    When used as a context manager, the return manager object has
    a result attribute that will be set to None if the time
    period expires (or True otherwise).
    '''
    if coro is None:
        return _TimeoutAfter(seconds, ignore=True, timeout_result=timeout_result)
    else:
        return _timeout_after_func(seconds, coro, ignore=True, timeout_result=timeout_result)

async def current_task():
    '''
    Returns a reference to the current task
    '''
    return await _get_current()

def run(coro, *, pdb=False, log_errors=True, with_monitor=False, selector=None):
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
    kernel = Kernel(selector=selector, with_monitor=with_monitor)
    result = kernel.run(coro, pdb=pdb, log_errors=log_errors, shutdown=True)
    return result

__all__ = [ 'Kernel', 'sleep', 'spawn', 'timeout_after', 'stop_after', 'current_task',
            'SignalSet', 'TaskError', 'TaskTimeout', 'CancelledError', 'run' ]
            
from .monitor import Monitor
        
