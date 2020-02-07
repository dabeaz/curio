Curio Reference Manual
======================

Coroutines
----------

Curio executes coroutines.  A coroutine is a function defined using
``async def``.  For example::

    async def hello(name):
          return 'Hello ' + name

Coroutines call other coroutines using ``await``. For example::

    async def main(name):
          s = await hello(name)
          print(s)

Unlike a normal function, a coroutine never runs on its own.
It always executes under the supervision of a manager (e.g., an
event-loop, a kernel, etc.).  In Curio, an initial coroutine is
executed using ``run()``.  For example::

    import curio
    curio.run(main, 'Guido')

When it's executing, a coroutine is encapsulated inside a "Task."  Whenever
the word "task" is used, it refers to a running coroutine.

The Execution Kernel
--------------------

Coroutines are executed by an underlying kernel.  Normally, you run
a coroutine using the following:

.. function:: run(corofunc, *args, debug=None, selector=None, with_monitor=False, taskcls=Task)

   Run *corofunc* to completion and return its result.  *args* are the
   arguments provided to *corofunc*.  *with_monitor* enables the task
   monitor.  *selector* is an instance of a selector from the
   :mod:`selectors <python:selectors>` module. *debug* is a list of optional
   debugging features. See the section on debugging for more detail.
   *taskcls* is the class used to instantiate tasks.  If ``run()`` is called 
   when a task is already running, a ``RuntimeError`` is raised.

If you are going to repeatedly execute coroutines one after the other, it
will be more efficient to create a ``Kernel`` instance and submit
them using its ``run()`` method as described below:

.. class:: Kernel(selector=None, debug=None, taskcls=Task):

   Create an instance of a Curio kernel.  The arguments are the same
   as described above for the :func:`run()` function.  

There is only one method that may be used on a :class:`Kernel` instance.

.. method:: Kernel.run(corofunc=None, *args, shutdown=False)

   Runs async function *corofunc* and return its reself.
   *args* are the arguments given to *corofunc*.  If
   *shutdown* is ``True``, the kernel cancels all remaining tasks
   and performs a clean shutdown. Calling this method with *corofunc*
   set to ``None`` causes the kernel to run through a single check for
   task activity before returning immediately.  Raises a
   ``RuntimeError`` if a task is submitted to an already running kernel
   or if an attempt is made to run more than one kernel in a thread.

A kernel may be used as a context manager. For example::

    with Kernel() as kernel:
        kernel.run(corofunc1)
        kernel.run(corofunc2)
        ...
    # Kernel shuts down here

When submitting a task, you can either provide an async
function and calling arguments or you can provide an already instantiated
coroutine.  For example, both of these invocations of ``run()`` work::

    async def hello(name):
        print('hello', name)

    run(hello, 'Guido')    # Preferred
    run(hello('Guido'))    # Ok

This convention is observed by nearly all other functions that accept
coroutines (e.g., spawning tasks, waiting for timeouts, etc.).  As a
general rule, the first form of providing a function and arguments
should be preferred. This form of calling is required for certain 
parts of Curio so your code will be more consistent if you use it.

Tasks
-----

The following functions are defined to help manage the execution of tasks.

.. asyncfunction:: spawn(corofunc, *args, daemon=False)

   Create a new task that runs the async function *corofunc*.  *args*
   are the arguments provided to *corofunc*. Returns a :class:`Task`
   instance as a result.  The *daemon* option specifies
   that the new task will never be joined and that its result may be
   disregarded. 

.. asyncfunction:: current_task()

   Returns the :class:`Task` instance corresponding to the caller.  

.. asyncfunction:: schedule()

   Immediately switch to the next ready task.  

:func:`spawn` and :func:`current_task` return a :class:`Task` instance 
that provides the following methods::

.. asyncmethod:: Task.join()

   Wait for the task to terminate and return its result.
   Raises :exc:`curio.TaskError` if the task failed with an
   exception. This is a chained exception.  The ``__cause__`` attribute 
   contains the actual exception raised by the task when it crashed.

.. asyncmethod:: Task.wait()

   Waits for task to terminate, but returns no value. 

.. asyncmethod:: Task.cancel(blocking=True)

   Cancels the task by raising a :exc:`curio.TaskCancelled` exception
   at its next blocking operation.  If ``blocking=True`` (the
   default), waits for the task to actually terminate.  A task may
   only be cancelled once.  If this method is invoked more than once,
   the second request will wait until the task is cancelled from the
   first request.  If the task has already terminated, this method
   does nothing and returns immediately.  Returns ``True`` if the task
   was actually cancelled and ``False`` if the task was already
   terminated.  Note: uncaught exceptions that occur as a result of
   cancellation are logged, but not propagated out of the
   ``Task.cancel()`` method.

.. method:: Task.traceback()

   Creates a stack traceback string for the task.  Useful for debugging if you print it out.

.. method:: Task.where()

   Return a (filename, lineno) tuple where the task is executing. Useful for debugging and logging.

The following attributes and properties are defined on :class:`Task` instances:

.. attribute:: Task.id

   The task's integer id.  Monotonically increases. 

.. attribute:: Task.coro

   The underlying coroutine associated with the task.

.. attribute:: Task.daemon

   Boolean flag that indicates whether or not a task is daemonic.

.. attribute:: Task.state

   The name of the task's current state.  Useful for debugging.

.. attribute:: Task.cycles

   The number of scheduling cycles the task has completed. 

.. attribute:: Task.result

   A property holding the task result. If accessed before the task terminates,
   a ``RuntimeError`` exception is raised. If the task crashed with an exception,
   that exception is reraised on access.

.. attribute:: Task.exception

   Exception raised by a task, if any.  ``None`` otherwise. 

.. attribute:: Task.cancelled

   A boolean flag that indicates whether or not the task was cancelled.

.. attribute:: Task.terminated

   A boolean flag that indicates whether or not the task has terminated.

.. attribute:: Task.cancel_pending

   An instance of a pending cancellation exception. Raised on the next blocking operation.

.. attribute:: Task.allow_cancel

   A boolean flag that indicates whether or not cancellation exceptions can be delivered.
   This is better controlled using the ``disable_cancellation()`` function as opposed
   to being set directly.


Task Groups
-----------

Tasks may be grouped together to better manage their execution and
collect results.  To do this, create a ``TaskGroup`` instance.

.. class:: TaskGroup(tasks=(), *, wait=all)

   A class representing a group of executing tasks.  *tasks* is an
   optional set of existing tasks to put into the group.  New tasks
   can later be added using the ``spawn()`` or ``add_task()`` methods. *wait*
   specifies the policy used by the ``join()`` method when waiting for tasks.  If *wait* is
   ``all``, then wait for all tasks to complete.  If *wait* is
   ``any`` then wait for any task to terminate and cancel any
   remaining tasks.  If *wait* is ``object``, then wait for any task
   return a non-None object, cancelling all remaining
   tasks afterwards. If *wait* is ``None``, then immediately cancel all running tasks. 
   Task groups do not form a hierarchy or any kind of relationship to
   other previously created task groups or tasks.  Moreover, Tasks created by
   the top level ``spawn()`` function are not placed into any task group.
   To create a task in a group, it should be created using ``TaskGroup.spawn()``
   or explicitly added using ``TaskGroup.add_task()``.

The following methods are supported on ``TaskGroup`` instances:

.. asyncmethod:: TaskGroup.spawn(corofunc, *args)

   Create a new task that's part of the group.  Returns a ``Task``
   instance. 

.. asyncmethod:: TaskGroup.add_task(coro)

   Adds an already existing task to the task group. 

.. asyncmethod:: TaskGroup.next_done()

   Returns the next completed task.  Returns ``None`` if no more tasks remain.

.. asyncmethod:: TaskGroup.next_result()

   Returns the result of the next completed task.  If the task failed with an
   exception, that exception is raised.  A ``RuntimeError`` exception is raised
   if called when no remaining tasks are available. 

.. asyncmethod:: TaskGroup.join()

   Wait for all tasks in the group to terminate according to the wait policy
   set for the group.  If any of the monitored tasks exits with an exception or
   if the ``join()`` operation itself is cancelled, all remaining tasks in the 
   group are cancelled. If a ``TaskGroup`` is used as a
   context manager, the ``join()`` method is called on block-exit.

