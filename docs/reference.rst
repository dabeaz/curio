Curio Reference Manual
======================

Coroutines
----------

Curio executes coroutines.  A coroutine is a function defined using
``async def``::

    async def hello(name):
          return 'Hello ' + name

Coroutines call other coroutines using ``await``::

    async def main(name):
          s = await hello(name)
          print(s)

Coroutines never run on their own.
They always execute under the supervision of a manager (e.g., an
event-loop, a kernel, etc.).  In Curio, the initial coroutine is
executed using ``run()``::

    import curio
    curio.run(main, 'Guido')

When executing, a coroutine is encapsulated by a "Task."  

Basic Execution
---------------

The following function runs an initial coroutine:

.. function:: run(corofunc, *args, debug=None, selector=None, with_monitor=False, taskcls=Task)

   Run *corofunc* and return its result.  *args* are the arguments
   provided to *corofunc*.  *with_monitor* enables the task monitor.
   *selector* is an optional selector from the :mod:`selectors
   <python:selectors>` standard library. *debug* is a list of
   debugging features (see the section on debugging).  *taskcls* is
   the class used to encapsulate coroutines.  If ``run()`` is called
   when a task is already running, a ``RuntimeError`` is raised.

If you are going to repeatedly execute coroutines one after the other, it
is more efficient to create a ``Kernel`` instance and submit
them using the ``run()`` method.

.. class:: Kernel(selector=None, debug=None, taskcls=Task):

   Create a runtime kernel. The arguments are the same
   as described above for :func:`run()`.

There is only one method that may be used on a :class:`Kernel` instance.

.. method:: Kernel.run(corofunc=None, *args, shutdown=False)

   Run *corofunc* and return its result.
   *args* are the arguments given to *corofunc*.  If
   *shutdown* is ``True``, the kernel cancels all remaining tasks
   and performs a clean shutdown upon return. Calling this method with *corofunc*
   set to ``None`` executes a single scheduling cycle of background tasks 
   before returning immediately. Raises a
   ``RuntimeError`` if called on an already running kernel or if an attempt is
   made to run more than one kernel in the same thread.

A kernel is commonly used as a context manager. For example::

    with Kernel() as kernel:
        kernel.run(corofunc1)
        kernel.run(corofunc2)
        ...
    # Kernel shuts down here

When submitting work, you can either provide an async
function and arguments or you can provide an already instantiated
coroutine.  Both of these ``run()`` invocations work::

    async def hello(name):
        print('hello', name)

    run(hello, 'Guido')    # Preferred
    run(hello('Guido'))    # Ok

This convention is observed by nearly all other functions that accept
coroutines (e.g., spawning tasks, waiting for timeouts, etc.).

Tasks
-----

The following functions manage the execution of concurrent tasks.

.. asyncfunction:: spawn(corofunc, *args, daemon=False)

   Create a new task that concurrently executes the async function *corofunc*.  *args*
   are the arguments provided to *corofunc*. Returns a :class:`Task`
   instance as a result.  The *daemon* option specifies
   that the task is never joined and that its result may be
   disregarded. 

.. asyncfunction:: current_task()

   Returns the :class:`Task` instance corresponding to the caller.  

:func:`spawn` and :func:`current_task` return a :class:`Task` instance ``t``
with the following methods and attributes:

.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``await t.join()``
     - Wait for the task to terminate and return its result.
       Raises :exc:`curio.TaskError` if the task failed with an
       exception. The ``__cause__`` attribute 
       contains the actual exception raised by the task when it crashed.
   * - ``await t.wait()``
     - Waits for task to terminate, but returns no value. 

   * - ``await t.cancel(*, blocking=True, exc=TaskCancelled)``
     - Cancels the task by raising a :exc:`curio.TaskCancelled` exception
       (or the exception specified by *exc*). If ``blocking=True`` (the
       default), waits for the task to actually terminate.  A task may
       only be cancelled once.  If invoked more than once, the second
       request waits until the task is cancelled from the first request.
       If the task has already terminated, this method does nothing and
       returns immediately.  Note: uncaught exceptions that occur as a
       result of cancellation are logged, but not propagated out of the
       ``Task.cancel()`` method.

   * - ``t.traceback()``
     -  Creates a stack traceback string.  Useful for debugging.
   * - ``t.where()``
     - Return (filename, lineno) where the task is executing.
   * - ``t.id``
     - The task's integer id. Monotonically increases.
   * - ``t.coro``
     - The coroutine associated with the task.
   * - ``t.daemon``
     - Boolean flag that indicates whether or not a task is daemonic.
   * - ``t.state``
     - The name of the task's current state.  Useful for debugging.
   * - ``t.cycles``
     - The number of scheduling cycles the task has completed. 
   * - ``t.result``
     - A property holding the task result. If accessed before the a terminates,
       a ``RuntimeError`` exception is raised. If a task crashed with an exception,
       that exception is reraised on access.
   * - ``t.exception``
     - Exception raised by a task, if any.  ``None`` otherwise. 
   * - ``t.cancelled``
     - A boolean flag that indicates whether or not the task was cancelled.
   * - ``t.terminated``
     - A boolean flag that indicates whether or not the task has terminated.

