Curio Reference Manual
======================

This manual describes the basic concepts and functionality provided by curio.

Coroutines
----------

Curio is solely concerned with the execution of coroutines.  A coroutine
is a function defined using ``async def``.  For example::

    async def hello(name):
          return 'Hello ' + name

Coroutines call other coroutines using ``await``. For example::

    async def main(name):
          s = await hello(name)
          print(s)

Unlike a normal function, a coroutine can never run all on its own.
It always has to execute under the supervision of a manager (e.g., an
event-loop, a kernel, etc.).  In curio, an initial coroutine is
executed by a low-level kernel using the ``run()`` function. For
example::

    import curio
    curio.run(main, 'Guido')

When executed by curio, a coroutine is considered to be a "Task."  Whenever
the word "task" is used, it refers to the execution of a coroutine.

The Kernel
----------

All coroutines in curio are executed by an underlying kernel.  Normally, you would
run a top-level coroutine using the following function:

.. function:: run(corofunc, *args, debug=None, selector=None,
              with_monitor=False, **other_kernel_args)

   Run the async function *corofunc* to completion and return its
   final return value.  *args* are the arguments provided to
   *corofunc*.  If *with_monitor* is ``True``, then the monitor
   debugging task executes in the background.  If *selector* is given,
   it should be an instance of a selector from the :mod:`selectors
   <python:selectors>` module.  *debug* is a list of optional
   debugging features. See the section on debugging for more detail.
   A ``RuntimeError`` is raised if ``run()`` is invoked more than once
   from the same thread.

If you are going to repeatedly run coroutines one after the other, it
will be more efficient to create a ``Kernel`` instance and submit
them using its ``run()`` method as described below:

.. class:: Kernel(selector=None, debug=None):

   Create an instance of a curio kernel.  The arguments are the same
   as described above for the :func:`run()` function.  

There is only one method that may be used on a :class:`Kernel` outside of coroutines.

.. method:: Kernel.run(corofunc=None, *args, shutdown=False)

   Runs the kernel until the supplied async function *corofunc*
   completes execution.The final result of this function, if supplied,
   is returned. *args* are the arguments given to *corofunc*.  If
   *shutdown* is ``True``, the kernel will cancel all remaining tasks
   and perform a clean shutdown. Calling this method with *corofunc*
   set to ``None`` causes the kernel to run through a single check for
   task activity before returning immediately.  Raises a
   `RuntimeError` if a task is submitted to an already running kernel
   or if an attempt is made to run more than one kernel in a thread.

If submitting multiple tasks, one after another, from synchronous
code, consider using a kernel as a context manager.  For example::

    with Kernel() as kernel:
        kernel.run(corofunc1)
        kernel.run(corofunc2)
        ...
    # Kernel shuts down here

When submitted a task to the Kernel, you can either provide an async
function and calling arguments or you can provide an instantiated
coroutine.  For example::

    async def hello(name):
        print('hello', name)

    run(hello, 'Guido')    # Preferred
    run(hello('Guido'))    # Ok

This convention is observed by nearly all other functions that accept
coroutines (e.g., spawning tasks, waiting for timeouts, etc.).  As a
general rule, the first form of providing a function and arguments
should be preferred. This form of calling is required for certain 
parts of Curio so you're code will be more consistent if you use it.

Tasks
-----

The following functions are defined to help manage the execution of tasks.

.. asyncfunction:: spawn(corofunc, *args, daemon=False)

   Create a new task that runs the async function *corofunc*.  *args*
   are the arguments provided to *corofunc*. Returns a :class:`Task`
   instance as a result.  The *daemon* option, if supplied, specifies
   that the new task will run indefinitely in the background.  Curio
   only runs as long as there are non-daemonic tasks to execute.
   Note: a daemonic task will still be cancelled if the underlying
   kernel is shut down.  

   Note: ``spawn()`` creates a completely independent task.  The resulting task
   is not placed into any kind of task group as might be managed by :class:`TaskGroup`
   instances described later.

.. asyncfunction:: current_task()

   Returns a reference to the :class:`Task` instance corresponding to the
   caller.  A coroutine can use this to get a self-reference to its
   current :class:`Task` instance if needed.

The :func:`spawn` and :func:`current_task` both return a :class:`Task` instance
that serves as a kind of wrapper around the underlying coroutine that's executing.

.. class:: Task

   A class representing an executing coroutine. This class cannot be
   created directly.

.. asyncmethod:: Task.join()

   Wait for the task to terminate.  Returns the value returned by the task or
   raises a :exc:`curio.TaskError` exception if the task failed with an
   exception. This is a chained exception.  The ``__cause__`` attribute of this
   exception contains the actual exception raised by the task when it crashed.
   If called on a task that has been cancelled, the ``__cause__``
   attribute is set to :exc:`curio.TaskCancelled`.

.. asyncmethod:: Task.wait()

   Like ``join()`` but doesn't return any value.  The caller must obtain the
   result of the task separately via the ``result`` or ``exception`` attribute.

.. asyncmethod:: Task.cancel(blocking=True)

   Cancels the task. This raises a :exc:`curio.TaskCancelled`
   exception in the task which may choose to handle it in order to
   perform cleanup actions. If ``blocking=True`` (the default), does
   not return until the task actually terminates.  Curio only allows a
   task to be cancelled once. If this method is somehow invoked more
   than once on a still running task, the second request will merely
   wait until the task is cancelled from the first request.  If the
   task has already run to completion, this method does nothing and
   returns immediately.  Returns ``True`` if the task was actually
   cancelled. ``False`` is returned if the task was already finished
   prior to the cancellation request.  Cancelling a task also cancels
   any previously set timeout. 

The following public attributes are available of :class:`Task` instances:

.. attribute:: Task.id

   The task's integer id.

.. attribute:: Task.coro

   The underlying coroutine associated with the task.

.. attribute:: Task.daemon

   Boolean flag that indicates whether or not a task is daemonic.

.. attribute:: Task.state

   The name of the task's current state.  Printing it can be potentially useful
   for debugging.

.. attribute:: Task.cycles

   The number of scheduling cycles the task has completed. This might be useful
   if you're trying to figure out if a task is running or not. Or if you're
   trying to monitor a task's progress.

.. attribute:: Task.result

   The result of a task, if completed.  If accessed before the task terminated,
   a ``RuntimeError`` exception is raised.  If the task crashed with an exception,
   that exception is reraised on access.

.. attribute:: Task.exception

   Exception raised by a task, if any.