.. asyncmethod:: TaskGroup.cancel_remaining()

   Cancel all remaining tasks.  Cancelled tasks are disregarded by the task
   group when reporting results.  

.. attribute:: TaskGroup.completed

   The first task that completed with a valid result when joining. Typically used
   in combination with the ``wait=any`` or ``wait=object`` options to
   ``TaskGroup()``.

.. attribute:: TaskGroup.result

   The result of the first task that completed. Access may raise an
   exception if the task exited with an exception.  The same as accessing
   ``TaskGroup.completed.result``.

.. attribute:: TaskGroup.exception

   The exception raised by the first task that completed (if any).
   The same as accessing ``TaskGroup.completed.exception``.

.. attribute:: TaskGroup.results

   A list of all results returned by tasks created in the group,
   ordered by task id. May raise an exception if one of the tasks
   exited with an exception.  Typically used with the ``wait=all`` option
   to ``TaskGroup()``. 

.. attribute:: TaskGroup.exceptions

   A list of all exceptions raised by tasks managed by the group.

.. attribute:: TaskGroup.tasks

   A list of all tasks actively tracked by the group. Can be useful in
   determining task status after a task group has been joined.  Does
   not include tasks where the ``Task.join()`` method has already been
   called.

The preferred way to use a ``TaskGroup`` is as a context manager.  When
used in this manner, all tasks are guanteeed to be terminated/cancelled
upon block exit.  Here are a few common usage patterns::

    # Spawn multiple tasks and collect all of their results
    async with TaskGroup(wait=all) as g:
        await g.spawn(coro1)
        await g.spawn(coro2)
        await g.spawn(coro3)
    print('Results:', g.results)

    # Spawn multiple tasks and collect the result of the first one
    # that completes--cancelling other tasks
    async with TaskGroup(wait=any) as g:
        await g.spawn(coro1)
        await g.spawn(coro2)
        await g.spawn(coro3)
    print('Result:', g.result)

    # Spawn multiple tasks and collect their results as they complete
    async with TaskGroup() as g:
        await g.spawn(coro1)
        await g.spawn(coro2)
        await g.spawn(coro3)
        async for task in g:
            print(task, 'completed.', task.result)

In all of these examples, access to the ``result`` or ``results`` attribute
may raise an exception if a task failed for some reason. 

If ann exception is raised inside the task group context, all managed
tasks are cancelled and the exception is propagated.  For example::

    try:
        async with TaskGroup() as g:
            t1 = await g.spawn(func1)
            t2 = await g.spawn(func2)
            t3 = await g.spawn(func3)
            raise RuntimeError()
    except RuntimeError:
        # All launched tasks will have terminated or been cancelled here
        assert t1.terminated
        assert t2.terminated
        assert t3.terminated

This behavior also applies to timeouts.  For example::

    try:
        async with timeout_after(10):
            async with TaskGroup() as g:
                t1 = await g.spawn(func1)
                t2 = await g.spawn(func2)
                t3 = await g.spawn(func3)
            # All tasks cancelled here on timeout

    except TaskTimeout:
        # All launched tasks will have terminated or been cancelled
        assert t1.terminated
        assert t2.terminated
        assert t3.terminated

In this case, the timeout exception is only raised in the code that created
the task group. Child tasks are still cancelled using the ``cancel()`` 
method and would receive a ``TaskCancelled`` exception.

Time
----

.. asyncfunction:: sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, the
   kernel switches to the next task (if any). Returns the current clock value.

.. asyncfunction:: wake_at(clock)

   Sleep until the monotonic clock reaches the given absolute clock
   value.  Returns the value of the monotonic clock at the time the
   task awakes.  

.. asyncfunction:: clock()

   Returns the current value of the monotonic clock.   This is often used in
   conjunction with the ``wake_at()`` function (you'd use this to get
   an base clock value).

Timeouts
--------
Any blocking operation can be cancelled by a timeout.

.. asyncfunction:: timeout_after(seconds, corofunc=None, *args)

   Execute a coroutine and return its result. If no result is returned
   before *seconds* have elapsed, a :py:exc:`curio.TaskTimeout`
   exception is raised.  If *corofunc* is ``None``, the function 
   returns an asynchronous context manager that applies a timeout
   to a block of statements.

.. asyncfunction:: timeout_at(deadline, corofunc=None, *args)

   The same as :func:`timeout_after` except that the deadline time is
   given as an absolute clock time.  Use the :func:`clock` function to
   get a base time for computing a deadline.

Every call to ``timeout_after()`` should have a matching exception handler
to catch the resulting timeout. For example::

    try:
        result = await timeout_after(10, coro, arg1, arg2)
    except TaskTimeout: 
        ...

    # Alternative (context-manager)
    try:
        async with timeout_after(10):
            result = coro(arg1, arg2)
            ...
    except TaskTimeout:
        ...

When timeout operations are nested, the resulting ``TaskTimeout``
exception is paired to the matching ``timeout_after()`` operation that
produced it.  Consider this subtle example::

    async def main():
        try:
            async with timeout_after(1):        # Expires first
                try:
                    async with timeout_after(5):    
                        await sleep(1000)
                except TaskTimeout:             # (a) Does NOT match
                    print("Inner timeout")     
        except TaskTimeout:                     # (b) Matches!
            print("Outer timeout")

    run(main)

If you run this, you will see output of "Outer timeout" from the
exception handler at (b). This is because the outer timeout is the one
that expired.  The exception handler at (a) does not match because at
that point, the exception being reported is
:py:exc:`curio.TimeoutCancellationError`.  This exception indicates
that a timeout/cancellation has occurred somewhere, but that it is NOT
due to the inner-most timeout.

If a nested ``timeout_after()`` is used without a matching except
clause, a timeout might get reported as a
:py:exc:`curio.UncaughtTimeoutError` exception.  Remember that all
timeouts should have a matching exception handler--even if nested.

If you don't care about exception handling, you can also use the following
functions:

.. asyncfunction:: ignore_after(seconds, corofunc=None, *args, timeout_result=None)

   Executes a coroutine and returns its result. If *seconds* elapse, the
   operation is cancelled with a :py:exc:`curio.TaskTimeout` exception, but
   the exception is discarded and the value of *timeout_result* is returned.
   If *corofunc* is ``None``, returns an asynchronous context manager that 
   applies a timeout to a block of statements.  For this case, the resulting
   context manager object has an ``expired`` attribute set to ``True`` if
   time expired.

.. asyncfunction:: ignore_at(deadline, corofunc=None, *args)

   The same as :func:`ignore_after` except that the deadline time is
   given as an absolute clock time. 

Here are some examples::

    result = await ignore_after(5, coro, args)
    if result is None:
        # Timeout occurred (if you care)
        ...

    # Execute multiple statements with a 5 second timeout
    async with ignore_after(5) as s:
        await coro1(args)
        await coro2(args)

    if s.expired:
        # Timeout occurred
        ...

The ``ignore_*`` functions are just a convenience layer to simplify exception
handling. All of the timeout-related functions can be composed and layered
together in any configuration and it should still work.

Cancellation Control
--------------------

Sometimes it is necessary to disabled cancellation on critical operations. The
following functions can control this::

.. function:: disable_cancellation(corofunc=None, *args)

   Disables the delivery of cancellation-related exceptions while
   executing *corofunc*.  *args* are arguments supplied to *corofunc*.
   The result of *corofunc* is returned.  Any pending cancellation
   will be delivered to the first-blocking operation that is performed
   once cancellations are reenabled.  If *corofunc* is ``None`` a
   context manager is returned that can be used to shield a block of
   statements from cancellation.

.. asyncfunction:: check_cancellation(exc=None)

   Explicitly check if a cancellation is pending for the calling task.  If
   cancellation is enabled, any pending exception is raised
   immediately.  If cancellation is disabled, it returns the pending
   cancellation exception instance (if any) or ``None``.  If ``exc``
   is supplied and it matches the type of the pending exception, the
   exception is returned and any pending cancellation exception is
   cleared.

.. asyncfunction:: set_cancellation(exc)

   Set the pending cancellation exception for the calling task to ``exc``.
   If cancellation is enabled, it will be raised immediately on the next
   blocking operation.  Returns any previously set, but pending cancellation
   exception.