Task Groups
-----------

Tasks may be grouped together to better manage their execution and
collect results.  To do this, create a ``TaskGroup`` instance.

.. class:: TaskGroup(tasks=(), *, wait=all)

   A class representing a group of executing tasks.  *tasks* is an
   optional set of existing tasks to put into the group.  
   *wait* specifies the policy used by ``join()`` to wait for tasks. If *wait* is
   ``all``, then wait for all tasks to complete.  If *wait* is
   ``any`` then wait for any task to terminate and cancel any
   remaining tasks.  If *wait* is ``object``, then wait for any task
   to return a non-None object, cancelling all remaining
   tasks afterwards. If *wait* is ``None``, then immediately cancel all running tasks. 
   Task groups do not form a hierarchy or have any kind of relationship to
   other previously created task groups or tasks.  Moreover, Tasks created by
   the top level ``spawn()`` function are not placed into any task group.
   To create a task in a group, it should be created using ``TaskGroup.spawn()``
   or explicitly added using ``TaskGroup.add_task()``.

The following methods and attributes are supported on a ``TaskGroup`` instance ``g``:

.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``await g.spawn(corofunc, *args, daemon=False)``
     - Create a new task in the group. Returns a ``Task`` instance.
       *daemon* specifies whether or not the result of the task is
       disregarded.  Daemonic tasks are both ignored and cancelled by the ``join()``
       method.
   * - ``await g.add_task(task)``
     - Add an already existing task to the group.
   * - ``await g.next_done()``
     - Wait for and return the next completed task. Return ``None`` if no more tasks remain.
   * - ``await g.next_result()``
     - Wait for and return the result of the next completed task.
       If the task failed with an exception, the exception is raised.  
   * - ``await g.join()``
     - Wait for all tasks in the group to terminate according to the wait policy
       set for the group.  If any of the monitored tasks exits with an exception or
       if the ``join()`` operation itself is cancelled, all remaining tasks in the 
       group are cancelled. If a ``TaskGroup`` is used as a
       context manager, the ``join()`` method is called on block exit.
   * - ``await g.cancel_remaining()``
     - Cancel and remove all remaining non-daemonic tasks from the group.
   * - ``g.completed``
     - The first task that completed with a valid result after calling ``join()``.
   * - ``g.result``
     - The result of the first task that completed after calling ``join()``. 
       May raise an exception if the task exited with an exception.  
   * - ``g.exception``
     - Exception raised by the first task that completed (if any).
   * - ``g.results``
     - A list of all results collected by ``join()``, 
       ordered by task id. May raise an exception if any task
       exited with an exception. 
   * - ``g.exceptions``
     - A list of all exceptions collected by ``join()``.
   * - ``g.tasks``
     - A list of all non-daemonic tasks managed by the group, ordered by task id.
       Does not include tasks where ``Task.join()`` or ``Task.cancel()``
       has been directly called already.

The preferred way to use a ``TaskGroup`` is as a context manager.  
Here are a few common usage patterns::

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

In these examples, access to the ``result`` or ``results`` attribute
may raise an exception if a task failed for some reason. 

If an exception is raised inside the task group context, all managed
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

It is important to emphasize that no tasks placed in a task group survive past
the ``join()`` operation or exit from a context manager.  This includes
any daemonic tasks running in the background.

Time
----

Curio manages time with an internal monotonic clock.  The following functions
are provided:

.. asyncfunction:: sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, 
   execution switches to the next ready task (if any). Returns the current clock value.

.. asyncfunction:: clock()

   Returns the current value of the monotonic clock.  Use this to get a 
   base clock value for the ``wake_at()`` function.

Timeouts
--------
Any blocking operation can be cancelled by a timeout.

.. asyncfunction:: timeout_after(seconds, corofunc=None, *args)

   Execute ``corofunc(*args)`` and return its result. If no result is
   returned before *seconds* have elapsed, a
   :py:exc:`curio.TaskTimeout` exception is raised on the current
   blocking operation.  If *corofunc* is ``None``, the function
   returns an asynchronous context manager that applies a timeout to a
   block of statements.

Every call to ``timeout_after()`` must have a matching exception handler
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
that expired.  The exception handler at (a) does not match (at that
point, the exception being reported is
:py:exc:`curio.TimeoutCancellationError` which indicates
that a timeout/cancellation has occurred somewhere, but that it is NOT
due to the inner-most timeout).