.. attribute:: Task.cancelled

   A boolean flag that indicates whether or not the task was cancelled.

.. attribute:: Task.terminated

   A boolean flag that indicates whether or not the task has run to completion.


Task Groups
-----------

Curio provides a mechanism for grouping tasks together and managing their
execution.  This includes cancelling tasks as a group, waiting for tasks
to finish, or watching a group of tasks as they finish.   To do this, create
a ``TaskGroup`` instance.

.. class:: TaskGroup(tasks=(), *, wait=all, name=None)

   A class representing a group of executing tasks.  *tasks* is an
   optional set of existing tasks to put into the group.  New tasks
   can later be added using the ``spawn()`` method below. *wait*
   specifies the policy used for waiting for tasks.  See the ``join()``
   method below.  Each ``TaskGroup`` is an independent entity.
   Task groups do not form a hierarchy or any kind of relationship to
   other previously created task groups or tasks.  Moreover, Tasks created by
   the top level ``spawn()`` function are not placed into any task group.
   To create a task in a group, it should be created using ``TaskGroup.spawn()``
   or explicitly added using ``TaskGroup.add_task()``.

The following methods are supported on ``TaskGroup`` instances:

.. asyncmethod:: TaskGroup.spawn(corofunc, *args, ignore_result=False)

   Create a new task that's part of the group.  Returns a ``Task`` instance.
   The *ignore_result* flag indicates whether or not the group cares about the 
   task's final result.  If specified, the result of the task is ignored.
   The task is still considered part of the group for purposes of cancellation
   however (i.e., if the task group is cancelled, any running tasks with an ignored result
   in the group are also cancelled).   

.. asyncmethod:: TaskGroup.add_task(coro)

   Adds an already existing task to the task group. 

.. asyncmethod:: TaskGroup.next_done(*, cancel_remaining=False)

   Returns the next completed task.  Returns ``None`` if no more tasks remain.
   A ``TaskGroup`` may also be used as an asynchronous iterator. If the
   *cancel_remaining* option is given, all remaining tasks are cancelled.

.. asyncmethod:: TaskGroup.join(*, wait=all)

   Wait for tasks in the group to terminate.  If *wait* is `all`, then
   wait for all tasks to completee.  If *wait* is `any` then wait for
   any task to complete and cancel any remaining tasks. 
   If any task returns with an error, then all remaining tasks are
   immediately cancelled and a ``TaskGroupError`` exception is raised.
   If the ``join()`` operation itself is cancelled, all remaining
   tasks in the group are also cancelled.  If a ``TaskGroup`` is used
   as a context manager, the ``join()`` method is called on
   context-exit.

.. asyncmethod:: TaskGroup.cancel_remaining()

   Cancel all remaining tasks.

.. attribute:: TaskGroup.completed

   The first task that completed in the group.  Useful when used in
   combination with the ``wait=any`` option on ``join()``.   


The preferred way to use a ``TaskGroup`` is as a context manager.  For
example, here is how you can create a group of tasks, wait for them
to finish, and collect their results::

    async with TaskGroup() as g:
        t1 = await g.spawn(func1)
        t2 = await g.spawn(func2)
        t3 = await g.spawn(func3)

    # all tasks done here
    print('t1 got', t1.result)
    print('t2 got', t2.result)
    print('t3 got', t3.result)

Here is how you would launch tasks and collect their results in the
order that they complete::

    async with TaskGroup() as g:
        t1 = await g.spawn(func1)
        t2 = await g.spawn(func2)
        t3 = await g.spawn(func3)
        async for task in g:
            print(task, 'completed.', task.result)

If you wanted to launch tasks and exit when the first one has finished,
use the ``wait=any`` option like this::

    async with TaskGroup(wait=any) as g:
        await g.spawn(func1)
        await g.spawn(func2)
        await g.spawn(func3)

    result = g.completed.result    # First completed task

If any exception is raised inside the task group context, all launched
tasks are cancelled and the exception is reraised.  For example::

    try:
        async with TaskGroup() as g:
            t1 = await g.spawn(func1)
            t2 = await g.spawn(func2)
            t3 = await g.spawn(func3)
            raise RuntimeError()
    except RuntimeError:
        # All launched tasks will have terminated or been cancelled
        assert t1.terminated
        assert t2.terminated
        assert t3.terminated

This behavior also applies to features such as a timeout. For
example::

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

The timeout exception itself is only raised in the code that's using
the task group.  Child tasks are cancelled using the ``cancel()`` 
method and would receive a ``TaskCancelled`` exception.

If any launched tasks exit with an exception other than
``TaskCancelled``, a ``TaskGroupError`` exception is raised.  For
example::

    async def bad1():
        raise ValueError('bad value')

    async def bad2():
        raise RuntimeError('bad run')

    try:
        async with TaskGroup() as g:
            await g.spawn(bad1)
            await g.spawn(bad2)
            await sleep(1)
    except TaskGroupError as e:
        print('Failed:', e.errors)   # Print set of exception types
	for task in e:
	    print('Task', task, 'failed because of:', task.exception)

A ``TaskGroupError`` exception contains more information about what happened
with the tasks.  The ``errors`` attribute is a set of exception types
that took place.  In this example, it would be the set ``{ ValueError, RuntimeError }``.
To get more specific information, you can iterate over the exception (or look at its
``failed`` attribute).   This will produce all of the tasks that failed.  The
``task.exception`` attribute can be used to get specific exception information 
for that task.

Time
----

The following functions are used by tasks to help manage time.

.. asyncfunction:: sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, the
   kernel merely switches to the next task (if any).

.. asyncfunction:: wake_at(clock)

   Sleep until the monotonic clock reaches the given absolute clock
   value.  Returns the value of the monotonic clock at the time the
   task awakes.  Use this function if you need to have more precise
   interval timing.

.. asyncfunction:: clock()

   Returns the current value of the kernel clock.   This is often used in
   conjunction with the ``wake_at()`` function (you'd use this to get
   an initial clock value for passing an argument).  

Timeouts
--------
Any blocking operation in curio can be cancelled after a timeout.  The following
functions can be used for this purpose:

.. asyncfunction:: timeout_after(seconds, corofunc=None, *args)

   Execute the specified coroutine and return its result. However,
   issue a cancellation request to the calling task after *seconds*
   have elapsed.  When this happens, a :py:exc:`curio.TaskTimeout`
   exception is raised.  If *corofunc* is ``None``, the result of this
   function serves as an asynchronous context manager that applies a
   timeout to a block of statements.

   :func:`timeout_after` may be composed with other :func:`timeout_after`
   operations (i.e., nested timeouts).   If an outer timeout expires
   first, then ``curio.TimeoutCancellationError`` is raised
   instead of :py:exc:`curio.TaskTimeout`.  If an inner timeout
   expires and fails to properly catch :py:exc:`curio.TaskTimeout`,
   a ``curio.UncaughtTimeoutError`` is raised in the outer
   timeout.

