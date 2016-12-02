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

# Logger where uncaught exceptions from crashed tasks are logged
log = logging.getLogger(__name__)

from .errors import *
from .errors import _CancelRetry
from .task import Task
from .traps import _read_wait, BlockingTraps, SyncTraps
from .local import _enable_tasklocal_for, _copy_tasklocal

class BlockingTaskWarning(RuntimeWarning):
    pass

# kqueue is the datatype used by the kernel for all of its queuing functionality.
# Any time a task queue is needed, use this type instead of directly hard-coding the
# use of a deque.  This will make sure the code continues to work even if the
# queue type is changed later.

kqueue = deque

# ----------------------------------------------------------------------
# Underlying kernel that drives everything
# ----------------------------------------------------------------------

class Kernel(object):
    def __init__(self, *, selector=None, with_monitor=False, pdb=False, log_errors=True,
                 crash_handler=None, warn_if_task_blocks_for=0.05):
        if selector is None:
            selector = DefaultSelector()

        self._selector = selector
        self._ready = kqueue()            # Tasks ready to run
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

        # Optional crash handler callback
        self._crash_handler = crash_handler

        self._warn_if_task_blocks_for = warn_if_task_blocks_for

        self._pdb = pdb
        self._log_errors = log_errors

        self._monitor = None

        # If a monitor is specified, launch it
        if with_monitor or 'CURIOMONITOR' in os.environ:
            self._monitor = Monitor(self)

    def __del__(self):
        if self._selector is not None:
            raise RuntimeError('Curio kernel not properly terminated.  Please use Kernel.run(shutdown=True)')

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
        self._default_signals = { }
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
        if self._notify_sock:
            self._notify_sock.close()
            self._notify_sock = None
            self._wait_sock.close()
            self._wait_sock = None

        if self._signal_sets:
            signal.set_wakeup_fd(-1)
            self._signal_sets = None
            self._default_signals = None

        if self._selector:
            self._selector.close()
            self._selector = None

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

        # ---- Number of non-daemonic tasks running
        njobs = sum(not task[0].daemon for task in tasks.values())

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
            self._tasks[task.id] = [task, current, set()]

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
            tasks[task.id] = [task, current, set()]
            if current is not None:
                tasks[current.id][2].add(task)
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

        # Attempt to cancel a task. This causes a CancelledError exception to
        # raise in the underlying coroutine.  The coroutine can elect to catch
        # the exception and continue to run to perform cleanup actions.
        # However, it would normally terminate shortly afterwards.  This
        # method is also used to raise timeouts.
        #
        # This only works if the task is currently blocked. If it succeeds, it
        # returns True. If it fails, it returns False. (And in that case, we
        # need to arrange for the cancellation to happen some other way.)
        def _try_cancel_blocked_task(task, exc=CancelledError, val=None):
            if task.terminated:
                return True

            if not task.cancel_allowed_stack[-1]:
                return False

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
            _reschedule_task(task, exc=exc(exc.__name__ if val is None else val))
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
                njobs -= 1

            if task.joining:
                for wtask in task.joining:
                    _reschedule_task(wtask)
                task.joining = None
            task.terminated = True

            _, parent, child_tasks = tasks[task.id]
            if parent is not None and parent.id in tasks:
                tasks[parent.id][2].remove(task)
            for child in child_tasks:
                tasks[child.id][1] = maintask
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
            tocancel = [task[0] for task in tasks.values() if task[0].id != self._kernel_task_id]

            # Cancel all non-daemonic tasks first
            tocancel.sort(key=lambda task: task.daemon)

            # Cancel the kernel loopback task last
            if self._kernel_task_id is not None:
                tocancel.append(tasks[self._kernel_task_id][0])

            if tocancel:
                _new_task(_shutdown_tasks(tocancel))
                self.run()

            self._kernel_task_id = None

            # There had better not be any tasks left
            assert not tasks

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
                selector_modify(fileobj,  mask | event,
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
        # 2) Sync trap handlers act like regular function calls -- whatever
        #    they return or raise will be passed back to the invoker.

        # Wait for I/O
        def _blocking_trap_io(fileobj, event, state):
            # See comment about deferred unregister in run().  If the requested
            # I/O operation is *different* than the last I/O operation that was
            # performed by the task, we need to unregister the last I/O resource used
            # and register a new one with the selector.
            if current._last_io != (fileobj, event):
                if current._last_io:
                    _unregister_event(*current._last_io)
                _register_event(fileobj, event, current)
            
            # This step indicates that we have managed any deferred I/O management
            # for the task.  Otherwise the run() method will perform an unregistration step.
            current._last_io = None
            return (state, lambda: _unregister_event(fileobj, event))

        # Wait on a Future
        def _blocking_trap_future_wait(future, event):
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
        def _sync_trap_spawn(coro, daemon):
            task = _new_task(coro, daemon)
            _copy_tasklocal(current, task)
            return task

        # Reschedule one or more tasks from a queue
        def _sync_trap_reschedule_tasks(queue, n):
            for _ in range(n):
                _reschedule_task(queue.popleft())

        # Trap that returns a function for rescheduling tasks from synchronous code
        def _sync_trap_queue_reschedule_function(queue):
            def _reschedule(n):
                for _ in range(n):
                    _reschedule_task(queue.popleft())
            return _reschedule

        # Join with a task
        def _blocking_trap_join_task(task):
            if task.terminated:
                return _blocking_trap_sleep(0, False)
            else:
                if task.joining is None:
                    task.joining = kqueue()
                return _blocking_trap_wait_queue(task.joining, 'TASK_JOIN')

        # Enter a {defer,allow}_cancellation block
        def _sync_trap_cancel_allowed_stack_push(state):
            current.cancel_allowed_stack.append(state)
            _check_pending_cancellation()

        def _sync_trap_cancel_allowed_stack_pop(state):
            previous = current.cancel_allowed_stack.pop()
            assert previous == state
            assert current.cancel_allowed_stack
            _check_pending_cancellation()

        def _check_pending_cancellation():
            if not current.cancel_allowed_stack[-1]:
                return
            if current.cancel_pending:
                current.cancel_pending = False
                raise CancelledError("CancelledError")
            else:
                if current.timeout is not None:
                    now = time_monotonic()
                    if current.timeout <= now:
                        raise TaskTimeout(now)

        # Cancel a task
        def _sync_trap_cancel_task(task):
            if task.cancelled:
                return
            task.cancelled = True

            if _try_cancel_blocked_task(task, CancelledError):
                # we were able to do it immediately
                pass
            else:
                # wait for the next cancellation point (either exiting a 'with
                # defer_cancellation' block, or entering a blocking call).
                task.cancel_pending = True

        # Wait on a queue
        def _blocking_trap_wait_queue(queue, state):
            queue.append(current)
            return (state, lambda current=current: queue.remove(current))

        # Sleep for a specified period. Returns value of monotonic clock.
        # absolute flag indicates whether or not an absolute or relative clock 
        # interval has been provided
        def _blocking_trap_sleep(clock, absolute):
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
        def _sync_trap_sigwatch(sigset):
            # Initialize the signal handling part of the kernel if not done already
            # Note: This only works if running in the main thread
            if self._kernel_task_id is None:
                _init_loopback_task()

            if self._signal_sets is None:
                self._init_signals()

            self._signal_watch(sigset)

        # Unwatch signals
        def _sync_trap_sigunwatch(sigset):
            self._signal_unwatch(sigset)

        # Wait for a signal
        def _blocking_trap_sigwait(sigset):
            sigset.waiting = current
            return ('SIGNAL_WAIT', lambda: setattr(sigset, 'waiting', None))

        # Set a timeout to be delivered to the calling task
        def _sync_trap_set_timeout(timeout):
            old_timeout = current.timeout
            if timeout:
                _set_timeout(timeout)
                if old_timeout and current.timeout > old_timeout:
                    current.timeout = old_timeout
            else:
                current.timeout = None

            return old_timeout

        # Clear a previously set timeout
        def _sync_trap_unset_timeout(previous):
            # Here's an evil corner case.  Suppose the previous timeout in effect
            # has already expired?  If so, then we need to arrange for a timeout
            # to be generated.  However, this has to happen on the *next* blocking
            # call, not on this trap.  That's because the "unset" timeout feature
            # is usually done in the finalization stage of the previous timeout
            # handling.  If we were to raise a TaskTimeout here, it would get mixed
            # up with the prior timeout handling and all manner of head-explosion
            # will occur.

            if previous and previous < time_monotonic():
                _set_timeout(previous)
            else:
                current.timeout = previous

        # Return the running kernel
        def _sync_trap_get_kernel():
            return self

        # Return the currently running task
        def _sync_trap_get_current():
            return current

        def _sync_trap_get_child_tasks(task):
            return list(tasks[task.id][2])

        # Return the current value of the kernel clock
        def _sync_trap_clock():
            return time_monotonic()

        # Create the traps tables
        blocking_traps = [None] * len(BlockingTraps)
        for trap in BlockingTraps:
            blocking_traps[trap] = locals()[trap.name]

        sync_traps = [None] * len(SyncTraps)
        for trap in SyncTraps:
            sync_traps[trap] = locals()[trap.name]

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
                intfd = type(key.fileobj) is int
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
                cancel_retry = []
                while sleeping and sleeping[0][0] <= current_time:
                    tm, taskid, sleep_type = heapq.heappop(sleeping)
                    # When a task wakes, verify that the timeout value matches that stored
                    # on the task. If it differs, it means that the task completed its
                    # operation, was cancelled, or is no longer concerned with this
                    # sleep operation.  In that case, we do nothing
                    if taskid in tasks:
                        task = tasks[taskid][0]
                        if sleep_type == 'sleep':
                            if tm == task.sleep:
                                task.sleep = None
                                _reschedule_task(task, value=current_time)
                        else:
                            if tm == task.timeout:
                                if _try_cancel_blocked_task(task, exc=TaskTimeout, val=current_time):
                                    task.timeout = None
                                else:
                                    # Note: There is a possibility that a task will be
                                    # marked for timeout-cancellation even though it is
                                    # sitting on the ready queue.  In this case, the
                                    # rescheduled task is given priority. However, the
                                    # cancellation timeout will be put back on the sleep
                                    # queue and reprocessed the next time around.
                                    cancel_retry.append((tm, taskid, sleep_type))

                # Put deferred cancellation requests back on sleep queue
                for item in cancel_retry:
                    heapq.heappush(sleeping, item)

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
                current = ready.popleft()
                try:
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

                        # If the trap is synchronous, then handle it
                        # immediately without rescheduling. Sync trap handlers
                        # have a different API than blocking trap handlers --
                        # they just return or raise whatever the trap should
                        # return or raise.
                        while type(trap[0]) is SyncTraps:
                            try:
                                next_value = sync_traps[trap[0]](*trap[1:])
                            except Exception as next_exc:
                                trap = current._throw(next_exc)
                            else:
                                trap = current._send(next_value)

                except StopIteration as e:
                    _cleanup_task(current, value=e.value)

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

                    if self._crash_handler:
                        self._crash_handler(current)

                    if self._pdb:
                        import pdb as _pdb
                        _pdb.post_mortem(current.exc_info[2])

                except: # (SystemExit, KeyboardInterrupt):
                    _cleanup_task(current)
                    raise

                else:
                    # Execute the trap
                    assert type(trap[0]) is BlockingTraps
                    current.state, current.cancel_func = blocking_traps[trap[0]](*trap[1:])
                    # Entering a blocking call triggers a check for pending
                    # cancellation
                    assert current.cancel_func is not None
                    if (current.cancel_allowed_stack[-1] and current.cancel_pending):
                        result = _try_cancel_blocked_task(current, CancelledError)
                        assert result

                finally:
                    duration = time_monotonic() - task_start
                    if duration > self._warn_if_task_blocks_for:
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

def run(coro, *, pdb=False, log_errors=True, with_monitor=False, selector=None, 
        crash_handler=None, warn_if_task_blocks_for=0.05, **extra):
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
                    log_errors=log_errors, pdb=pdb, crash_handler=crash_handler,
                    warn_if_task_blocks_for=warn_if_task_blocks_for,
                    **extra)
    with kernel:
        result = kernel.run(coro)
    return result

__all__ = [ 'Kernel', 'run', 'BlockingTaskWarning' ]

from .monitor import Monitor