If a nested ``timeout_after()`` is used without a matching except
clause, a timeout is reported as a
:py:exc:`curio.UncaughtTimeoutError` exception.  Remember that all
timeouts should have a matching exception handler.

If you don't care about exception handling, you can also use the following
functions:

.. asyncfunction:: ignore_after(seconds, corofunc=None, *args, timeout_result=None)

   Execute ``corofunc(*args)`` and return its result. If *seconds* elapse, the
   operation is cancelled with a :py:exc:`curio.TaskTimeout` exception, but
   the exception is discarded and the value of *timeout_result* is returned.
   If *corofunc* is ``None``, returns an asynchronous context manager that 
   applies a timeout to a block of statements.  For this case, the resulting
   context manager object has an ``expired`` attribute set to ``True`` if
   time expired.

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

The ``ignore_after()`` function is just a convenience layer to simplify exception
handling. All of the timeout-related functions can be composed and layered
together in any configuration and it should still work.

Cancellation Control
--------------------

Sometimes it is necessary to disable or control cancellation on critical operations. The
following functions can control this:

.. asyncfunction:: disable_cancellation(corofunc=None, *args)

   Disables the delivery of cancellation-related exceptions while
   executing *corofunc*.  *args* are the arguments to *corofunc*.
   The result of *corofunc* is returned.  Any pending cancellation
   is delivered to the first-blocking operation after
   cancellation is reenabled.  If *corofunc* is ``None``, a
   context manager is returned that shields a block of
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
points. Here is an example that shows how to check for cancellation at 
a specific code location (a)::

    async def coro():
        async with disable_cancellation():
            while True:
                await coro1()
                await coro2()
                if await check_cancellation():    # (a)
                    break   # Bail out!

        await check_cancellation()  # Cancellation (if any) delivered here

If you only need to shield a single operation, you can write statements like this::

    async def coro():
        ...
        await disable_cancellation(some_operation, x, y, z)
        ...

Note: It is not possible for cancellation to be reenabled inside code
where it has been disabled.

Synchronization Primitives
--------------------------
.. currentmodule:: None

The following synchronization primitives are available. Their behavior
is identical to their equivalents in the :mod:`threading` module.  However, none
of these primitives are safe to use with threads.

.. class:: Event()

   An event object.

An :class:`Event` instance ``e`` supports the following methods:

.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``e.is_set()``
     - Return ``True`` if set
   * - ``e.clear()``
     - Clear the event value
   * - ``await e.wait()``
     - Wait for the event to be set
   * - ``await e.set()``
     - Set the event. Wake all waiting tasks (if any)

``Lock``, ``RLock``, ``Semaphore`` classes that allow for mutual exclusion and
inter-task coordination. 

.. class:: Lock()

   A mutual exclusion lock. 

.. class:: RLock()

   A recursive mutual-exclusion lock that can be acquired multiple times within the 
   same task.

.. class:: Semaphore(value=1)

   Semaphores are based on a counter.  ``acquire()`` and ``release()``
   decrement and increment the counter respectively.  If the counter is 0, 
   ``acquire()`` blocks until the value is incremented by another task.  The ``value`` 
   attribute of a semaphore is a read-only property holding the current value of the internal 
   counter.

An instance ``lock`` of any of the above classes supports the following methods:

.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``await lock.acquire()``
     - Acquire the lock
   * - ``await lock.release()``
     - Release the lock.
   * - ``lock.locked()``
     - Return ``True`` if the lock is currently held.

The preferred way to use a Lock is as an asynchronous context manager. For example::

    import curio
    lock = curio.Lock()

    async def sometask():
        async with lock:
            print("Have the lock")
            ...


.. class:: Condition(lock=None)

   Condition variable.  *lock* is the underlying lock to use. If ``None``, then
   a :class:`Lock` object is used.

An instance ``cv`` of :class:`Condition`  supports the following methods:


.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``await cv.acquire()``
     - Acquire the underlying lock
   * - ``await cv.release()``
     - Release the underlying lock.
   * - ``cv.locked()``
     - Return ``True`` if the lock is currently held.
   * - ``await cv.wait()``
     - Wait on the condition variable. Releases the underlying lock.
   * - ``await cv.wait_for(pred)``
     - Wait on the condition variable until a supplied predicate function returns ``True``.
       ``pred`` is a callable that takes no arguments.
   * - ``await cv.notify(n=1)``
     - Notify one or more tasks, cause them to wake from ``cv.wait()``.
   * - ``await cv.notify_all()``
     - Notify all waiting tasks.

Proper use of a condition variable is tricky. The following example shows how to implement
producer-consumer synchronization on top of a ``collections.deque`` object::

    import curio
    from collections import deque

    async def consumer(items, cond):
        while True:
            async with cond:
                while not items:         # (a) 
                    await cond.wait()    # Wait for items
                item = items.popleft()
            print('Got', item)

     async def producer(items, cond):
         for n in range(10):
              async with cond:
                  items.append(n)
                  await cond.notify()
              await curio.sleep(1)

     async def main():
         items = deque()
         cond = curio.Condition()
         await curio.spawn(producer, items, cond)
         await curio.spawn(consumer, items, cond)

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