.. asyncfunction:: ignore_after(seconds, corofunc=None, *args, timeout_result=None)

   Execute the specified coroutine and return its result. Issue a
   cancellation request after *seconds* have elapsed.  When a timeout
   occurs, no exception is raised.  Instead, ``None`` or the value of
   *timeout_result* is returned.  If *corofunc* is ``None``, the result is
   an asynchronous context manager that applies a timeout to a block
   of statements.  For the context manager case, the resulting 
   context manager object has an ``expired`` attribute set to ``True`` if time
   expired.

   Note: :func:`ignore_after` may also be composed with other timeout
   operations.  ``curio.TimeoutCancellationError`` and
   ``curio.UncaughtTimeoutError`` exceptions might be raised
   according to the same rules as for :func:`timeout_after`.

Here is an example that shows how these functions can be used::

    # Execute coro(args) with a 5 second timeout
    try:
        result = await timeout_after(5, coro, args)
    except TaskTimeout as e:
        result = None

    # Execute multiple statements with a 5 second timeout
    try:
        async with timeout_after(5):
             await coro1(args)
             await coro2(args)
             ...
    except TaskTimeout as e:
        # Handle the timeout
        ...

The difference between :func:`timeout_after` and :func:`ignore_after` concerns
the exception handling behavior when time expires.  The latter function
returns ``None`` instead of raising an exception which might be more
convenient in certain cases. For example::

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

It's important to note that every curio operation can be cancelled by timeout.
Rather than having every possible call take an explicit *timeout* argument,
you should wrap the call using :func:`timeout_after` or :func:`ignore_after` as
appropriate.

Cancellation Control
--------------------

.. function:: disable_cancellation(corofunc=None, *args)

   Disables the delivery of cancellation-related exceptions to the
   calling task.  Cancellations will be delivered to the first
   blocking operation that's performed once cancellation delivery is
   reenabled.  This function may be used to shield a single coroutine 
   or used as a context manager (see example below).
   
.. function:: enable_cancellation(corofunc=None, *args)

   Reenables the delivery of cancellation-related exceptions.  This
   function is used as a context manager.  It may only be used
   inside a context in which cancellation has been disabled.  This
   function may be used to shield a single coroutine or used as
   a context manager (see example below).

.. asyncfunction:: check_cancellation()

   Checks to see if any cancellation is pending for the calling task.
   If cancellation is allowed, a cancellation exception is raised
   immediately.  If cancellation is not allowed, it returns the
   pending cancellation exception instance (if any).  Returns ``None``
   if no cancellation is pending.

Use of these functions is highly specialized and is probably best avoided.
Here is an example that shows typical usage::

    async def coro():
        async with disable_cancellation():
            while True:
                await coro1()
                await coro2()
                async with enable_cancellation():
                    await coro3()   # May be cancelled
                    await coro4()   # May be cancelled

                if await check_cancellation():
                    break   # Bail out!

        await blocking_op()   # Cancellation (if any) delivered here

If you only need to shield a single operation, you can write statements like this::

    async def coro():
        ...
        await disabled_cancellation(some_operation, x, y, z)
        ...

This is shorthand for writing the following::

    async def coro():
        ...
        async with disable_cancellation():
            await some_operation(x, y, z)
        ...

See the section on cancellation in the Curio Developer's Guide for more detailed information.

Performing External Work
------------------------
.. module:: curio.workers

Sometimes you need to perform work outside the kernel.  This includes CPU-intensive
calculations and blocking operations.  Use the following functions to do that:

.. asyncfunction:: run_in_process(callable, *args)

   Run ``callable(*args)`` in a separate process and returns
   the result.  If cancelled, the underlying
   worker process (if started) is immediately cancelled by a ``SIGTERM``
   signal.

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
dependencies, have substantially less communication overhead, and more
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

I/O Layer
---------

.. module:: curio.io

I/O in curio is performed by classes in :mod:`curio.io` that
wrap around existing sockets and streams.  These classes manage the
blocking behavior and delegate their methods to an existing socket or
file.

Socket
^^^^^^

The :class:`Socket` class is used to wrap existing an socket.  It is compatible with
sockets from the built-in :mod:`socket` module as well as SSL-wrapped sockets created
by functions by the built-in :mod:`ssl` module.  Sockets in curio should be fully
compatible most common socket features.

.. class:: Socket(sockobj)

   Creates a wrapper the around an existing socket *sockobj*.  This socket
   is set in non-blocking mode when wrapped.  *sockobj* is not closed unless
   the created instance is explicitly closed or used as a context manager.

The following methods are redefined on :class:`Socket` objects to be
compatible with coroutines.  Any socket method not listed here will be
delegated directly to the underlying socket. Be aware
that not all methods have been wrapped and that using a method not
listed here might block the kernel or raise a :py:exc:`BlockingIOError`
exception.

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

   Wait for a new connection.  Returns a tuple `(sock, address)`.

.. asyncmethod:: Socket.connect(address)

   Make a connection.

.. asyncmethod:: Socket.connect_ex(address)

   Make a connection and return an error code instead of raising an exception.

.. asyncmethod:: Socket.close()

   Close the connection.  This method is not called on garbage collection.

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
   method below.

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

FileStream
^^^^^^^^^^

The :class:`FileStream` class puts a non-blocking wrapper around an
existing file-like object.  Certain other functions in curio use this
(e.g., the :meth:`Socket.makefile` method).

.. class:: FileStream(fileobj)

   Create a file-like wrapper around an existing file.  *fileobj* must be in
   in binary mode.  The file is placed into non-blocking mode
   using ``os.set_blocking(fileobj.fileno())``.  *fileobj* is not
   closed unless the resulting instance is explicitly closed or used
   as a context manager.

The following methods are available on instances of :class:`FileStream`:

.. asyncmethod:: FileStream.read(maxbytes=-1)

   Read up to *maxbytes* of data on the file. If omitted, reads as
   much data as is currently available and returns it.

.. asyncmethod:: FileStream.readall()

   Return all of the data that's available on a file up until an EOF is read.

.. asyncmethod:: FileStream.readline()

   Read a single line of data from a file.  