A common use of these functions is to more precisely control cancellation
points. Here is an example that shows a common use case::

    async def coro():
        async with disable_cancellation():
            while True:
                await coro1()
                await coro2()
                if await check_cancellation():
                    break   # Bail out!

        await check_cancellation()  # Cancellation (if any) delivered here

If you only need to shield a single operation, you can write statements like this::

    async def coro():
        ...
        await disable_cancellation(some_operation, x, y, z)
        ...

It is not possible for a function executing inside a block where cancellation has been
disabled to reenable it.

Synchronization Primitives
--------------------------
.. currentmodule:: None

The following synchronization primitives are available. Their behavior
is identical to their equivalents in the :mod:`threading` module.  None
of these primitives are safe to use with threads created by the
built-in :mod:`threading` module. 

.. class:: Event()

   An event object.

:class:`Event` instances support the following methods:

.. method:: Event.is_set()

   Return ``True`` if the event is set.

.. method:: Event.clear()

   Clear the event value.

.. asyncmethod:: Event.wait()

   Wait for the event.

.. asyncmethod:: Event.set()

   Set the event. Wake all waiting tasks (if any).

Curio provides ``Lock``, ``RLock``, ``Semaphore`` classes that allow for mutual exclusion and
inter-task coordination. 

.. class:: Lock()

   This class provides a mutex lock.  It can only be used in tasks. It is not thread safe.

.. class:: RLock()

   A recursive mutual-exclusion lock that can be acquired multiple times within the 
   same task.

.. class:: Semaphore(value=1)

   Create a semaphore instance.  Semaphores are based on a counter.  ``acquire()`` and ``release()``
   operations decrement and increment the counter respectively.  If the counter is 0, 
   ``acquire()`` operations block until the value is incremented by another task.  The ``value`` 
   attribute of a semaphore is a read-only property holding the current value of the internal 
   counter.

Instances of any of the above lock classes support the following methods:

.. asyncmethod:: Lock.acquire()

   Acquire the lock.

.. asyncmethod:: Lock.release()

   Release the lock.

.. method:: Lock.locked()

   Return ``True`` if the lock is currently held.

The preferred way to use a Lock is as an asynchronous context manager. For example::

    import curio
    lock = curio.Lock()

    async def sometask():
        async with lock:
            print("Have the lock")
            ...

The following :class:`Condition` class is used to implement inter-task signaling:

.. class:: Condition(lock=None)

   Condition variable.  *lock* is the underlying lock to use. If none is provided, then
   a :class:`Lock` object is used.

:class:`Condition` objects support the following methods:

.. method:: Condition.locked()

   Return ``True`` if the condition variable is locked.

.. asyncmethod:: Condition.acquire()

   Acquire the condition variable lock.

.. asyncmethod:: Condition.release()

   Release the condition variable lock.

.. asyncmethod:: Condition.wait()

   Wait on the condition variable. This releases the underlying lock.

.. asyncmethod:: Condition.wait_for(predicate)

   Wait on the condition variable until a supplied predicate function returns ``True``. *predicate* is
   a callable that takes no arguments.

.. asyncmethod:: notify(n=1)

   Notify one or more tasks, causing them to wake from the
   :meth:`Condition.wait` method.

.. asyncmethod:: notify_all()

   Notify all tasks waiting on the condition.

Proper use of a condition variable is tricky. The following example shows how to implement a
produce-consumer problem::

    import curio
    from collections import deque

    items = deque()
    async def consumer(cond):
        while True:
            async with cond:
                while not items:         # (a) 
                    await cond.wait()    # Wait for items
                item = items.popleft()
            print('Got', item)

     async def producer(cond):
         for n in range(10):
              async with cond:
                  items.append(n)
                  await cond.notify()
              await curio.sleep(1)

     async def main():
         cond = curio.Condition()
         await curio.spawn(producer(cond))
         await curio.spawn(consumer(cond))

     curio.run(main())

In this code, it is critically important that the ``wait()`` and
``notify()`` operations take place in a block where the condition
variable has been properly acquired.  Also, the ``while``-loop at (a)
is not a typo.  Condition variables are often used to "signal" that
some condition has become true, but it is standard practice to re-test
the condition before proceding (it might be the case that a
condition was only briefly transient and by the time a notified task
awakes, the condition no longer holds).  

Queues
------

To communicate between tasks, you can use a :class:`Queue`.  

.. class:: Queue(maxsize=0)

   Creates a queue with a maximum number of elements in *maxsize*.  If not
   specified, the queue can hold an unlimited number of items.

A :class:`Queue` instance supports the following methods:

.. method:: Queue.empty()

   Returns ``True`` if the queue is empty.

.. method:: Queue.full()

   Returns ``True`` if the queue is full.

.. method:: Queue.qsize()

   Return the number of items currently in the queue.

.. asyncmethod:: Queue.get()

   Returns an item from the queue.  Blocks if no items are available.

.. asyncmethod:: Queue.put(item)

   Puts an item on the queue. Blocks if the queue is at capacity.

.. asyncmethod:: Queue.join()

   Wait for all of the elements put onto a queue to be processed. Consumers
   must call :meth:`Queue.task_done` to indicate completion.

.. asyncmethod:: Queue.task_done()

   Indicate that processing has finished for an item.  If all items have
   been processed and there are tasks waiting on :meth:`Queue.join` they
   will be awakened.

Here is an example of using queues in a producer-consumer problem::

    import curio

    async def producer(queue):
        for n in range(10):
            await queue.put(n)
        await queue.join()
        print('Producer done')

    async def consumer(queue):
        while True:
            item = await queue.get()
            print('Consumer got', item)
            await queue.task_done()

    async def main():
        q = curio.Queue()
        prod_task = await curio.spawn(producer(q))
        cons_task = await curio.spawn(consumer(q))
        await prod_task.join()
        await cons_task.cancel()

    curio.run(main())

The following variants of the basic :class:`Queue` class are also provided:

.. class:: PriorityQueue(maxsize=0)

   Creates a priority queue with a maximum number of elements in *maxsize*.
   The priority of items is determined by standard relational operators
   such as ``<`` and ``<=``.   Lowest priority items are returned first.

.. class:: LifoQueue(maxsize=0)

   A queue with "Last In First Out" retrieving policy. In other words, a stack.


Universal Synchronizaton
------------------------

Sometimes it is necessary to synchronize with threads and foreign event loops.
For this, Curio provides the following queue and event classes.

.. class: UniversalQueue(maxsize=0, withfd=False)

   A queue that can be safely used from both Curio tasks and threads.  
   The same programming API is used for both, but ``await`` is
   required for asynchronous operations.  When the queue is no longer
   in use, the ``shutdown()`` method should be called to terminate
   an internal helper-task.   The ``withfd`` option specifies whether
   or not the queue should optionally set up an I/O loopback that
   allows it to be polled by a foreign event loop.  When ``withfd`` is
   ``True``, adding something to the queue writes a byte of data to the
   I/O loopback.  

Here is an example of a producer-consumer problem with a ``UniversalQueue``::

    from curio import run, UniversalQueue, spawn, run_in_thread

    import time
    import threading

    # An async task
    async def consumer(q):
        print('Consumer starting')
        while True:
            item = await q.get()
            if item is None:
                break
            print('Got:', item)
            await q.task_done()
        print('Consumer done')

    # A threaded producer
    def producer(q):
        for i in range(10):
            q.put(i)
            time.sleep(1)
        q.join()
        print('Producer done')

    async def main():
        q = UniversalQueue()
        t1 = await spawn(consumer(q))
        t2 = threading.Thread(target=producer, args=(q,))
        t2.start()
        await run_in_thread(t2.join)
        await q.put(None)
        await t1.join()
        await q.shutdown()

    run(main())

In this code, the ``consumer()`` is a Curio task and ``producer()`` is a thread.

Blocking Operations and External Work
-------------------------------------
.. module:: curio.workers

Sometimes you need to perform work that takes a long time to complete
or otherwise blocks the progress of other tasks. This includes
CPU-intensive calculations and blocking operations carried out by
foreign libraries.  Use the following functions to do that:

.. asyncfunction:: run_in_process(callable, *args)

   Run ``callable(*args)`` in a separate process and returns the
   result.  If cancelled, the underlying worker process is immediately
   cancelled by a ``SIGTERM`` signal.  The given callable executes in
   an entirely independent Python interpreter and there is no shared
   global state. The separate process is launched using the "spawn"
   method of the ``multiprocessing`` module.