To communicate between tasks, use a :class:`Queue`.  

.. class:: Queue(maxsize=0)

   Creates a queue with a maximum number of elements in *maxsize*.  If not
   specified, the queue can hold an unlimited number of items.

An instance ``q`` of :class:`Queue` supports the following methods:

.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``q.empty()``
     - Return ``True`` if the queue is empty.
   * - ``q.full()``
     - Return ``True`` if the queue is full.
   * - ``q.size()``
     - Return number of items currently in the queue.
   * - ``await q.get()``
     - Return an item from the queue. Block if no items are available.
   * - ``await q.put(item)``
     - Put an item on the queue. Blocks if the queue is at capacity.
   * - ``await q.join()``
     - Wait for all elements to be processed.  Consumers must call 
       ``q.task_done()`` to indicate the completion of each element.
   * - ``await q.task_done()``
     - Indicate that the processing has finished for an item.  If all
       items have been processed and there are tasks waiting on 
       ``q.join()``, they will be awakened.

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

   A queue with "Last In First Out" retrieval policy. In other words, a stack.


Universal Synchronizaton
------------------------

Sometimes it is necessary to synchronize with threads and foreign event loops.
For this, use the following queue and event classes.

.. class:: UniversalQueue(maxsize=0, withfd=False)

   A queue that can be safely used from both Curio tasks and threads.  
   The same programming API is used for both, but ``await`` is
   required for asynchronous operations.  When the queue is no longer
   in use, the ``shutdown()`` method should be called to terminate
   an internal helper-task.   The ``withfd`` option specifies whether
   or not the queue should optionally set up an I/O loopback that
   allows it to be polled by a foreign event loop.  When ``withfd`` is
   ``True``, adding something to the queue writes a byte of data to the
   I/O loopback.  

.. class:: UniversalEvent()

   An event object that can be used in both Curio tasks and threads.
   The same programming interface is used in both. Asynchronous operations
   must be prefaced by ``await``.

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

I/O in Curio is managed by a collection of classes in :mod:`curio.io`.
These classes act as asynchronous proxies around sockets, streams, and
ordinary files.  The programming interface is meant to be the same as
in normal synchronous Python code.

Socket
^^^^^^

The :class:`Socket` class wraps an existing socket-like object with
an async interface.

.. class:: Socket(sockobj)

   Creates a proxy around an existing socket *sockobj*.  *sockobj* is 
   put in non-blocking mode when wrapped. *sockobj* is not closed unless
   the created ``Socket`` instance is explicitly closed or used as a 
   context manager.

The following methods are redefined on an instance ``s`` of :class:`Socket`.

.. list-table:: 
   :widths: 60 40
   :header-rows: 0

   * - ``await s.recv(maxbytes, flags=0)``
     - Receive up to *maxbytes* of data.
   * - ``await s.recv_into(buffer, nbytes=0, flags=0)``
     - Receive up to *nbytes* of data into a buffer.
   * - ``await s.recvfrom(maxsize, flags=0)``
     - Receive up to *maxbytes* of data. Returns a tuple ``(data, client_address)``.
   * - ``await s.recvfrom_into(buffer, nbytes=0, flags=0)``
     - Receive up to *nbytes* of data into a buffer.
   * - ``await s.recvmsg(bufsize, ancbufsize=0, flags=0)``
     - Receive normal and ancillary data.
   * - ``await s.recvmsg_into(buffers, ancbufsize=0, flags=0)``
     - Receive normal and ancillary data into a buffer.
   * - ``await s.send(data, flags=0)``
     - Send data.  Returns the number of bytes sent.
   * - ``await s.sendall(data, flags=0)``
     - Send all of the data in *data*. If cancelled, the ``bytes_sent`` attribute of the
       exception contains the number of bytes sent.
   * - ``await s.sendto(data, address)``
     - Send data to the specified address.
   * - ``await s.sendto(data, flags, address)``
     - Send data to the specified address (alternate).
   * - ``await s.sendmsg(buffers, ancdata=(), flags=0, address=None)``
     - Send normal and ancillary data to the socket.
   * - ``await s.accept()``
     - Wait for a new connection.  Returns a tuple ``(sock, address)`` where ``sock``
       is an instance of ``Socket``.
   * - ``await s.connect(address)``
     - Make a connection.   
   * - ``await s.connect_ex(address)``
     - Make a connection and return an error code instead of raising an exception.
   * - ``await s.close()``
     - Close the connection.  
   * - ``await s.shutdown(how)``
     - Shutdown the socket.  *how* is one of
       ``SHUT_RD``, ``SHUT_WR``, or ``SHUT_RDWR``.
   * - ``await s.do_handshake()``
     - Perform an SSL client handshake (only on SSL sockets).
   * - ``s.makefile(mode, buffering=0)``
     - Make a :class:`curio.io.FileStream` instance wrapping the socket.
       Prefer to use :meth:`Socket.as_stream` instead. Not supported on Windows.
   * - ``s.as_stream()``
     - Wrap the socket as a stream using :class:`curio.io.SocketStream`. 
   * - ``s.blocking()``
     -  A context manager that returns the internal socket placed into blocking mode.