.. asyncmethod:: FileStream.readlines()

   Read all of the lines from a file. If cancelled, the ``lines_read`` attribute of
   the resulting exception contains all of the lines that were read so far.

.. asyncmethod:: FileStream.write(bytes)

   Write all of the data in *bytes* to the file.

.. asyncmethod:: FileStream.writelines(lines)

   Writes all of the lines in *lines* to the file.  If cancelled, the ``bytes_written``
   attribute of the exception contains the total bytes written so far.

.. asyncmethod:: FileStream.flush()

   Flush any unwritten data from buffers to the file.

.. asyncmethod:: FileStream.close()

   Flush any unwritten data and close the file.  This method is not
   called on garbage collection.

.. method:: FileStream.blocking()

   A context manager that temporarily places the stream into blocking mode and
   returns the raw file object used internally.  This can be used if you need
   to pass the file to existing synchronous code.

Other file methods (e.g., ``tell()``, ``seek()``, etc.) are available
if the supplied ``fileobj`` also has them.

A ``FileStream`` may be used as an asynchronous context manager.  For example::

    async with stream:
        #  Use the stream object
        ...
    # stream closed here

SocketStream
^^^^^^^^^^^^

The :class:`SocketStream` class puts a non-blocking file-like interface
around a socket.  This is normally created by the :meth:`Socket.as_stream()` method.

.. class:: SocketStream(sock)

   Create a file-like wrapper around an existing socket.  *sock* must be a
   ``socket`` instance from Python's built-in ``socket`` module. The
   socket is placed into non-blocking mode.  *sock* is not closed unless
   the resulting instance is explicitly closed or used as a context manager.

A ``SocketStream`` instance supports the same methods as ``FileStream`` above.
One subtle issue concerns the ``blocking()`` method below.

.. method:: SocketStream.blocking()

   A context manager that temporarily places the stream into blocking
   mode and returns a raw file object that wraps the underlying
   socket.  It is important to note that the return value of this
   operation is a file created ``open(sock.fileno(), 'rb+',
   closefd=False)``.  You can pass this object to code that is
   expecting to work with a file.  The file is not closed when garbage
   collected.

socket wrapper module
---------------------

.. module:: curio.socket

The :mod:`curio.socket` module provides a wrapper around the built-in
:mod:`socket` module--allowing it to be used as a stand-in in
curio-related code.  The module provides exactly the same
functionality except that certain operations have been replaced by
coroutine equivalents.

.. function:: socket(family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None)

   Creates a :class:`curio.io.Socket` wrapper the around :class:`socket` objects created in the built-in :mod:`socket`
   module.  The arguments for construction are identical and have the same meaning.
   The resulting :class:`socket` instance is set in non-blocking mode.

The following module-level functions have been modified so that the returned socket
objects are compatible with curio:

.. function:: socketpair(family=AF_UNIX, type=SOCK_STREAM, proto=0)
.. function:: fromfd(fd, family, type, proto=0)
.. function:: create_connection(address, source_address)

The following module-level functions have been redefined as coroutines so that they
don't block the kernel when interacting with DNS:

.. asyncfunction:: getaddrinfo(host, port, family=0, type=0, proto=0, flags=0)
.. asyncfunction:: getfqdn(name)
.. asyncfunction:: gethostbyname(hostname)
.. asyncfunction:: gethostbyname_ex(hostname)
.. asyncfunction:: gethostname()
.. asyncfunction:: gethostbyaddr(ip_address)
.. asyncfunction:: getnameinfo(sockaddr, flags)


ssl wrapper module
------------------

.. module:: curio.ssl