.. asyncfunction:: run_in_thread(callable, *args)

   Run ``callable(*args)`` in a separate thread and return
   the result.  If the calling task is cancelled, the underlying
   worker thread (if started) is set aside and sent a termination
   request.  However, since there is no underlying mechanism to
   forcefully kill threads, the thread won't recognize the termination
   request until it runs the requested work to completion.  It's
   important to note that a cancellation won't block other tasks
   from using threads. Instead, cancellation produces a kind of
   "zombie thread" that executes the requested work, discards the
   result, and then disappears.  For reliability, work submitted to
   threads should have a timeout or some other mechanism that
   puts a bound on execution time.

.. asyncfunction:: block_in_thread(callable, *args)

   The same as ``run_in_thread()``, but guarantees that only
   one background thread is used for each unique callable
   regardless of how many tasks simultaneously try to
   carry out the same operation at once.  Only use this function if there is
   an expectation that the provided callable is going to 
   block for an undetermined amount of time and that there 
   might be a large amount of contention from multiple tasks on the same
   resource.  The primary use is on waiting operations involving
   foreign locks and queues.  For example, if you launched a hundred
   Curio tasks and they all decided to block on a shared thread queue,
   using this would be much more efficient than ``run_in_thread()``.

.. asyncfunction:: run_in_executor(exc, callable, *args)

   Run ``callable(*args)`` callable in a user-supplied
   executor and returns the result. *exc* is an executor from the
   :py:mod:`concurrent.futures` module in the standard library.  This
   executor is expected to implement a
   :meth:`~concurrent.futures.Executor.submit` method that executes
   the given callable and returns a
   :class:`~concurrent.futures.Future` instance for collecting its
   result.


When performing external work, it's almost always better to use the
:func:`run_in_process` and :func:`run_in_thread` functions instead
of :func:`run_in_executor`.  These functions have no external library
dependencies, have less communication overhead, and more
predictable cancellation semantics.

The following values in :mod:`curio.workers` define how many
worker threads and processes are used.  If you are going to
change these values, do it before any tasks are executed.

.. data:: MAX_WORKER_THREADS

   Specifies the maximum number of threads used by a single kernel
   using the :func:`run_in_thread` function.  Default value is 64.

.. data:: MAX_WORKER_PROCESSES

   Specifies the maximum number of processes used by a single kernel
   using the :func:`run_in_process` function. Default value is the
   number of CPUs on the host system.

I/O Classes
-----------

.. module:: curio.io

I/O in Curio is managed by a collection of classes in :mod:`curio.io`.
These classes act as asynchronous proxies around sockets, streams, and
ordinary files.  The programming interface is meant to be the same as
in normal synchronous Python code.

Socket
^^^^^^

The :class:`Socket` class wraps an existing socket-like object as might 
be created by the built in :mod:`socket` module.

.. class:: Socket(sockobj)

   Creates a proxy around an existing socket *sockobj*.  *sockobj* is 
   put in non-blocking mode when wrapped. *sockobj* is not closed unless
   the created ``Socket`` instance is explicitly closed or used as a 
   context manager.

The following methods are redefined on :class:`Socket` objects to be
compatible with coroutines.  Any socket method not listed here will be
delegated directly to the underlying socket as an ordinary method.

.. asyncmethod:: Socket.recv(maxbytes, flags=0)

   Receive up to *maxbytes* of data.

.. asyncmethod:: Socket.recv_into(buffer, nbytes=0, flags=0)

   Receive up to *nbytes* of data into a buffer object.

.. asyncmethod:: Socket.recvfrom(maxsize, flags=0)

   Receive up to *maxbytes* of data.  Returns a tuple `(data, client_address)`.

.. asyncmethod:: Socket.recvfrom_into(buffer, nbytes=0, flags=0)

   Receive up to *nbytes* of data into a buffer object.

.. asyncmethod:: Socket.recvmsg(bufsize, ancbufsize=0, flags=0)

   Receive normal and ancillary data.

.. asyncmethod:: Socket.recvmsg_into(buffers, ancbufsize=0, flags=0)

   Receive normal and ancillary data.

.. asyncmethod:: Socket.send(data, flags=0)

   Send data.  Returns the number of bytes of data actually sent (which may be
   less than provided in *data*).

.. asyncmethod:: Socket.sendall(data, flags=0)

   Send all of the data in *data*. If cancelled, the ``bytes_sent`` attribute of the
   resulting exception contains the actual number of bytes sent.

.. asyncmethod:: Socket.sendto(data, address)
.. asyncmethod:: Socket.sendto(data, flags, address)

   Send data to the specified address.

.. asyncmethod:: Socket.sendmsg(buffers, ancdata=(), flags=0, address=None)

   Send normal and ancillary data to the socket.

.. asyncmethod:: Socket.accept()

   Wait for a new connection.  Returns a tuple `(sock, address)` where `sock`
   is an instance of ``Socket``.

.. asyncmethod:: Socket.connect(address)

   Make a connection.   

.. asyncmethod:: Socket.connect_ex(address)

   Make a connection and return an error code instead of raising an exception.

.. asyncmethod:: Socket.close()

   Close the connection.  This method is not called on garbage
   collection.  Warning: You know that scene from Star Wars where
   they're taking a fun joy-ride through hyperspace, there's a sudden
   disturbance in the force, and they emerge into the middle of an
   asteroid debris field?  That's kind of what it will be like if a task
   chooses to use a giant "death laser" to close a socket being
   used by another task.  Only instead of it being a disturbance in
   the force, it will be more like dropping a huge amount of acid and
   having your debugger emerge from the trip into the middle of that
   scene from The Matrix Reloaded.  Yeah, THAT scene.  Don't do that.
   Consider using `Socket.shutdown()` or cancelling a task instead.

.. asyncmethod:: Socket.shutdown(how)

   Shutdown the socket.  *how* indicates which end of the connection
   to shutdown and is one of ``SHUT_RD``, ``SHUT_WR``, or ``SHUT_RDWR``.
   
.. asyncmethod:: do_handshake()

   Perform an SSL client handshake. The underlying socket must have already
   be wrapped by SSL using the :mod:`curio.ssl` module.

.. method:: Socket.makefile(mode, buffering=0)

   Make a file-like object that wraps the socket.  The resulting file
   object is a :class:`curio.io.FileStream` instance that supports
   non-blocking I/O.  *mode* specifies the file mode which must be one
   of ``'rb'`` or ``'wb'``.  *buffering* specifies the buffering
   behavior. By default unbuffered I/O is used.  Note: It is not currently
   possible to create a stream with Unicode text encoding/decoding applied to it
   so those options are not available.   If you are trying to put a file-like
   interface on a socket, it is usually better to use the :meth:`Socket.as_stream`
   method below.  Not supported on Windows.

.. method:: Socket.as_stream()

   Wrap the socket as a stream using :class:`curio.io.SocketStream`. The
   result is a file-like object that can be used for both reading and
   writing on the socket.

.. method:: Socket.blocking()

   A context manager that temporarily places the socket into blocking mode and
   returns the raw socket object used internally.  This can be used if you need
   to pass the socket to existing synchronous code.

:class:`Socket` objects may be used as an asynchronous context manager
which cause the underlying socket to be closed when done. For
example::

    async with sock:
        # Use the socket
        ...
    # socket closed here

Streams
^^^^^^^

A stream is an asynchronous file-like object that wraps around an existing
I/O primitive that natively implements proper non-blocking I/O.
Curio implements two basic classes:

.. class:: FileStream(fileobj)

   Create a file-like wrapper around an existing file as might be
   created by the built-in ``open()`` function or
   ``socket.makefile()``.  *fileobj* must be in in binary mode and
   must support non-blocking I/O.  The file is placed into
   non-blocking mode using ``os.set_blocking(fileobj.fileno())``.
   *fileobj* is not closed unless the resulting instance is explicitly
   closed or used as a context manager.  Not supported on Windows.

.. class:: SocketStream(sockobj)

   Create a file-like wrapper around a socket.  *sockobj* is an
   existing socket-like object.  The socket is put into non-blocking mode.
   *sockobj* is not closed unless the resulting instance is explicitly
   closed or used as a context manager.

Instances of either class implement the following methods:

.. asyncmethod:: Stream.read(maxbytes=-1)

   Read up to *maxbytes* of data on the file. If omitted, reads as
   much data as is currently available and returns it.

.. asyncmethod:: Stream.readall()

   Return all of the data that's available on a file up until an EOF is read.

.. asyncmethod:: Stream.read_exactly(n)

   Read exactly n bytes of data, waiting for all data to arrive if necessary.

.. asyncmethod:: Stream.readline()

   Read a single line of data from a file.  

.. asyncmethod:: Stream.readlines()

   Read all of the lines from a file. If cancelled, the ``lines_read`` attribute of
   the resulting exception contains all of the lines that were read so far.

.. asyncmethod:: Stream.write(bytes)

   Write all of the data in *bytes* to the file.

.. asyncmethod:: Stream.writelines(lines)

   Writes all of the lines in *lines* to the file.  If cancelled, the ``bytes_written``
   attribute of the exception contains the total bytes written so far.

.. asyncmethod:: Stream.flush()

   Flush any unwritten data from buffers to the file.

.. asyncmethod:: Stream.close()

   Flush any unwritten data and close the file.  This method is not
   called on garbage collection.

.. method:: Stream.blocking()

   A context manager that temporarily places the stream into blocking mode and
   returns the raw file object used internally.  This can be used if you need
   to pass the file to existing synchronous code.  Note: for ``SocketStream``
   this creates a file using  ``open(sock.fileno(), 'rb+',
   closefd=False)`` which is not supported on Windows.

Other methods (e.g., ``tell()``, ``seek()``, ``setsockopt()``, etc.) are available
if underlying ``fileobj`` or ``sockobj`` provides them.

A ``Stream`` may be used as an asynchronous context manager.  For example::

    async with stream:
        #  Use the stream object
        ...
    # stream closed here

Files
^^^^^

.. module:: curio.file

One problem with coroutines concerns the use of file-like objects that
can't properly be used in non-blocking mode.  A common example is
files on the normal file system that were opened with the built-in
``open()`` function.  Internally, the operating system might have to
access a disk drive or perform networking of its own.  Either way, the
operation might take a long time to complete and while it does, all of
Curio will be blocked. You really don't want that--especially if the
system is under heavy load.

The :mod:`curio.file` module provides an asynchronous compatible
replacement for the built-in ``open()`` function and associated file
objects, should you want to read and write traditional files on the
filesystem. The underlying implementation avoids blocking.  How this
is accomplished is an implementation detail (although threads are used
in the initial version).

.. function:: aopen(*args, **kwargs)

   Creates a :class:`curio.file.AsyncFile` wrapper around a traditional file object as
   returned by Python's builtin ``open()`` function.   The arguments are exactly the
   same as for ``open()``.  The returned file object must be used as an asynchronous
   context manager.

.. class:: AsyncFile(fileobj)

   This class represents an asynchronous file as returned by the ``aopen()``
   function.  Normally, instances are created by the ``aopen()`` function.
   However, it can be wrapped around an already-existing file object that
   was opened using the built-in ``open()`` function.

The following methods are redefined on :class:`AsyncFile` objects to be
compatible with coroutines.  Any method not listed here will be
delegated directly to the underlying file.  These methods take the same arguments
as the underlying file object.  Be aware that not all of these methods are
available on all kinds of files (e.g., ``read1()``, ``readinto()`` and similar
methods are only available in binary-mode files).

.. asyncmethod:: AsyncFile.read(*args, **kwargs)
.. asyncmethod:: AsyncFile.read1(*args, **kwargs)
.. asyncmethod:: AsyncFile.readline(*args, **kwargs)
.. asyncmethod:: AsyncFile.readlines(*args, **kwargs)
.. asyncmethod:: AsyncFile.readinto(*args, **kwargs)
.. asyncmethod:: AsyncFile.readinto1(*args, **kwargs)
.. asyncmethod:: AsyncFile.write(*args, **kwargs)
.. asyncmethod:: AsyncFile.writelines(*args, **kwargs)
.. asyncmethod:: AsyncFile.truncate(*args, **kwargs)
.. asyncmethod:: AsyncFile.seek(*args, **kwargs)
.. asyncmethod:: AsyncFile.tell(*args, **kwargs)
.. asyncmethod:: AsyncFile.flush()
.. asyncmethod:: AsyncFile.close()

The preferred way to use an :class:`AsyncFile` object is as an asynchronous context manager.
For example::

    async with aopen(filename) as f:
        # Use the file
        data = await f.read()

:class:`AsyncFile` objects may also be used with asynchronous iteration.
For example::

    async with open(filename) as f:
        async for line in f:
            ...

:class:`AsyncFile` objects are intentionally incompatible with code
that uses files in a synchronous manner.  Partly, this is to help
avoid unintentional errors in your program where blocking might
occur without you realizing it.  If you know what you're doing and you
need to access the underlying file in synchronous code, use the
`blocking()` context manager like this::

    async with aopen(filename) as f:
        ...
        # Pass to synchronous code (danger: might block)
        with f.blocking() as sync_f:
             # Use synchronous I/O operations
             data = sync_f.read()
             ...

At first glance, the API to streams and files might look identical.  The
difference concerns internal implementation.  A stream works natively 
with non-blocking I/O.  An ``AsyncFile`` uses a combination of threads and
synchronous calls to provide an async-compatible API.   Given a choice,
you should use streams.  However, some systems don't provide non-blocking
implementations of certain system calls. In those cases, an ``AsyncFile`` is a
fallback.

Networking
----------

Curio provides a number of submodules for different kinds of network
programming.

High Level Networking
^^^^^^^^^^^^^^^^^^^^^

.. currentmodule:: curio

The following functions are use to make network connections and implement
socket-based servers.

.. asyncfunction:: open_connection(host, port, *, ssl=None, source_addr=None, server_hostname=None, alpn_protocols=None)

   Creates an outgoing connection to a server at *host* and
   *port*. This connection is made using the
   :py:func:`socket.create_connection` function and might be IPv4 or
   IPv6 depending on the network configuration (although you're not
   supposed to worry about it).  *ssl* specifies whether or not SSL
   should be used.  *ssl* can be ``True`` or an instance of
   :class:`curio.ssl.SSLContext`.  *source_addr* specifies the source
   address to use on the socket.  *server_hostname* specifies the
   hostname to check against when making SSL connections.  It is
   highly advised that this be supplied to avoid man-in-the-middle
   attacks.  *alpn_protocols* specifies a list of protocol names
   for use with the TLS ALPN extension (RFC7301).  A typical value
   might be ``['h2', 'http/1.1']`` for negotiating either a HTTP/2
   or HTTP/1.1 connection.

.. asyncfunction:: open_unix_connection(path, *, ssl=None, server_hostname=None, alpn_protocols=None)

   Creates a connection to a Unix domain socket with optional SSL applied.

.. asyncfunction:: tcp_server(host, port, client_connected_task, *, family=AF_INET, backlog=100, ssl=None, reuse_address=True, reuse_port=False)

   Runs a server for receiving TCP connections on
   a given host and port.  *client_connected_task* is a coroutine that
   is to be called to handle each connection.  Family specifies the
   address family and is either :data:`socket.AF_INET` or
   :data:`socket.AF_INET6`.  *backlog* is the argument to the
   :py:meth:`socket.socket.listen` method.  *ssl* specifies an
   :class:`curio.ssl.SSLContext` instance to use. *reuse_address*
   specifies whether to reuse a previously used port. *reuse_port*
   specifies whether to use the ``SO_REUSEPORT`` socket option
   prior to binding. 

.. asyncfunction:: unix_server(path, client_connected_task, *, backlog=100, ssl=None)

   Runs a Unix domain server on a given
   path. *client_connected_task* is a coroutine to execute on each
   connection. *backlog* is the argument given to the
   :py:meth:`socket.socket.listen` method.  *ssl* is an optional
   :class:`curio.ssl.SSLContext` to use if setting up an SSL
   connection.

.. asyncfunction:: run_server(sock, client_connected_task, ssl=None)

   Runs a server on a given socket.  *sock* is a socket already 
   configured to receive incoming connections.  *client_connected_task* and
   *ssl* have the same meaning as for the ``tcp_server()`` and ``unix_server()``
   functions.  If you need to perform some kind of special socket
   setup, not possible with the normal ``tcp_server()`` function, you can
   create the underlying socket yourself and then call this function
   to run a server on it.