Any socket method not listed here (e.g., ``s.setsockopt()``) will be
delegated directly to the underlying socket as an ordinary method.
:class:`Socket` objects may be used as an asynchronous context manager
which cause the underlying socket to be closed when done. 

Streams
^^^^^^^

A stream is an asynchronous file-like object that wraps around an
object that natively implements non-blocking I/O.  Curio implements
two basic classes:

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
   closed or used as a context manager.  Instantiated by ``Socket.as_stream()``.

An instance ``s`` of either stream class implement the following methods:


.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``await s.read(maxbytes=-1)``
     - Read up to *maxbytes* of data on the file. If omitted, reads as
       much data as is currently available.
   * - ``await s.readall()``
     - Return all data up to EOF.
   * - ``await s.read_exactly(n)``
     - Read exactly n bytes of data.
   * - ``await s.readline()``
     - Read a single line of data.
   * - ``await s.readlines()``
     - Read all of the lines.  If cancelled, the ``lines_read`` attribute of
       the exception contains all lines read.
   * - ``await s.write(bytes)``
     - Write all of the data in *bytes*.
   * - ``await s.writelines(lines)``
     - Writes all of the lines in *lines*. If cancelled, the ``bytes_written``
       attribute of the exception contains the total bytes written so far.
   * - ``await s.flush()``
     - Flush any unwritten data from buffers.
   * - ``await s.close()``
     - Flush any unwritten data and close the file.  Not called on garbage collection.
   * - ``s.blocking()``
     -  A context manager that temporarily places the stream into blocking mode and
        returns the raw file object used internally.  Note: for
        ``SocketStream`` this creates a file using
        ``open(sock.fileno(), 'rb+', closefd=False)`` which is not
        supported on Windows.

Other methods (e.g., ``tell()``, ``seek()``, ``setsockopt()``, etc.) are available
if the underlying ``fileobj`` or ``sockobj`` provides them. A ``Stream`` may be used as an asynchronous context manager. 

Files
^^^^^

The :mod:`curio.file` module provides an asynchronous compatible
replacement for the built-in ``open()`` function and associated file
objects.  Use this to read and write traditional files on the
filesystem while avoiding blocking. How this is accomplished is an
implementation detail (although threads are used in the initial
version).

.. function:: aopen(*args, **kwargs)

   Creates a :class:`curio.file.AsyncFile` wrapper around a traditional file object as
   returned by Python's builtin ``open()`` function.   The arguments are exactly the
   same as for ``open()``.  The returned file object must be used as an asynchronous
   context manager.

.. class:: AsyncFile(fileobj)

   This class represents an asynchronous file as returned by the ``aopen()``
   function.  Normally, instances are created by the ``aopen()`` function.
   However, it can be wrapped around an already-existing file object.

The following methods are redefined on :class:`AsyncFile` objects to be
compatible with coroutines.  Any method not listed here will be
delegated directly to the underlying file.  These methods take the same arguments
as the underlying file object.  Be aware that not all of these methods are
available on all kinds of files (e.g., ``read1()``, ``readinto()`` and similar
methods are only available in binary-mode files).

.. list-table:: 
   :widths: 50 50
   :header-rows: 0

   * - ``await f.read(maxbytes=-1)``
     - Read up to *maxbytes* of data on the file. If omitted, reads as
       much data as is currently available.
   * - ``await f.read1(maxbytes=-1)``
     - Same as ``read()``, but uses a single system call.
   * - ``await f.readline(maxbytes=-1)``
     - Read a line of input.
   * - ``await f.readlines(maxbytes=-1)``
     - Read all lines of input data
   * - ``await f.readinto(buffer)``
     - Read data into a buffer.
   * - ``await f.readinto1(buffer)``
     - Read data into a buffer using a single system call.
   * - ``await f.readall()``
     - Read all available data up to EOF.
   * - ``await f.write(data)``
     - Write data
   * - ``await f.writelines(lines)``
     - Write all lines.
   * - ``await f.truncate(pos=None)``
     - Truncate the file to a given size/position. If ``None``, file is truncated at position
       of current file pointer.
   * - ``await f.seek(offset, whence=os.SEEK_SET)``
     - Seek to a new file position.
   * - ``await f.tell()``
     - Report current file pointer.
   * - ``await f.flush()``
     - Flush data to a file
   * - ``await f.close()``
     - Flush remaining data and close.