The :mod:`curio.ssl` module provides curio-compatible functions for creating an SSL
layer around curio sockets.  The following functions are redefined (and have the same
calling signature as their counterparts in the standard :mod:`ssl` module:

.. asyncfunction:: wrap_socket(*args, **kwargs)

.. asyncfunction:: get_server_certificate(*args, **kwargs)

.. function:: create_default_context(*args, **kwargs)

.. class:: SSLContext

   A redefined and modified variant of :class:`ssl.SSLContext` so that the
   :meth:`wrap_socket` method returns a socket compatible with curio.

Don't attempt to use the :mod:`curio.ssl` module without a careful read of Python's official documentation
at https://docs.python.org/3/library/ssl.html.

For the purposes of curio, it is usually easier to apply SSL to a connection using some of the
high level network functions described in the next section.  For example, here's how you
make an outgoing SSL connection::

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

High Level Networking
---------------------

.. currentmodule:: curio

The following functions are provided to simplify common tasks related to
making network connections and writing servers.

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

   Creates a server for receiving TCP connections on
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

   Creates a Unix domain server on a given
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
----------------------------

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
   This method repeatedly attempts to make a connection if the other
   endpoint is not responding.  Returns a :class:`Connection` instance.

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
   and writing are to take place.

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

Here is an example of a correspoinding consumer program using a channel::

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

ZeroMQ wrapper module
---------------------
.. module:: curio.zmq

The :mod:`curio.zmq` module provides an async wrapper around the third party
pyzmq library for communicating via ZeroMQ.   You use it in the same way except
that certain operations are replaced by async functions.

.. class:: Context(*args, **kwargs)

   An asynchronous subclass of ``zmq.Context``. It has the same arguments
   and methods as the synchronous class.   Create ZeroMQ sockets using the
   ``socket()`` method of this class.

Sockets created by the :class:`curio.zmq.Context()` class have the following
methods replaced by asynchronous versions:

.. asyncmethod:: Socket.send(data, flags=0, copy=True, track=False)
.. asyncmethod:: Socket.recv(flags=0, copy=True, track=False)
.. asyncmethod:: Socket.send_multipart(msg_parts, flags=0, copy=True, track=False)
.. asyncmethod:: Socket.recv_multipart(flags=0, copy=True, track=False)
.. asyncmethod:: Socket.send_pyobj(obj, flags=0, protocol=pickle.DEFAULT_PROTOCOL)
.. asyncmethod:: Socket.recv_pyobj(flags=0)
.. asyncmethod:: Socket.send_json(obj, flags=0, **kwargs)
.. asyncmethod:: Socket.recv_json(flags, **kwargs)
.. asyncmethod:: Socket.send_string(u, flags=0, copy=True, encoding='utf-8')
.. asyncmethod:: Socket.recv_string(flags=0, encoding='utf-8')

To run a Curio application that uses ZeroMQ, a special selector must be given
to the Kernel.  You can either do this::

   from curio.zmq import ZMQSelector
   from curio import run

   async def main():
       ...

   run(main(), selector=ZMQSelector())

Alternative, you can use the ``curio.zmq.run()`` function like this::

   from curio.zmq import run

   async def main():
       ...

   run(main())

Here is an example of task that uses a ZMQ PUSH socket::

    import curio.zmq as zmq

    async def pusher(address):
        ctx = zmq.Context()
        sock = ctx.socket(zmq.PUSH)
        sock.bind(address)
        for n in range(100):
            await sock.send(b'Message %d' % n)
        await sock.send(b'exit')

    if __name__ == '__main__':
        zmq.run(pusher('tcp://*:9000'))

Here is an example of a Curio task that receives messages::

    import curio.zmq as zmq

    async def puller(address):
        ctx = zmq.Context()
        sock = ctx.socket(zmq.PULL)
        sock.connect(address)
        while True:
            msg = await sock.recv()
            if msg == b'exit':
                break
            print('Got:', msg)

    if __name__ == '__main__':
        zmq.run(puller('tcp://localhost:9000'))

subprocess wrapper module
-------------------------
.. module:: curio.subprocess

The :mod:`curio.subprocess` module provides a wrapper around the built-in
:mod:`subprocess` module.

.. class:: Popen(*args, **kwargs)

   A wrapper around the :class:`subprocess.Popen` class.  The same arguments are
   accepted. On the resulting :class:`~subprocess.Popen` instance, the
   :attr:`~subprocess.Popen.stdin`, :attr:`~subprocess.Popen.stdout`, and
   :attr:`~subprocess.Popen.stderr` file attributes have been wrapped by the
   :class:`curio.io.FileStream` class. You can use these in an asynchronous
   context.

Here is an example of using :class:`Popen` to read streaming output off of a
subprocess with curio::

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

file wrapper module
---------------------

.. module:: curio.file

One problem concerning coroutines and async concerns access to files on the
normal file system.  Yes, you can use the built-in ``open()`` function, but
what happens afterwards is hard to predict.  Internally, the operating
system might have to access a disk drive or perform networking of its own.
Either way, the operation might take a long time to complete and while it does,
the whole Curio kernel will be blocked.  You really don't want that--especially
if the system is under heavy load.

The :mod:`curio.file` module provides an asynchronous compatible
replacement for the built-in ``open()`` function and associated file
objects, should you want to read and write traditional files on the
filesystem.  The underlying implementation avoids blocking.  How this
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

:class:`AsyncFile` objects should always be used as an asynchronous
context manager.  For example::

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
occur with you realizing it.  If you know what you're doing and you
need to access the underlying file in synchronous code, use the
`blocking()` context manager like this::

    async with open(filename) as f:
        ...
        # Pass to synchronous code (danger: might block)
        with f.blocking() as sync_f:
             # Use synchronous I/O operations
             data = sync_f.read()
             ...

Synchronization Primitives
--------------------------
.. currentmodule:: None

The following synchronization primitives are available. Their behavior
is similar to their equivalents in the :mod:`threading` module.  None
of these primitives are safe to use with threads created by the
built-in :mod:`threading` module.

.. class:: Event()

   An event object.

:class:`Event` instances support the following methods:

.. method:: Event.is_set()

   Return ``True`` if the event is set.

.. method:: Event.clear()

   Clear the event.

.. asyncmethod:: Event.wait()

   Wait for the event.

.. asyncmethod:: Event.set()

   Set the event. Wake all waiting tasks (if any).

Here is an Event example::

    import curio

    async def waiter(evt):
        print('Waiting')
        await evt.wait()
        print('Running')

    async def main():
        evt = curio.Event()
	# Create a few waiters
        await curio.spawn(waiter(evt))
        await curio.spawn(waiter(evt))
        await curio.spawn(waiter(evt))

        await curio.sleep(5)

	# Set the event. All waiters should wake up
	await evt.set()

    curio.run(main)

.. class:: Lock()

   This class provides a mutex lock.  It can only be used in tasks. It is not thread safe.

:class:`Lock` instances support the following methods:

.. asyncmethod:: Lock.acquire()

   Acquire the lock.

.. asyncmethod:: Lock.release()

   Release the lock.

.. method:: Lock.locked()

   Return ``True`` if the lock is currently held.

The preferred way to use a Lock is as an asynchronous context manager. For example::

    import curio

    async def child(lck):
        async with lck:
            print('Child has the lock')

    async def main():
        lck = curio.Lock()
        async with lck:
            print('Parent has the lock')
            await curio.spawn(child(lck))
            await curio.sleep(5)

    curio.run(main())

Note that due to the asynchronous nature of the context manager, the
lock could be acquired by another waiter before the current task
executes the first line after the context, which might surprise a user::

    lck = Lock()
    async def foo():
        async with lck:
            print('locked')
            # since the actual call to lck.release() will be done before
            # exiting the context, some other waiter coroutine could be
            # scheduled to run before we actually exit the context
        print('This line might be executed after'
              'another coroutine acquires this lock')

.. class:: RLock()

   This class provides a recursive lock funtionality, that could be acquired multiple times
   within the same task. The behavior of this lock is identical to the ``threading.RLock``,
   except that the owner of the lock will be a task, wich acquired it, instead of a thread.


:class:`RLock` instances support the following methods:

.. asyncmethod:: RLock.acquire()

   Acquire the lock, incrementing the recursion by 1. Can be used multiple times within
   the same task, that owns this lock.

.. asyncmethod:: RLock.release()

   Release the lock, decrementing the recursion level by 1. If recursion level reaches 0,
   the lock is unlocked. Raises ``RuntimeError`` if called not by the owner or if lock
   is not locked.

.. method:: RLock.locked()

   Return ``True`` if the lock is currently held, i.e. recursion level is greater than 0.

.. class:: Semaphore(value=1)

   Create a semaphore.  Semaphores are based on a counter.  If the count is greater
   than 0, it is decremented and the semaphore is acquired.  Otherwise, the task
   has to wait until the count is incremented by another task.

.. class:: BoundedSemaphore(value=1)

   This class is the same as :class:`Semaphore` except that the
   semaphore value is not allowed to exceed the initial value.

Semaphores support the following methods:

.. asyncmethod:: Semaphore.acquire()

   Acquire the semaphore, decrementing its count.  Blocks if the count is 0.

.. asyncmethod:: Semaphore.release()

   Release the semaphore, incrementing its count. Never blocks.

.. method:: Semaphore.locked()

   Return ``True`` if the Semaphore is locked.

.. attribute:: Semaphore.value

   A read-only property giving the current value of the semaphore.

.. attribute:: BoundedSemaphore.bound

   A read-only property giving the upper bound of a bounded semaphore.

Like locks, semaphores support the async-with statement.  A common use of semaphores is to
limit the number of tasks performing an operation.  For example::

    import curio

    async def worker(sema):
        async with sema:
            print('Working')
            await curio.sleep(5)

    async def main():
         sema = curio.Semaphore(2)     # Allow two tasks at a time

         # Launch a bunch of tasks
         for n in range(10):
             await curio.spawn(worker(sema))

         # After this point, you should see two tasks at a time run. Every 5 seconds.

    curio.run(main())

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

Condition variables are often used to signal between tasks.  For example, here is a simple producer-consumer
scenario::

    import curio
    from collections import deque

    items = deque()
    async def consumer(cond):
        while True:
            async with cond:
                while not items:
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

Queues
------
If you want to communicate between tasks, it's usually much easier to use
a :class:`Queue` instead.

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

   Returns an item from the queue.

.. asyncmethod:: Queue.put(item)

   Puts an item on the queue.

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

.. class:: PriorityQueue(maxsize=0)

  Creates a priority queue with a maximum number of elements in *maxsize*.

In a :class:`PriorityQueue` items are retrieved in priority order with the
lowest priority first::

    import curio

    async def main():
        q = curio.PriorityQueue()
        await q.put((0, 'highest priority'))
        await q.put((100, 'very low priority'))
        await q.put((3, 'higher priority'))

        while not q.empty():
            print(await q.get())

    curio.run(main())


This will output
::

    (0, 'highest priority')
    (3, 'higher priority')
    (100, 'very low priority')

.. class:: LifoQueue(maxsize=0)

    A queue with "Last In First Out" retrieving policy

::

    import curio

    async def main():
        q = curio.LifoQueue()
        await q.put('first')
        await q.put('second')
        await q.put('last')

        while not q.empty():
            print(await q.get())

    curio.run(main())

This will output
::

    last
    second
    first

.. class: UniversalQueue(maxsize=0, withfd=False)

   A queue that can be safely used from both Curio tasks and threads.  
   The same programming API is used for both worlds, but ``await`` is
   required for asynchronous operations.  When the queue is no longer
   in use, the ``shutdown()`` method should be called to terminate
   an internal helper-task.   The ``withfd`` option specifies whether
   or not the queue should optionally set up an I/O loopback that
   allows it to be polled by a foreign event loop.

Here is an example a producer-consumer problem with a ``UniversalQueue``::

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

If the ``withfd=True`` option is given to a ``UniveralQueue``, it additionally
has a ``fileno()`` method that can be passed to various functions that might
poll for I/O events.  When enabled, putting something in the queue will also
write a byte of I/O.  This might be useful if trying to pass data from Curio
to a foreign event loop.

Synchronizing with Threads and Processes
----------------------------------------
Curio's synchronization primitives aren't safe to use with externel threads or
processes.   However, Curio can work with existing thread or process-level
synchronization primitives if you use the :func:`abide` function.

.. asyncfunction:: abide(op, *args, reserve_thread=False)

   Execute an operation in a manner that safely works with async code.
   If ``op`` is a coroutine function, then ``op(*args)`` is
   returned.  If ``op`` is a synchronous function, then
   ``block_in_thread(op, *args)`` is returned.  In both
   cases, you would use ``await`` to obtain the result.  If ``op`` is
   an asynchronous context manager, it is returned unmodified.  If
   ``op`` is a synchronous context manager, it is wrapped in a manner
   that carries out its execution in a backing thread.  For this
   latter case, a special keyword argument ``reserve_thread=True`` may be
   given that instructs Curio to use the same backing thread for the
   entire duraction of the context manager.

The main use of this function is in code that wants to safely
synchronize curio with threads and processes. For example, here is how
you would synchronize a thread with a curio task using a threading
lock::

    import curio
    import threading
    import time

    # A curio task
    async def child(lock):
        async with curio.abide(lock):
            print('Child has the lock')

    # A thread
    def parent(lock):
        with lock:
             print('Parent has the lock')
             time.sleep(5)

    lock = threading.Lock()
    threading.Thread(target=parent, args=(lock,)).start()
    curio.run(child(lock))

If you wanted to trigger or wait for a thread-event, you might do this::

    import curio
    import threading

    evt = threading.Event()

    async def worker():
        await abide(evt.wait)
        print('Working')
        ...

    def main():
        ...
        evt.set()
        ...

For condition variables and reentrant locks, you should use
``reserve_thread=True`` keyword argument to make sure the same thread is used
throughout the block. For example::

    import curio
    import threading
    import collections

    # A thread
    def producer(cond, items):
        for n in range(10):
            with cond:
                 items.append(n)
                 cond.notify()
        print('Producer done')

    # A curio task
    async def consumer(cond, items):
        while True:
            async with abide(cond, reserve_thread=True) as c:
	        while not items:
                    await c.wait()
                item = items.popleft()
                if item is None:
                    break
                print('Consumer got:', item)
        print('Consumer done')

    cond = threading.Condition()
    items = collections.deque()
    
    threading.Thread(target=producer, args=(cond, items)).start()
    curio.run(consumer(cond, items))

A notable feature of :func:`abide()` is that it also accepts Curio's
own synchronization primitives.  Thus, you can write code that
works independently of the lock type.  For example, the first locking
example could be rewritten as follows and the child would still work::

    import curio

    # A curio task (works with any lock)
    async def child(lock):
        async with curio.abide(lock):
            print('Child has the lock')

    # Another curio task
    async def main():
        lock = curio.Lock()
        async with lock:
             print('Parent has the lock')
             await curio.spawn(child(lock))
             await curio.sleep(5)

    curio.run(main())

A special circle of hell awaits code that combines the use of
the ``abide()`` function with task cancellation.  Although
cancellation is mostly supported, there are a few things to keep in mind
about it.  First, if you are using ``abide(func, arg1, arg2, ...)`` to
run a synchronous function, that function will fully run to completion
in a separate thread regardless of the cancellation.  So, if there are
any side-effects associated with that code executing, you'll need to
take them into account.  Second, if you are using ``async with
abide(lock)`` with a thread-lock and a cancellation request is
received while waiting for the ``lock.__enter__()`` method to execute,
a background thread continues to run waiting for the eventual lock
acquisition.  Once acquired, curio releases it again.  However, fully
figuring out what's happening might be mind-bending.

The ``abide()`` function can be used to synchronize with a thread
reentrant lock (e.g., ``threading.RLock``).  However, reentrancy is
not supported.  Each lock acquisition using ``abide()`` involves a
different backing thread.  Repeated acquisitions would violate the
constraint that reentrant locks have on only being acquired by a
single thread.

All things considered, it's probably best to try and avoid code that
synchronizes Curio tasks with threads.  However, if you must, Curio
abides.

Asynchronous Threads
--------------------

If you need to perform a lot of synchronous operations, but still
interact with Curio, you might consider launching an asynchronous
thread. An asynchronous thread flips the whole world around--instead
of executing synchronous operations using ``run_in_thread()``, you
kick everything out to a thread and perform the asynchronous
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

.. asyncmethod:: cancel()

   Cancels the asynchronous thread.  The behavior is the same as cancellation
   performed on Curio tasks.  An asynchronous thread can only be cancelled
   when it performs blocking operations on asynchronous objects (e.g.,
   using ``AWAIT()``.

Within a thread, the following function can be used to execute a coroutine.

.. function:: AWAIT(coro)

   Execute a coroutine on behalf of an asynchronous thread.  The requested
   coroutine executes in Curio's main execution thread.  The caller is
   blocked until it completes.  If used outside of an asynchronous thread,
   an ``AsyncOnlyError`` exception is raised.  If ``coro`` is not a 
   coroutine, it is returned unmodified.   The reason ``AWAIT`` is all-caps
   is to make it more easily heard when there are all of these coders yelling
   at you to just use pure async code instead of launching a thread. Also, 
   ``await`` is likely to be a reserved keyword in Python 3.7.

Here is a simple example of an asynchronous thread that reads data off a
Curio queue::

    from curio import run, Queue, sleep, CancelledError
    from curio.thread import AsyncThread, AWAIT

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
        t = AsyncThread(target=consumer, args=(q,))
        await t.start()

        for i in range(10):
            await q.put(i)
            await sleep(1)

        await q.join()
        await t.cancel()

    run(main())

Asynchronous threads can also be created using the following decorator.

.. function:: async_thread(callable)

   A decorator that adapts a synchronous callable into an asynchronous
   function that runs an asynchronous thread.

Using this decorator, you can write a function like this::

    @async_thread
    def consumer(queue):
        try:
            while True:
                item = AWAIT(queue.get())
                print('Got:', item)
                AWAIT(queue.task_done())

        except CancelledError:
            print('Consumer goodbye!')
            raise

Now, whenever the code executes (e.g., ``await consumer(q)``), a
thread will automatically be created.   The decorator might also
be useful in combination with ``spawn()`` like this::

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
        t = await spawn(async_thread(consumer)(q))
        ...

Asynchronous threads can use all of Curio's features including
coroutines, asynchronous context managers, asynchronous iterators,
timeouts and more.  For coroutines, use the ``AWAIT()`` function.  For
context managers and iterators, use the synchronous counterpart.  For
example, you could write this::

    from curio.thread import async_thread, AWAIT
    from curio import run, tcp_server

    @async_thread
    def echo_client(client, addr):
        print('Connection from:', addr)
        with client:
            f = client.as_stream()
            for line in f:
                AWAIT(client.sendall(line))
        print('Client goodbye')

    run(tcp_server('', 25000, echo_client))

In this code, the ``with client`` and ``for line in f`` statements are
actually executing asynchronous code behind the scenes.

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
threads.  For example, this code actually runs::

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

Signals
-------

One way to manage Unix signals is to use the :class:`SignalQueue` class.
This class operates as a queue, but you use it with an asynchronous context
manager to enable the delivery of signals.  The usage looks like this::

    import signal

    async def coro():
        ...
        async with SignalQueue(signal.SIGUSR1, signal.SIGHUP) as sig_q:
              ...
              signo = await sig_q.get()
              print('Got signal', signo)
              ...

For all of the statements inside the context-manager, signals will be
queued in the background.  The ``sig_q.get()`` operation will return
received signals one at a time from the queue.  Even though this queue
contains signals as they were received by Python, be aware that
"reliable signaling" is not guaranteed.  Python only runs signal
handlers periodically in the background and multiple signals might be
collapsed into a single signal delivery.

Another way to receive signals is to use the :class:`SignalEvent` class.
This is particularly useful for one-time signals such as the keyboard
interrupt or ``SIGTERM`` signal.  Here's an example of how you might
use a signal event to shutdown a task::

    Goodbye = SignalEvent(signal.SIGINT, signal.SIGTERM)

    async def child():
        while True:
            print('Spinning')
            await sleep(1)

    async def coro():
        task = await spawn(child)
        await Goodbye.wait()
	print('Got signal. Goodbye')    
	await task.cancel()

.. class:: SignalQueue(*signals)

   Create a queue for receiving signals. *signals* is one or more
   signals as defined in the built-in :mod:`signal` module.  A 
   ``SignalQueue`` is a proper queue.  Use the ``get()`` method
   to receive a signal.  Other queue methods can be used as well.
   For example, you can call ``put()`` to manually put a signal
   number on the queue if you want (possibly useful in testing).
   The queue must be used as an asynchronous-context manager for
   signal delivery to enabled.

.. class:: SignalEvent(*signals)

   Create an event that allows signal waiting.  Use the ``wait()``
   method to wait for arrival.  This is a proper ``Event`` object.
   You can use other methods such as ``set()`` or ``is_set()``.
   		 

The following functions are also defined for signal management::

.. function::ignore_signals(signals)

   Return a context manager in which signals are ignored. ``signals`` is
   a set of signal numbers from the ``signal`` module.  This
   function may only be called from Python's main execution thread.
   Note that signals are not delivered asynchronous to Curio via 
   callbacks (they only come via queues or events). Because of this,
   it's rarely necessary to mask signals.  You may be better off
   blocking cancellation with the ``disable_cancellation()`` function
   instead.

.. function::enable_signals(signals)

   Returns a context manager in which the Curio signaling system is
   initialized for a given set of signals.  This function may only
   be called by Python's main execution thread and is only needed
   if you intend to run Curio in a separate thread.  ``signals``
   should specify the complete set of signals that will be caught
   in the application.   The main reason this is needed is that
   signals can only be initialized in Python's main thread. If you
   don't do this and you attempt to run Curio in a separate thread,
   the other signal-related functionality will fail.

These last two functions are mainly intended for use in setting up
the runtime environment for Curio.  For example, if you needed to run
Curio in a separate thread and your code involved signal handling,
you'd need to do this::

    import threading
    import curio
    import signal

    allowed_signals = { signal.SIGINT, signal.SIGTERM, signal.SIGUSR1 }

    async def main():
         ...

    if __name__ == '__main__':
       with curio.enable_signals(allowed_signals):
           t = threading.Thread(target=curio.run, args=(main,))
           t.start()
	   ...
           t.join()

Again, keep in mind you don't need to do this is Curio is running in the
main thread.  Running in a separate thread is more of a special case.

Asynchronous Metaprogramming
----------------------------
.. module:: curio.meta

The :mod:`curio.meta` module provides some decorators and metaclasses that might
be useful if writing larger programs involving coroutines.

.. class:: AsyncABC()

   A base class that provides the functionality of a normal abstract base class,
   but additionally enforces coroutine-correctness on methods in subclasses. That is,
   if a method is defined as a coroutine in a parent class, then it must also be
   a coroutine in child classes.

Here is an example::

    from curio.abc import AsyncABC, abstractmethod

    class Base(AsyncABC):
        @abstractmethod
        async def spam(self):
            pass

        @abstractmethod
        async def grok(self):
            pass

    class Child(Base):
        async def spam(self):
            pass

    c = Child()   # Error -> grok() not defined

    class Child2(Base):
        def spam(self):     # Error -> Not defined using async def
            pass

        async def grok(self):
            pass

The enforcement of coroutines is applied to all methods.  Thus, the following
classes would also generate an error::

    class Base(AsyncABC):
        async def spam(self):
            pass

        async def grok(self):
            pass

    class Child(Base):
        def spam(self):     # Error -> Not defined using async def
            pass


.. class:: AsyncObject()

   A base class that provides all of the functionality of ``AsyncABC``, but additionally
   requires instances to be created inside of coroutines.   The ``__init__()`` method
   must be defined as a coroutine and may call other coroutines.

Here is an example using ``AsyncObject``::

    from curio.meta import AsyncObject

    class Spam(AsyncObject):
        async def __init__(self, x, y):
            self.x = x
            self.y = y

    # To create an instance
    async def func():
        s = await Spam(2, 3)
        ...

.. function:: blocking(func)

   A decorator that indicates that the function performs a blocking operation.
   If the function is called from within a coroutine, the function is executed
   in a separate thread and ``await`` is used to obtain the result.  If the
   function is called from normal synchronous code, then the function executes
   normally.  The Curio ``run_in_thread()`` coroutine is used to execute the
   function in a thread.

.. function:: cpubound(func)

   A decorator that indicates that the function performs CPU intensive work.
   If the function is called from within a coroutine, the function is executed
   in a separate process and ``await`` is used to obtain the result.  If the
   function is called from normal synchronous code, then the function executes
   normally.  The Curio ``run_in_process()`` coroutine is used to execute the
   function in a process.

The ``@blocking`` and ``@cpubound`` decorators are interesting in that they make
normal Python functions usable from both asynchronous and synchronous code.
For example, consider this example::

    import curio
    from curio.meta import blocking
    import time

    @blocking
    def slow(name):
        time.sleep(30)
        return 'Hello ' + name

    async def main():
        result = await slow('Dave')      # Async execution
        print(result)

    if __name__ == '__main__':
        result = slow('Guido')           # Sync execution
        print(result)
        curio.run(main())

In this example, the ``slow()`` function can be used from both
coroutines and normal synchronous code.  However, when called in
a coroutine, ``await`` must be used.  Behind the scenes, the function
runs in a thread--preventing the function from blocking the
execution of other coroutines.

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

.. exception:: TimeoutCancellationError

   Exception raised in a coroutine if it has been cancelled due to a timeout,
   but not one related to the inner-most timeout operation.

.. exception:: TaskError

   Exception raised by the :meth:`Task.join` method if an uncaught exception
   occurs in a task.  It is a chained exception. The ``__cause__`` attribute
   contains the exception that causes the task to fail.

Low-level Kernel System Calls
-----------------------------
.. module:: curio.traps

The following system calls are available, but not typically used
directly in user code.  They are used to implement higher level
objects such as locks, socket wrappers, and so forth. If you find
yourself using these, you're probably doing something wrong--or
implementing a new curio primitive.   These calls are found in the
``curio.traps`` submodule.

Traps come in two flavors: *blocking* and *synchronous*. A blocking
trap might block for an indefinite period of time while allowing other
tasks to run, and always checks for and raises any pending timeouts or
cancellations. A synchronous trap is implemented by trapping into the
kernel, but semantically it acts like a regular synchronous function
call. Specifically, this means that it always returns immediately
without running any other task, and that it does *not* act as a
cancellation point.

.. asyncfunction:: _read_wait(fileobj)

   Blocking trap. Sleep until data is available for reading on
   *fileobj*.  *fileobj* is any file-like object with a `fileno()`
   method.

.. asyncfunction:: _write_wait(fileobj)

   Blocking trap. Sleep until data can be written on *fileobj*.
   *fileobj* is any file-like object with a `fileno()` method.

.. asyncfunction:: _future_wait(future)

   Blocking trap. Sleep until a result is set on *future*.  *future*
   is an instance of :py:class:`concurrent.futures.Future`.

.. asyncfunction:: _cancel_task(task)

   Synchronous trap. Cancel the indicated *task*.

.. asyncfunction:: _scheduler_wait(sched, state_name)

   Blocking trap.  Go to sleep on a kernel scheduler primitive. *sched* is an instance of
   ``curio.sched.SchedBase``. *state_name* is the name of the wait state (used in
   debugging).

.. asyncfunction:: _scheduler_wake(sched, n=1, value=None, exc=None)

   Synchronous trap. Reschedule one or more tasks from a
   kernel scheduler primitive. *n* is the
   number of tasks to release. *value* and *exc* specify the return
   value or exception to raise in the task when it resumes execution.

.. asyncfunction:: _get_kernel()

   Synchronous trap. Get a reference to the running ``Kernel`` object.

.. asyncfunction:: _get_current()

   Synchronous trap. Get a reference to the currently running ``Task``
   instance.

.. asyncfunction:: _set_timeout(seconds)

   Synchronous trap. Set a timeout in the currently running
   task. Returns the previous timeout (if any)

.. asyncfunction:: _unset_timeout(previous)

   Synchronous trap. Unset a timeout in the currently running
   task. *previous* is the value returned by the _set_timeout() call
   used to set the timeout.

.. asyncfunction:: _clock():

   Synchronous trap. Returns the current time according to the Curio
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