.. function:: tcp_server_socket(host, port, family=AF_INET, backlog=100, reuse_address=True, reuse_port=False)

   Creates and returns a TCP socket. Arguments are the same as for the
   ``tcp_server()`` function.  The socket is suitable for use with other
   async operations as well as the ``run_server()`` function.

.. function:: unix_server_socket(path, backlog=100)

   Creates and returns a Unix socket. Arguments are the same as for the
   ``unix_server()`` function.  The socket is suitable for use with other
   async operations as well as the ``run_server()`` function.


Message Passing and Channels
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. module:: curio.channel

Curio provides a :class:`Channel` class that can be used to perform message
passing between interpreters running in separate processes.  

.. class:: Channel(address, family=socket.AF_INET)

   Represents a communications endpoint for message passing.  
   *address* is the address and *family* is the protocol
   family.

The following methods are used to establish a connection on a :class:`Channel` instance.

.. asyncmethod:: Channel.accept(*, authkey=None)

   Wait for an incoming connection.  *authkey* is an optional authentication
   key that can be used to authenticate the client.  Authentication involves
   computing an HMAC-based cryptographic digest. The key itself is not 
   transmitted.  Returns an :class:`Connection` instance.

.. asyncmethod:: Channel.connect(*, authkey=None)

   Make an outgoing connection. *authkey* is an optional authentication key.
   Returns a :class:`Connection` instance.

.. method:: Channel.bind()

   Performs the address binding step of the ``accept()`` method and returns.
   Can use this if you want the host operating system to assign a port
   number for you.  For example, you can supply an initial address
   of ``('localhost', socket.INADDR_ANY)`` and call ``bind()``. Afterwards,
   the ``address`` attribute of the ``Channel`` instance contains
   the assigned address.

.. asyncmethod:: Channel.close()

   Close the channel.

The ``connect()`` and ``accept()`` methods of :class:`Channel` instances return a
:class:`Connection` instance.

.. class:: Connection(reader, writer)

   Represents a connection on which message passing of Python objects is
   supported.  *reader* and *writer* are Curio I/O streams on which reading 
   and writing are to take place (for example, instances of ``SocketStream``
   or ``FileStream``).

Instances of :class:`Connection` support the following methods:

.. asyncmethod:: close()

   Close the connection by closing both the reader and writer streams.

.. asyncmethod:: recv()

   Receive a Python object. The received object is unserialized using the ``pickle`` module.

.. asyncmethod:: recv_bytes(maxlength=None)

   Receive a raw message of bytes.  *maxlength* specifies a maximum message size.
   By default messages may be of arbitrary size.

.. asyncmethod:: send(obj)

   Send a Python object.  The object must be compatible with the ``pickle`` module.

.. asyncmethod:: send_bytes(buf, offset=0, size=None)
   
   Send a buffer of bytes as a single message.  *offset* and *size* specify
   an optional byte offset and size into the underlying memory buffer. 

.. asyncmethod:: authenticate_server(authkey)

   Authenticate the connection for a server.

.. asyncmethod:: authenticate_client(authkey)

   Authenticate the connection for a client.

A :class:`Connection` instance may also be used as a context manager.

Here is an example of a producer program using channels::

    # producer.py
    from curio import Channel, run

    async def producer(ch):
        c = await ch.accept(authkey=b'peekaboo')
        for i in range(10):
            await c.send(i)
        await c.send(None)   # Sentinel

    if __name__ == '__main__':
        ch = Channel(('localhost', 30000))
        run(producer(ch))

Here is an example of a corresponding consumer program using a channel::

    # consumer.py
    from curio import Channel, run

    async def consumer(ch):
        c = await ch.connect(authkey=b'peekaboo')
        while True:
            msg = await c.recv()
            if msg is None:
                break
            print('Got:', msg)

    if __name__ == '__main__':
        ch = Channel(('localhost', 30000))
        run(consumer(ch))

socket module
^^^^^^^^^^^^^

.. module:: curio.socket

The :mod:`curio.socket` module provides a wrapper around the built-in
:mod:`socket` module--allowing it to be used as a stand-in in
Curio-related code.  The module provides exactly the same
functionality except that certain operations have been replaced by
asynchronous equivalents.

.. function:: socket(family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None)

   Creates a :class:`curio.io.Socket` wrapper the around :class:`socket` objects created in the built-in :mod:`socket`
   module.  The arguments for construction are identical and have the same meaning.
   The resulting :class:`socket` instance is set in non-blocking mode.

The following module-level functions have been modified so that the returned socket
objects are compatible with Curio:

.. function:: socketpair(family=AF_UNIX, type=SOCK_STREAM, proto=0)
.. function:: fromfd(fd, family, type, proto=0)
.. function:: create_connection(address, source_address)

The following module-level functions have been redefined as coroutines so that they
don't block the kernel when interacting with DNS.  This is accomplished through
the use of threads.

.. asyncfunction:: getaddrinfo(host, port, family=0, type=0, proto=0, flags=0)
.. asyncfunction:: getfqdn(name)
.. asyncfunction:: gethostbyname(hostname)
.. asyncfunction:: gethostbyname_ex(hostname)
.. asyncfunction:: gethostname()
.. asyncfunction:: gethostbyaddr(ip_address)
.. asyncfunction:: getnameinfo(sockaddr, flags)


ssl module
^^^^^^^^^^

.. module:: curio.ssl