The preferred way to use an :class:`AsyncFile` object is as an asynchronous context manager.
For example::

    async with aopen(filename) as f:
        # Use the file
        data = await f.read()

:class:`AsyncFile` objects may also be used with asynchronous iteration.
For example::

    async with aopen(filename) as f:
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
   specifies whether to use the ``SO_REUSEADDR`` socket option.  *reuse_port*
   specifies whether to use the ``SO_REUSEPORT`` socket option.

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

Curio provides a :class:`Channel` class that can be used to perform message
passing between interpreters running in separate processes.  Message passing
uses the same protocol as the ``multiprocessing`` standard library.

.. class:: Channel(address, family=socket.AF_INET)

   Represents a communications endpoint for message passing.  
   *address* is the address and *family* is the protocol
   family.

The following methods are used to establish a connection on a :class:`Channel` instance ``ch``.

.. list-table:: 
   :widths: 50 50
   :header-rows: 0

   * - ``await ch.accept(*, authkey=None)``
     - Wait for an incoming connection and return a
       :class:`Connection` instance.  *authkey* is an optional
       authentication key.
   * - ``await ch.connect(*, authkey=None)``
     - Make an outgoing connection and return a :class:`Connection` instance. 
       *authkey* is an optional authentication key.
   * - ``ch.bind()``
     - Performs the address binding step of the ``accept()`` method.
       Use this to have the host operating system to assign a port
       number.  For example, use an address of ``('localhost', socket.INADDR_ANY)`` and call ``bind()``. 
       Afterwards,  ``ch.address`` contains the assigned address.
   * - ``await ch.close()``
     - Close the channel.

The ``connect()`` and ``accept()`` methods of :class:`Channel` instances return an
instance of the :class:`Connection` class:

.. class:: Connection(reader, writer)

   Represents a connection on which message passing of Python objects is
   supported.  *reader* and *writer* are I/O streams on which reading 
   and writing are to take place (for example, instances of ``SocketStream``
   or ``FileStream``).

An instance ``c`` of :class:`Connection` supports the following methods:

.. list-table:: 
   :widths: 55 45
   :header-rows: 0

   * - ``await c.close()``
     - Close the connection.
   * - ``await c.recv()``
     - Receive a Python object.
   * - ``await c.recv_bytes()``
     - Receive a raw message of bytes. 
   * - ``await c.send(obj)``
     - Send a Python object.
   * - ``await c.send_bytes(buf, offset=0, size=None)``
     - Send a buffer of bytes as a single message.  *offset* and *size* specify
       an optional byte offset and size into the underlying memory buffer. 
   * - ``await c.authenticate_server(authkey)``
     - Authenticate server endpoint.
   * - ``await c.authenticate_client(authkey)``
     - Authenticate client endpoint.

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

The :mod:`curio.socket` module provides a wrapper around selected functions in the built-in
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

The :mod:`curio.ssl` module provides Curio-compatible functions for creating an SSL
wrapped Curio socket.  The following functions are redefined (and have the same
calling signature as their counterparts in the standard :mod:`ssl` module:

.. asyncfunction:: wrap_socket(*args, **kwargs)

.. asyncfunction:: get_server_certificate(*args, **kwargs)

.. function:: create_default_context(*args, **kwargs)

.. class:: SSLContext

   A redefined and modified variant of :class:`ssl.SSLContext` so that the
   :meth:`wrap_socket` method returns a socket compatible with Curio.

Don't attempt to use the :mod:`curio.ssl` module without a careful read of Python's official documentation
at https://docs.python.org/3/library/ssl.html.

It is usually easier to apply SSL to a
connection using the high level network functions previously described.
For example, here's how you make an outgoing SSL connection::

    sock = await curio.open_connection('www.python.org', 443,
                                       ssl=True,
                                       server_hostname='www.python.org')

Here's how you create a server that uses SSL::

    import curio
    from curio import ssl

    KEYFILE = "privkey_rsa"       # Private key
    CERTFILE = "certificate.crt"  # Server certificat

    async def handler(client, addr):
        ...

    if __name__ == '__main__':
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
        curio.run(curio.tcp_server('', 10000, handler, ssl=ssl_context))


Subprocesses
------------

The :mod:`curio.subprocess` module implements the same functionality as the built-in
:mod:`subprocess` module.

.. class:: Popen(*args, **kwargs)

   A wrapper around the :class:`subprocess.Popen` class.  The same arguments are
   accepted. On the resulting :class:`~subprocess.Popen` instance, the
   :attr:`~subprocess.Popen.stdin`, :attr:`~subprocess.Popen.stdout`, and
   :attr:`~subprocess.Popen.stderr` file attributes have been wrapped by the
   :class:`curio.io.FileStream` class. You can use these in an asynchronous
   context.

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

Asynchronous Threads
--------------------

If you need to perform a lot of synchronous operations, but still
interact with Curio, you can launch an async-thread.
An asynchronous thread flips the whole world around--instead
of executing selected synchronous operations using ``run_in_thread()``, you
run everything in a thread and perform selected async operations using the
``AWAIT()`` function.

To create an asynchronous thread, use ``spawn_thread()``:

.. asyncfunction:: spawn_thread(func, *args, daemon=False)

   Launch an asynchronous thread that runs the callable ``func(*args)``.
   ``daemon`` specifies if the thread runs in daemonic mode. 
   Returns an ``AsyncThread`` instance.

An instance ``t`` of ``AsyncThread`` supports the following methods.

.. list-table:: 
   :widths: 55 45
   :header-rows: 0

   * - ``await t.join()``
     - Waits for the thread to terminate, returning the final result.
       The final result is returned in the same manner as ``Task.join()``.
   * - ``await t.wait()``
     - Waits for the thread to terminate, but does not return any result.
   * - ``await t.cancel(*, blocking=True, exc=TaskCancelled)``
     - Cancels the asynchronous thread.  The behavior is the same as with ``Task``.
       Note: An asynchronous thread can only be cancelled when it performs 
       operations using ``AWAIT()``.
   * - ``t.result``
     - The final result of the thread. If the thread crashed
       with an exception, that exception is reraised on access.
   * - ``t.exception``
     - The final exception (if any)
   * - ``t.id``
     - Thread ID. A monotonically increasing integer.
   * - ``t.terminated``
     - ``True`` if the thread is terminated.
   * - ``t.cancelled``
     - ``True`` if the thread was cancelled.

Within a thread, the following function is used to execute any coroutine.

.. function:: AWAIT(coro)

   Execute a coroutine on behalf of an asynchronous thread.  The requested
   coroutine executes in Curio's main execution thread.  The caller is
   blocked until it completes.  If used outside of an asynchronous thread,
   an ``AsyncOnlyError`` exception is raised.  If ``coro`` is not a 
   coroutine, it is returned unmodified.   The reason ``AWAIT`` is all-caps
   is to make it more easily heard when there are all of these coders yelling
   at you to just use pure async code instead of launching a thread. Also, 
   ``await`` is a reserved keyword in Python 3.7.

Here is an example of an asynchronous thread reading off a Curio queue::

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

Scheduler Activations
---------------------

Every task in Curio goes through a life-cycle of creation, running,
suspension, and termination.  These steps are managed by an internal
scheduler.  A scheduler activation is a mechanism for monitoring these
steps.  To do this, you define a class that inherits from 
:class:`Activation` in the submodule ``curio.activation``. 

.. class:: Activation

   Base class for defining scheduler activations.

An instance ``a`` of :class:`Activation` implements the following methods:

.. list-table:: 
   :widths: 55 45
   :header-rows: 0

   * - ``a.activate(kernel)``
     - Executed once upon initialization of the Curio kernel. *kernel* is
       a reference to the ``Kernel`` instance.
   * - ``a.created(task)``
     - Called when a new task is created.  *task* is the newly created ``Task`` instance.
   * - ``a.running(task)``
     - Called immediately prior to the execution cycle of a task.
   * - ``a.suspended(task)``
     - Called when a task has suspended execution.
   * - ``a.terminated(task)``
     - Called when a task has terminated execution. Note: the
       ``suspended()`` method is always called immediately prior to a task being terminated.

Activations are used to implement debugging and diagnostic tools. As
an example, here is a scheduler activation that monitors for
long-execution times and reports warnings::

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
    run(coro, activations=[LongBlock(0.05)])

Asynchronous Metaprogramming
----------------------------

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

The following exceptions are defined. All are subclasses of the
:class:`CurioError` base class.


.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``CurioError``
     - Base class for all Curio-specific exceptions.
   * - ``CancelledError``
     - Base class for all cancellation-related exceptions.
   * - ``TaskCancelled``
     - Exception raised in a coroutine if it has been cancelled using the :meth:`Task.cancel` method.  If ignored, the
       coroutine is silently terminated.  If caught, a coroutine can continue to
       run, but should work to terminate execution.  Ignoring a cancellation
       request and continuing to execute will likely cause some other task to hang.
   * - ``TaskTimeout``
     - Exception raised in a coroutine if it has been cancelled by timeout.
       A subclass of ``CancelledError``.
   * - ``TimeoutCancellationError``
     - Exception raised in a coroutine if it has been cancelled due to a timeout,
       but not one related to the inner-most timeout operation.  A subclass
       of ``CancelledError``.
   * - ``UncaughtTimeoutError``
     - Exception raised if a timeout from an inner timeout operation has
       propagated to an outer timeout, indicating the lack of a proper
       try-except block.  A subclass of ``CurioError``. 
   * - ``TaskError``
     - Exception raised by the :meth:`Task.join` method if an uncaught exception
       occurs in a task.  It is a chained exception. The ``__cause__`` attribute
       contains the exception that causes the task to fail.
   * - ``SyncIOError``
     - Exception raised if a task attempts to perform a synchronous I/O operation
       on an object that only supports asynchronous I/O.
   * - ``AsyncOnlyError``
     - Exception raised by the ``AWAIT()`` function if its applied to code not
       properly running in an async-thread. 
   * - ``ResourceBusy``
     - Exception raised in an I/O operation is requested on a resource, but the
       resource is already busy performing the same operation on behalf of another task.
       The exceptions ``ReadResourceBusy`` and ``WriteResourceBusy`` are subclasses
       that provide a more specific cause. 

Low-level Traps and Scheduling
------------------------------

The following system calls are available in ``curio.traps``, but not typically used
directly in user code.  They are used to implement higher level
objects such as locks, socket wrappers, and so forth. If you find
yourself using these, you're probably doing something wrong--or
implementing a new Curio primitive.   

Unless otherwise indicated, all traps are potentially blocking and
may raise a cancellation exception.

.. list-table:: 
   :widths: 50 50
   :header-rows: 0

   * - ``await _read_wait(fileobj)``
     - Sleep until data is available for reading on
       *fileobj*.  *fileobj* is any file-like object with a `fileno()`
       method.
   * - ``await _write_wait(fileobj)``
     - Sleep until data can be written on *fileobj*.
       *fileobj* is any file-like object with a `fileno()` method.
   * - ``await _io_waiting(fileobj)``
     - Returns a tuple `(rtask, wtask)` of tasks currently sleeping on
       *fileobj* (if any).  Returns immediately.
   * - ``await _future_wait(fut)``   
     - Sleep until a result is set on *fut*.  *fut*
       is an instance of :py:class:`concurrent.futures.Future`.
   * - ``await _cancel_task(task, exc=TaskCancelled, val=None)``
     - Cancel *task*.  Returns immediately. *exc* and *val*
       specify the exception type and value.
   * - ``await _scheduler_wait(sched, state_name)``
     - Go to sleep on a kernel scheduler primitive. *sched* is an 
       instance of ``curio.sched.SchedBase``. *state_name* is the name of 
       the wait state (used in debugging).
   * - ``await _scheduler_wake(sched, n=1, value=None, exc=None)``
     -  Reschedule one or more tasks from a kernel scheduler primitive. *n* is the
        number of tasks to release. *value* and *exc* specify the return
        value or exception to raise in the task when it resumes execution.
        Returns immediately.
   * - ``await _get_kernel()``
     - Get a reference to the running ``Kernel`` object. Returns immediately.
   * - ``await _get_current()``
     - Get a reference to the currently running ``Task`` instance. Returns immediately.
   * - ``await _sleep(seconds)``
     - Sleep for a given number of seconds.
   * - ``await _set_timeout(seconds)``
     - Set a timeout in the currently running task. Returns immediately
       with the previous timeout (if any)
   * - ``await _unset_timeout(previous)``
     - Unset a timeout in the currently running task. *previous* is the
       value returned by the _set_timeout() call used to set the timeout.
       Returns immediately.
   * - ``await _clock()``
     - Immediately returns the current monotonic clock value.

Again, you're unlikely to use any of these functions directly.
However, here's a small taste of how they get used.  For example, the
:meth:`curio.io.Socket.recv` method looks roughly like this::

    class Socket:
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

The ``_scheduler_wait()`` and ``_scheduler_wake()`` traps are used to 
implement high-level synchronization and queuing primitives.  The
``sched`` argument to these calls is an instance of a class that 
inherits from ``SchedBase`` defined in the ``curio.sched`` submodule.
The following specific classes are defined:

.. class:: SchedFIFO

   A scheduling FIFO queue.  Used to implement locks and queues.

.. class:: SchedBarrier

   A scheduling barrier.  Used to implement events.

The following public methods are defined on an instance ``s`` of these classes:

.. list-table:: 
   :widths: 40 60
   :header-rows: 0

   * - ``await s.suspend(reason)``
     - Suspend the calling task. ``reason`` is a string describing why.
   * - ``await s.wake(n=1)``
     - Wake one or more suspended tasks.
   * - ``len(s)``
     - Number of tasks suspended.

Here is an example of how a scheduler primitive is used to implement an ``Event``::

    from curio.sched import SchedBarrier

    class Event:
        def __init__(self):
            self._value = 0
            self._sched = SchedBarrier()
        
        async def wait(self):
            if self._value == 0:
                await self._sched.suspend('EVENT_WAIT')

        async def set(self):
            self._value = 1
            await self._sched.wake(len(self._sched))


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


 