The :mod:`curio.ssl` module provides Curio-compatible functions for creating an SSL
layer around Curio sockets.  The following functions are redefined (and have the same
calling signature as their counterparts in the standard :mod:`ssl` module:

.. asyncfunction:: wrap_socket(*args, **kwargs)

.. asyncfunction:: get_server_certificate(*args, **kwargs)

.. function:: create_default_context(*args, **kwargs)

.. class:: SSLContext

   A redefined and modified variant of :class:`ssl.SSLContext` so that the
   :meth:`wrap_socket` method returns a socket compatible with Curio.

Don't attempt to use the :mod:`curio.ssl` module without a careful read of Python's official documentation
at https://docs.python.org/3/library/ssl.html.

For the purposes of Curio, it is usually easier to apply SSL to a
connection using some of the high level network functions previously described.
For example, here's how you make an outgoing SSL connection::

    sock = await curio.open_connection('www.python.org', 443,
                                       ssl=True,
                                       server_hostname='www.python.org')

Here's how you might define a server that uses SSL::

    import curio
    from curio import ssl

    KEYFILE = "privkey_rsa"       # Private key
    CERTFILE = "certificate.crt"  # Server certificat

    async def handler(client, addr):
        ...

    if __name__ == '__main__':
        kernel = curio.Kernel()
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
        kernel.run(curio.tcp_server('', 10000, handler, ssl=ssl_context))


Subprocesses
------------
.. module:: curio.subprocess

The :mod:`curio.subprocess` module implements the same functionality as the built-in
:mod:`subprocess` module.

.. class:: Popen(*args, **kwargs)

   A wrapper around the :class:`subprocess.Popen` class.  The same arguments are
   accepted. On the resulting :class:`~subprocess.Popen` instance, the
   :attr:`~subprocess.Popen.stdin`, :attr:`~subprocess.Popen.stdout`, and
   :attr:`~subprocess.Popen.stderr` file attributes have been wrapped by the
   :class:`curio.io.FileStream` class. You can use these in an asynchronous
   context.

Here is an example of using :class:`Popen` to read streaming output off of a
subprocess with Curio::

    import curio
    from curio import subprocess

    async def main():
        p = subprocess.Popen(['ping', 'www.python.org'], stdout=subprocess.PIPE)
        async for line in p.stdout:
            print('Got:', line.decode('ascii'), end='')

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.add_task(main())
        kernel.run()

The following methods of :class:`Popen` have been replaced by asynchronous equivalents:

.. asyncmethod:: Popen.wait()

   Wait for a subprocess to exit.  Cancellation does not terminate the process.

.. asyncmethod:: Popen.communicate(input=b'')

   Communicate with the subprocess, sending the specified input on standard input.
   Returns a tuple ``(stdout, stderr)`` with the resulting output of standard output
   and standard error.  If cancelled, the resulting exception has ``stdout`` and
   ``stderr`` attributes that contain the output read prior to cancellation. 
   Cancellation does not terminate the underlying subprocess.

The following functions are also available.  They accept the same arguments as their
equivalents in the :mod:`subprocess` module:

.. asyncfunction:: run(args, stdin=None, input=None, stdout=None, stderr=None, shell=False, check=False)

   Run a command in a subprocess.  Returns a :class:`subprocess.CompletedProcess` instance.
   If cancelled, the underlying process is terminated using the process ``kill()`` method.
   The resulting exception will have ``stdout`` and ``stderr`` attributes containing
   output read prior to cancellation.

.. asyncfunction:: check_output(args, stdout=None, stderr=None, shell=False)

   Run a command in a subprocess and return the resulting output. Raises a
   :py:exc:`subprocess.CalledProcessError` exception if an error occurred.
   The behavior on cancellation is the same as for ``run()``. 

Asynchronous Threads
--------------------

If you need to perform a lot of synchronous operations, but still
interact with Curio, you might consider launching an asynchronous
thread. An asynchronous thread flips the whole world around--instead
of executing synchronous operations using ``run_in_thread()``, you
kick everything out to a thread and selectively perform the asynchronous
operations using a magic ``AWAIT()`` function. 

.. class:: AsyncThread(target, args=(), kwargs={}, daemon=True)

   Creates an asynchronous thread.  The arguments are the same as
   for the ``threading.Thread`` class.  ``target`` is a synchronous
   callable.  ``args`` and ``kwargs`` are its arguments. ``daemon``
   specifies if the thread runs in daemonic mode.

.. asyncmethod:: AsyncThread.start()

   Starts the asynchronous thread.

.. asyncmethod:: join()

   Waits for the thread to terminate, returning the callables final result.
   The final result is returned in the same manner as the usual ``Task.join()``
   method used on Curio tasks.

.. asyncmethod:: wait()
   
   Waits for the thread to terminate, but do not result any result.

.. attribute:: AsyncThread.result

   The result of the thread, if completed.  If accessed before the thread
   terminates, a ``RuntimeError`` exception is raised.  If the task crashed
   with an exception, that exception is reraised on access.
   
.. asyncmethod:: cancel()

   Cancels the asynchronous thread.  The behavior is the same as cancellation
   performed on Curio tasks.  Note: An asynchronous thread can only be cancelled
   when it performs blocking operations on asynchronous objects (e.g.,
   using ``AWAIT()``.

As a shortcut for creating an asynchronous thread, you can use ``spawn_thread()`` instead.

.. asyncfunction:: spawn_thread(func=None, *args, daemon=False)

   Launch an asynchronous thread that runs the callable ``func(*args)``.
   ``daemon`` specifies if the thread runs in daemonic mode.   This
   function may also be used as a context manager if ``func`` is ``None``.
   In that case, the body of the context manager executes in a separate
   thread. For the context manager case, the body is not allowed to perform
   any asynchronous operation involving ``async`` or ``await``.  However,
   the ``AWAIT()`` function may be used to delegate asynchronous operations
   back to Curio's main thread.

Within a thread, the following function can be used to execute a coroutine.

.. function:: AWAIT(coro)

   Execute a coroutine on behalf of an asynchronous thread.  The requested
   coroutine always executes in Curio's main execution thread.  The caller is
   blocked until it completes.  If used outside of an asynchronous thread,
   an ``AsyncOnlyError`` exception is raised.  If ``coro`` is not a 
   coroutine, it is returned unmodified.   The reason ``AWAIT`` is all-caps
   is to make it more easily heard when there are all of these coders yelling
   at you to just use pure async code instead of launching a thread. Also, 
   ``await`` is likely to be a reserved keyword in Python 3.7.

Here is a simple example of an asynchronous thread that reads data off a
Curio queue::

    from curio import run, Queue, sleep, CancelledError
    from curio.thread import spawn_thread, AWAIT

    def consumer(queue):
        try:
            while True:
                item = AWAIT(queue.get())
                print('Got:', item)
                AWAIT(queue.task_done())

        except CancelledError:
            print('Consumer goodbye!')
            raise

    async def main():
        q = Queue()
        t = await spawn_thread(consumer, q)

        for i in range(10):
            await q.put(i)
            await sleep(1)

        await q.join()
        await t.cancel()

    run(main())

Asynchronous threads can perform any combination of blocking operations
including those that might involve normal thread-related primitives such
as locks and queues.  These operations will block the thread itself, but
will not block the Curio kernel loop.  In a sense, this is the whole
point--if you run things in an async threads, the rest of Curio is
protected.   Asynchronous threads can be cancelled in the same manner
as normal Curio tasks.  However, the same rules apply--an asynchronous
thread can only be cancelled on blocking operations involving ``AWAIT()``.

A final curious thing about async threads is that the ``AWAIT()``
function is no-op if you don't give it a coroutine.  This means that
code, in many cases, can be made to be compatible with regular Python
threads.  For example, this code involving normal threads actually runs::

    from curio.thread import AWAIT
    from curio import CancelledError
    from threading import Thread
    from queue import Queue
    from time import sleep

    def consumer(queue):
        try:
            while True:
                item = AWAIT(queue.get())
                print('Got:', item)
                AWAIT(queue.task_done())

        except CancelledError:
            print('Consumer goodbye!')
            raise
 
    def main():
        q = Queue()
        t = Thread(target=consumer, args=(q,), daemon=True)
        t.start()

        for i in range(10):
            q.put(i)
            sleep(1)
        q.join()

    main()

In this code, ``consumer()`` is simply launched in a regular thread
with a regular thread queue.  The ``AWAIT()`` operations do
nothing--the queue operations aren't coroutines and their results
return unmodified.  Certain Curio features such as cancellation aren't
supported by normal threads so that would be ignored.  However, it's
interesting that you can write a kind of hybrid code that works in
both a threaded and asynchronous world.

Scheduler Activations
---------------------
.. module:: curio.activation

Each task in Curio goes through a life-cycle of creation, running,
suspension, and eventual termination.   These can be monitored by
external tools by defining classes that inherit from :class:`Activation`.

.. class:: Activation

   Base class for defining scheduler activations.

The following methods are executed as callback-functions by the kernel:

.. method:: activate(kernel)

   Executed once upon initialization of the Curio kernel. *kernel* is
   a reference to the ``Kernel`` instance.

.. method:: created(task)

   Called when a new task is created.  *task* is the newly created ``Task`` instance.

.. method:: running(task)

   Called immediately prior to the execution of a task.

.. method:: suspended(task)

   Called when a task has suspended execution.

.. method:: terminated(task)

   Called when a task has terminated execution. Note: the
   ``suspended()`` method is always called prior to a task being
   terminated.

As an example, here is a scheduler activation that monitors for long-execution times
and reports warnings::

    from curio.activation import Activation
    import time

    class LongBlock(Activation):
        def __init__(self, maxtime):
            self.maxtime = maxtime

        def running(self, task):
            self.start = time.time()
  
        def suspended(self, task):
            end = time.time()
            if end - self.start > self.maxtime:
                print(f'Long blocking in {task.name}: {end - self.start}')

Scheduler activations are registered when a ``Kernel`` is created or with the
top-level ``run()`` function::

    kern = Kernel(activations=[LongBlock(0.05)])
    with kern:
        kern.run(coro)

    # Alternative
    run(activations=[LongBlock(0.05)])

Asynchronous Metaprogramming
----------------------------
.. module:: curio.meta

The :mod:`curio.meta` module provides some functions that might be useful if
implementing more complex programs and APIs involving coroutines.

.. function:: curio_running():

   Return ``True`` if Curio is running in the current thread.

.. function:: iscoroutinefunction(func)

   True ``True`` if the supplied *func* is a coroutine function or is known
   to resolve into a coroutine.   Unlike a similar function in ``inspect``,
   this function knows about ``functools.partial()``, awaitable objects, 
   and async generators.

.. function:: instantiate_coroutine(corofunc, *args, **kwargs)

   Instantiate a coroutine from *corofunc*. If *corofunc* is already
   a coroutine object, it is returned unmodified.  If it's a coroutine
   function, it's executed within an async context using the given 
   arguments.  If it's not a coroutine, *corofunc* is called 
   with the given arguments with the expectation that whatever is
   returned will be a coroutine instance.

.. function:: from_coroutine(level=2)

   Returns ``True`` if the caller is calling function is being invoked
   from inside a coroutine or not.  This is primarily of use when 
   writing decorators and other advanced metaprogramming features. 
   The implementation requires stack-frame inspection.  The *level*
   argument controls the stack frame in which information is obtained
   and might need to be adjusted depending on the nature of code calling
   this function.

.. function:: awaitable(syncfunc)

   A decorator that allows an asynchronous implementation of a function to be
   attached to an existing synchronous function. If the resulting function is
   called from synchronous code, the synchronous function is used. If the
   function is called from asynchronous code, the asynchronous function is used.

Here is an example that illustrates::

   import curio
   from curio.meta import awaitable

   def spam(x, y):
       print('Synchronous ->', x, y)

   @awaitable(spam)
   async def spam(x, y):
       print('Asynchronous ->', x, y)

   async def main():
       await spam(2, 3)        # Calls asynchronous spam()

   if __name__ == '__main__':
      spam(2, 3)               # Calls synchronous spam()
      curio.run(main())

Exceptions
----------
.. module:: curio

The following exceptions are defined. All are subclasses of the
:class:`CurioError` base class.

.. exception:: CurioError

   Base class for all Curio-specific exceptions.

.. exception:: CancelledError

   Base class for all cancellation-related exceptions.

.. exception:: TaskCancelled

   Exception raised in a coroutine if it has been cancelled using the :meth:`Task.cancel` method.  If ignored, the
   coroutine is silently terminated.  If caught, a coroutine can continue to
   run, but should work to terminate execution.  Ignoring a cancellation
   request and continuing to execute will likely cause some other task to hang.

.. exception:: TaskTimeout

   Exception raised in a coroutine if it has been cancelled by timeout.
   A subclass of ``CancelledError``.

.. exception:: TimeoutCancellationError

   Exception raised in a coroutine if it has been cancelled due to a timeout,
   but not one related to the inner-most timeout operation.  A subclass
   of ``CancelledError``.

.. exception:: UncaughtTimeoutError

   Exception raised if a timeout from an inner timeout operation has
   propagated to an outer timeout, indicating the lack of a proper
   try-except block.  A subclass of ``CurioError``. 

.. exception:: TaskError

   Exception raised by the :meth:`Task.join` method if an uncaught exception
   occurs in a task.  It is a chained exception. The ``__cause__`` attribute
   contains the exception that causes the task to fail.

.. exception:: SyncIOError

   Exception raised if a task attempts to perform a synchronous I/O operation
   on an object that only supports asynchronous I/O.

.. exception:: AsyncOnlyError

   Exception raised by the ``AWAIT()`` function if its applied to code not
   properly running in an async-thread. 

.. exception:: ResourceBusy

   Exception raised in an I/O operation is requested on a resource, but the
   resource is already busy performing the same operation on behalf of another task.
   The exceptions ``ReadResourceBusy`` and ``WriteResourceBusy`` are subclasses
   that provide a more specific cause. 

Low-level Kernel System Calls
-----------------------------
.. module:: curio.traps

The following system calls are available, but not typically used
directly in user code.  They are used to implement higher level
objects such as locks, socket wrappers, and so forth. If you find
yourself using these, you're probably doing something wrong--or
implementing a new Curio primitive.   These calls are found in the
``curio.traps`` submodule.

Unless otherwise indicated, all traps are potentially blocking and
may raise a cancellation exception.

.. asyncfunction:: _read_wait(fileobj)

   Sleep until data is available for reading on
   *fileobj*.  *fileobj* is any file-like object with a `fileno()`
   method.

.. asyncfunction:: _write_wait(fileobj)

   Sleep until data can be written on *fileobj*.
   *fileobj* is any file-like object with a `fileno()` method.

.. asyncfunction:: _io_waiting(fileobj)

   Returns a tuple `(rtask, wtask)` of tasks currently sleeping on
   *fileobj* (if any).  Returns immediately.
   
.. asyncfunction:: _future_wait(future)

   Sleep until a result is set on *future*.  *future*
   is an instance of :py:class:`concurrent.futures.Future`.

.. asyncfunction:: _cancel_task(task)

   Cancel the indicated *task*.  Returns immediately.

.. asyncfunction:: _scheduler_wait(sched, state_name)

   Go to sleep on a kernel scheduler primitive. *sched* is an instance of
   ``curio.sched.SchedBase``. *state_name* is the name of the wait state (used in
   debugging).

.. asyncfunction:: _scheduler_wake(sched, n=1, value=None, exc=None)

   Reschedule one or more tasks from a
   kernel scheduler primitive. *n* is the
   number of tasks to release. *value* and *exc* specify the return
   value or exception to raise in the task when it resumes execution.
   Returns immediately.

.. asyncfunction:: _get_kernel()

   Get a reference to the running ``Kernel`` object. Returns immediately.

.. asyncfunction:: _get_current()

   Get a reference to the currently running ``Task`` instance. Returns immediately.

.. asyncfunction:: _set_timeout(seconds)

   Set a timeout in the currently running task. Returns immediately
   with the previous timeout (if any)

.. asyncfunction:: _unset_timeout(previous)

   Unset a timeout in the currently running task. *previous* is the
   value returned by the _set_timeout() call used to set the timeout.
   Returns immediately.

.. asyncfunction:: _clock():

   Immediately returns the current time according to the Curio
   kernel's clock.

Again, you're unlikely to use any of these functions directly.  However, here's a small taste
of how they're used.  For example, the :meth:`curio.io.Socket.recv` method
looks roughly like this::

    class Socket(object):
        ...
        def recv(self, maxbytes):
            while True:
                try:
                    return self._socket.recv(maxbytes)
                except BlockingIOError:
                    await _read_wait(self._socket)
        ...

This method first tries to receive data.  If none is available, the
:func:`_read_wait` call is used to put the task to sleep until reading
can be performed. When it awakes, the receive operation is
retried. Just to emphasize, the :func:`_read_wait` doesn't actually
perform any I/O. It's just scheduling a task for it.

Debugging and Diagnostics
-------------------------

Curio provides a few facilities for basic debugging and diagnostics.  If you
print a ``Task`` instance, it will tell you the name of the associated
coroutine along with the current file/linenumber of where the task is currently 
executing.   The output might look similar to this::

    Task(id=3, name='child', state='TIME_SLEEP') at filename.py:9

You can additionally use the ``Task.traceback()`` method to create a current
stack traceback of any given task.  For example::

    t = await spawn(coro)
    ...
    print(t.traceback())

Instead of a full traceback, you can also get the current filename and line number::

    filename, lineno = await t.where()

To find out more detailed information about what the kernel is doing, you can 
supply one or more debugging modules to the ``run()`` function.  To trace
all task scheduling events, use the ``schedtrace`` debugger as follows::

    from curio.debug import schedtrace
    run(coro, debug=schedtrace)

To trace all low-level kernel traps, use the ``traptrace`` debugger::

    from curio.debug import traptrace
    run(coro, debug=traptrace)

To report all exceptions from crashed tasks, use the ``logcrash`` debugger::

    from curio.debug import logcrash
    run(coro, debug=logcrash)

To report warnings about long-running tasks that appear to be stalling the
event loop, use the ``longblock`` debugger::

    from curio.debug import longblock
    run(coro, debug=longblock(max_time=0.1))

The different debuggers may be combined together if you provide a list. For example::

    run(coro, debug=[schedtrace, traptrace, logcrash])

The amount of output produced by the different debugging modules might be considerable. You
can filter it to a specific set of coroutine names using the ``filter`` keyword argument.
For example::

    async def spam():
        ...

    async def coro():
        t = await spawn(spam)
        ...

    run(coro, debug=schedtrace(filter={'spam'}))

The logging level used by the different debuggers can be changed using the 
``level`` keyword argument::

    run(coro, debug=schedtrace(level=logging.DEBUG))

A different ``Logger`` instance can be used using the ``log`` keyword argument::

    import logging
    run(coro, debug=schedtrace(log=logging.getLogger('spam')))

Be aware that all diagnostic logging is synchronous.  As such, all
logging operations might temporarily block the event loop--especially
if logging output involves file I/O or network operations.  If this is
a concern, you should take steps to mitigate it in the configuration
of logging.  For example, you might use the ``QueueHandler`` and
``QueueListener`` objects from the ``logging`` module to offload log
handling to a separate thread.


 

