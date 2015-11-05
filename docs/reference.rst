Curio Reference Manual
======================

This manual lists the basic functionality provided by curio.

The Kernel
----------

The kernel is responsible for running all of the tasks.  It should normally be created
and used in the main execution thread.

.. class:: Kernel(selector=None, with_monitor=False)

   Create an instance of a curio kernel.  If *selector* is given, it should be
   an instance of a selector from the :mod:`selectors` module.  If not given,
   then ``selectors.DefaultSelector`` is used to poll for I/O.
   If *with_monitor* is ``True``, the monitor task executes in the background.
   The monitor responds to the keyboard-interrupt and allows you to inspect
   the state of the running kernel.

There are only a few methods that may be used on a ``Kernel`` outside of coroutines.


.. method:: Kernel.run(coro=None, pdb=False, log_errors=True)

   Runs the kernel until all non-daemonic tasks have finished execution.
   *coro* is a coroutine to run as a task.  If omitted, then tasks should
   have already been added using the ``add_task`` method below.
   If *pdb* is ``True``, then the kernel enters the Python debugger if any
   task crashes with an uncaught exception.  If *log_errors* is ``True``, then
   uncaught exceptions in tasks are logged.

.. method:: Kernel.add_task(coro, daemon=False)

   Adds a new task to the kernel.  *coro* is a newly instantiated coroutine.
   If *daemon* is ``True``, the task is created without a parent and runs in
   the background.   Returns a :class:`Task` instance.  This method may not
   be used to add a task to a running kernel and may not be used inside a
   coroutine.

.. method:: Kernel.stop()

   Force the kernel to stop execution.  Since the kernel normally runs in the main
   thread, this operation would normally have to be performed in a separate thread
   or possibly inside a coroutine.  This method merely sets a flag in the kernel
   and returns immediately.  The kernel will stop only after the currently running
   task yields.

.. method:: Kernel.shutdown()

   Performs a clean shutdown of the kernel by issuing a cancellation request to
   all remaining tasks (including daemonic tasks).  This function will not return
   until all tasks have terminated.  This method may only be invoked on a kernel
   that is not actively running.  It may not be used inside coroutines or from
   separate threads.  Normally, you would not call this method since the kernel
   runs until all tasks have terminated anyways.  The main use case would be cleaning up
   after a premature kernel shutdown due to a crash, system exit, or some other
   event.

Tasks
-----

Once the kernel is running, a coroutine can create a new task using the following
function:

.. function:: await new_task(coro, daemon=False)

   Create a new task.  *coro* is a newly called coroutine.  Does not
   return to the caller until the new task has been scheduled and executed for at least
   one cycle.  Returns a :class:`Task` instance as a result.  The *daemon* option,
   if supplied, creates the new task without a parent.  The task will run indefinitely
   in the background.  Note: The kernel only runs as long as there are non-daemonic
   tasks to execute.

Tasks created by :func:`new_task()` are represented as a :class:`Task` instance.
It is illegal to create a :class:`Task` instance directly by calling the class.
The following methods are available on tasks:

.. method:: await Task.join(timeout=None)

   Wait for the task to terminate.  Returns the value returned by the task or
   raises a :exc:`curio.TaskError` exception if the task failed with an exception.
   This is a chained exception.  The `__cause__` attribute of this
   exception contains the actual exception raised in the task.

.. method:: await Task.cancel(*, timeout=None, exc=CancelledError)

   Cancels the task.  This raises a :exc:`curio.CancelledError` exception in the
   task which may choose to handle it.  Does not return until the
   task is actually cancelled. If you want to change the exception raised,
   supply a different exception as the *exc* argument.

.. method:: await Task.cancel_children(*, timeout=None, exc=CancelledError)

   Cancels all of the immediate children of this task. *exc* specifies
   a different exception if desired.

The following public attributes are available of ``Task`` instances:

.. attribute:: Task.id

   The task's integer id.

.. attribute:: Task.coro

   The coroutine associated with the task.

.. attribute:: Task.state

   The name of the task's current state.  Printing it can be potentially useful
   for debugging.

.. attribute:: Task.exc_info

   A tuple of exception information obtained from ``sys.exc_info()`` if the
   task crashes for some reason.  Potentially useful for debugging.

.. attribute:: Task.children

   A set of the immediate child tasks created by this task.  Useful if writing
   code that needs to supervise a collection of tasks.  Be aware that the
   contents of the set may change as tasks are scheduled.  To safely iterate
   and perform asynchronous operations, make a copy first.

If you need to make a task sleep for awhile, use the following function:

.. function:: await sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, the
   kernel merely switches to the next task (if any).


Performing External Work
------------------------

Sometimes you need to perform work outside the kernel.  This includes CPU-intensive
calculations and blocking operations.  Use the following functions to do that:

.. function:: await run_cpu_bound(callable, *args, timeout=None)

   Run ``callable(*args)`` in a process pool created by :mod:`concurrent.futures.ProcessPoolExecutor`.
   Returns the result.

.. function:: await run_blocking(callable, *args, timeout=None)

   Run ``callable(*args)`` in a thread pool created by :mod:`concurrent.futures.ThreadPoolExecutor`.
   Returns the result.

.. function:: await run_in_executor(exc, callable, *args, timeout=None)

   Run ``callable(*args)`` callable in a user-supplied executor and returns the result.
   *exc* is an executor from the :mod:`concurrent.Futures` module in the standard library.

.. function:: set_cpu_executor(exc)

   Set the default executor used for CPU-bound processing.

.. function:: set_blocking_executor(exc)

   Set the default executor used for blocking processing.

Note that the callables supplied to these functions are only given positional arguments.
If you need to pass keyword arguments use ``functools.partial()`` to do it. For example::

   from functools import partial
   await run_blocking(partial(callable, arg1=value, arg2=value))

I/O Layer
---------
I/O in curio is performed by classes in :mod:`curio.io` that
wrap around existing sockets and streams.  These classes manage the
blocking behavior and delegate their methods to an existing socket or
file.

Socket
^^^^^^

The :class:`Socket` class is used to wrap existing an socket.  It is compatible with
sockets from the built-in :mod:`socket` module as well as SSL-wrapped sockets created
by functions by the built-in :mod:`ssl` module.  Sockets in curio should be fully
compatible with timeouts and other common socket features.

.. class:: Socket(sockobj)

   Creates a wrapper the around an existing socket *sockobj*.  This socket
   is set in non-blocking mode when wrapped.

The following methods are redefined on :class:`Socket` objects to be
compatible with coroutines.  Any socket method not listed here will be
delegated directly to the underlying socket. Be aware
that not all methods have been wrapped and that using a method not
listed here might block the kernel or raise a ``BlockingIOError`` exception.

.. method:: await Socket.recv(maxbytes, flags=0)

   Receive up to *maxbytes* of data.

.. method:: await Socket.recv_into(buffer, nbytes=0, flags=0)

   Receive up to *nbytes* of data into a buffer object.

.. method:: await Socket.recvfrom(maxsize, flags=0)

   Receive up to *maxbytes* of data.  Returns a tuple `(data, client_address)`.

.. method:: await Socket.recvfrom_into(buffer, nbytes=0, flags=0)

   Receive up to *nbytes* of data into a buffer object.

.. method:: await Socket.recvmsg(bufsize, ancbufsize=0, flags=0)

   Receive normal and ancillary data.

.. method:: await Socket.recvmsg_into(buffers, ancbufsize=0, flags=0)

   Receive normal and ancillary data.

.. method:: await Socket.send(data, flags=0)

   Send data.  Returns the number of bytes of data actually sent (which may be
   less than provided in *data*).

.. method:: await Socket.sendall(data, flags=0)

   Send all of the data in *data*.

.. method:: await Socket.sendto(data, address)
.. method:: await Socket.sendto(data, flags, address)

   Send data to the specified address.

.. method:: await Socket.sendmsg(buffers, ancdata=(), flags=0, address=None)

   Send normal and ancillary data to the socket.

.. method:: await Socket.accept()

   Wait for a new connection.  Returns a tuple `(sock, address)`.

.. method:: await Socket.connect(address)

   Make a connection.

.. method:: await Socket.connect_ex(address)

   Make a connection and return an error code instead of raising an exception.

.. method:: await Socket.close()

   Close the connection.

.. method:: await do_handshake()

   Perform an SSL client handshake. The underlying socket must have already
   be wrapped by SSL using the ``curio.ssl`` module.

.. method:: Socket.makefile(mode, buffering=0)

   Make a file-like object that wraps the socket.  The resulting file
   object is a :class:`curio.io.Stream` instance that supports
   non-blocking I/O.  *mode* specifies the file mode which must be one
   of ``'rb'`` or ``'wb'``.  *buffering* specifies the buffering
   behavior. By default unbuffered I/O is used.  Note: It is not currently
   possible to create a stream with Unicode text encoding/decoding applied to it
   so those options are not available.

.. method:: Socket.make_streams(buffering=0)

   Make a pair of files for reading and writing.  Returns a tuple ``(reader, writer)``
   where ``reader`` and ``writer`` are streams created by the ``Socket.makefile()`` method.

.. method:: Socket.blocking()

   A context manager that temporarily places the socket into blocking mode and
   returns the raw socket object used internally.  This can be used if you need
   to pass the socket to existing synchronous code.

:class:`Socket` objects may be used as an asynchronous context manager which
causes it to be closed when done. For example::

    async with sock:
        # Use the socket
        ...
    # socket closed here

Stream
^^^^^^

The :class:`Stream` class puts a non-blocking wrapper around an
existing file-like object.  Certain other functions in curio use this
(e.g., the :func:`Socket.makefile()` method).


.. class:: Stream(fileobj)

   Create a file-like wrapper around an existing file.  *fileobj* must be in
   in binary mode.  The file is placed into non-blocking mode
   using :mod:`os.set_blocking(fileobj.fileno())`.

The following methods are available on instances of :class:`Stream`:

.. method:: await Stream.read(maxbytes=-1)

   Read up to *maxbytes* of data on the file. If omitted, reads as
   much data as is currently available and returns it.

.. method:: await Stream.readall()

   Return all of the data that's available on a file up until an EOF is read.

.. method:: await Stream.readline():

   Read a single line of data from a file.

.. method:: await Stream.write(bytes)

   Write all of the data in *bytes* to the file.

.. method:: await Stream.writelines(lines)

   Writes all of the lines in *lines* to the file.

.. method:: await Stream.flush()

   Flush any unwritten data from buffers to the file.

.. method:: await Stream.close()

   Flush any unwritten data and close the file.

.. method:: Stream.settimeout(seconds)

   Sets a timeout on all file I/O operations.  If *seconds* is None, any previously set
   timeout is cleared.

.. method:: Stream.blocking()

   A context manager that temporarily places the stream into blocking mode and
   returns the raw file object used internally.  This can be used if you need
   to pass the file to existing synchronous code.

Other file methods (e.g., ``tell()``, ``seek()``, etc.) are available
if the supplied ``fileobj`` also has them.

Streams may be used as an asynchronous context manager.  For example::

    async with stream:
        #  Use the stream object
        ...
    # stream closed here

socket wrapper module
---------------------
The :mod:`curio.socket` module provides a wrapper around the built-in
:mod:`socket` module--allowing it to be used as a standin in
curio-related code.  The module provides exactly the same
functionality except that certain operations have been replaced by
coroutine equivalents.

.. function:: def socket(family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None)

   Creates a :class:`curio.io.Socket` wrapper the around :class:`socket` objects created in the built-in :mod:`socket`
   module.  The arguments for construction are identical and have the same meaning.
   The resulting :class:`socket` instance is set in non-blocking mode.

The following module-level functions have been modified so that the returned socket
objects are compatible with curio:

.. function:: socketpair(family=AF_UNIX, type=SOCK_STREAM, proto=0)
.. function:: fromfd(fd, family, type, proto=0)
.. function:: create_connection(address, timeout, source_address)

The following module-level functions have been redefined as coroutines so that they
don't block the kernel when interacting with DNS:

.. function:: await getaddrinfo(host, port, family=0, type=0, proto=0, flags=0)
.. function:: await getfqdn(name)
.. function:: await gethostbyname(hostname)
.. function:: await gethostbyname_ex(hostname)
.. function:: await gethostname()
.. function:: await gethostbyaddr(ip_address)
.. function:: await getnameinfo(sockaddr, flags)

subprocess wrapper module
-------------------------
The :mod:`curio.subprocess` module provides a wrapper around the built-in :mod:`subprocess` module.

.. class:: Popen(*args, **kwargs).

   A wrapper around the :class:`subprocess.Popen` class.  The same arguments are accepted.
   On the resulting ``Popen`` instance, the ``stdin``, ``stdout``, and ``stderr`` file
   attributes have been wrapped by the :class:`curio.io.Stream` class. You can use these
   in an asynchronous context.

Here is an example of using ``Popen`` to read streaming output off of a subprocess with curio::

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


.. method:: await Popen.wait(timeout=None)

   Wait for a subprocess to exit.

.. method:: await Popen.communicate(input=b'', timeout=None)

   Communicate with the subprocess, sending the specified input on standard input.
   Returns a tuple ``(stdout, stderr)`` with the resulting output of standard output
   and standard error.

The following functions are also available.  They accept the same arguments as their
equivalents in the :mod:`subprocess` module:

.. function:: await run(args, stdin=None, input=None, stdout=None, stderr=None, shell=False, timeout=None, check=False)

   Run a command in a subprocess.  Returns a :class:`subprocess.CompletedProcess` instance.

.. function:: await check_output(args, stdout=None, stderr=None, shell=False, timeout=None)

   Run a command in a subprocess and return the resulting output. Raises a ``subprocess.CalledProcessError``
   exception if an error occurred.

ssl wrapper module
------------------

The :mod:`curio.ssl` module provides curio-compatible functions for creating an SSL
layer around curio sockets.  The following functions are redefined (and have the same
calling signature as their counterparts in the standard :mod:`ssl` module:

.. function:: wrap_socket(*args, **kwargs)

.. function:: await get_server_certificate(*args, **kwargs)

.. function:: create_default_context(*args, **kwargs)

The :class:`SSLContext` class is also redefined and modified so that the ``wrap_socket()`` method
returns a socket compatible with curio.

Don't attempt to use the ``ssl`` module without a careful read of Python's official documentation
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
        kernel.run(curio.run_server('', 10000, handler, ssl=ssl_context))

High Level Networking
---------------------

The following functions are provided to simplify common tasks related to
making network connections and writing servers.

.. function:: await open_connection(host, port, *, ssl=None, source_addr=None, server_hostname=None, timeout=None)

   Creates an outgoing connection to a server at *host* and *port*. This connection is made using
   the ``socket.create_connection()`` function and might be IPv4 or IPv6 depending on
   the network configuration (although you're not supposed to worry about it).  *ssl* specifies
   whether or not SSL should be used.  *ssl* can be ``True`` or an instance of an ``SSLContext``
   created by the :mod:`curio.ssl` module.  *source_addr* specifies the source address to use
   on the socket.  *server_hostname* specifies the hostname to check against when making SSL
   connections.  It is highly advised that this be supplied to avoid man-in-the-middle attacks.

.. function:: await open_unix_connection(path, *, ssl=None, server_hostname=None):

   Creates a connection to a Unix domain socket with optional SSL applied.

.. function:: create_server(host, port, client_connected_task, *, family=AF_INET, backlog=100, ssl=None, reuse_address=True)

   Creates a ``Server`` instance for receiving TCP connections on a given host and port.
   *client_connected_task* is a coroutine that is to be called to handle each connection.
   Family specifies the address family and is either ``AF_INET`` or ``AF_INET6``.
   *backlog* is the argument to the socket ``listen()`` method.  *ssl* specifies an
   ``SSLContext`` instance to use. *reuse_address* specifies whether to reuse a previously
   used port.   This method does not actually start running the created server.  To
   do that, you need to use ``await Server.serve_forever()`` method on the returned
   ``Server`` instance.   Normally, it's easier to use ``run_server()`` instead. Only
   use ``create_server()`` if you need to do something else with the ``Server`` instance
   for some reason.

.. function:: await run_server(host, port, client_connected_task, *, family=AF_INET, backlog=100, ssl=None, reuse_address=True)

   Creates a server using ``create_server()`` and immediately starts running it.

.. function:: create_unix_server(path, client_connected_task, *, backlog=100, ssl=None)

   Creates a Unix domain server on a given path. *client_connected_task* is a coroutine to
   execute on each connection. *backlog* is the argument given to the socket ``listen()`` method.
   *ssl* is an optional ``SSLContext`` to use if setting up an SSL connection.   Returns a
   ``Server`` instance.  To start running the server use ``await Server.serve_forever()``.

.. function:: await run_unix_server(path, client_connected_task, *, backlog=100, ssl=None)

   Creates a Unix domain server using ``create_unix_server()`` and immediately starts running it.

Synchronization Primitives
--------------------------

The following synchronization primitives are available. Their behavior is
similar to their equivalents in the :mod:`threading` module.  None of these
primitives are safe to use with threads created by the built-in :mod:`threading` module.

.. class:: Event()

   An event object.

:class:`Event` instances support the following methods:

.. method:: Event.is_set()

   Return ``True`` if the event is set.

.. method:: Event.clear()

   Clear the event.

.. method:: await Event.wait(timeout=None)

   Wait for the event with an optional timeout.

.. method:: await Event.set()

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
        await curio.new_task(waiter(evt))
        await curio.new_task(waiter(evt))
        await curio.new_task(waiter(evt))

        await curio.sleep(5)

	# Set the event. All waiters should wake up
	await evt.set()

.. class:: Lock()

   This class provides a mutex lock.  It can only be used in tasks. It is not thread safe.

:class:`Lock` instances support the following methods:

.. method:: await Lock.acquire(timeout=None)

   Acquire the lock.

.. method:: await Lock.release()

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
            await curio.new_task(child(lck))
            await curio.sleep(5)

.. class:: Semaphore(value=1)

   Create a semaphore.  Semaphores are based on a counter.  If the count is greater
   than 0, it is decremented and the semaphore is acquired.  Otherwise, the task
   has to wait until the count is incremented by another task.

.. class:: BoundedSemaphore(value=1)

   This class is the same as :class:`Semaphore` except that the
   semaphore value is not allowed to exceed the initial value.

Semaphores support the following methods:

.. method:: await Semaphore.acquire(timeout=None)

   Acquire the semaphore, decrementing its count.  Blocks if the count is 0.

.. method:: await Semaphore.release()

   Release the semaphore, incrementing its count. Never blocks.

.. method:: Semaphore.locked()

   Return ``True`` if the Semaphore is locked.

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
             await curio.new_task(worker(sema))

         # After this point, you should see two tasks at a time run. Every 5 seconds.

.. class:: Condition(lock=None)

   Condition variable.  *lock* is the underlying lock to use. If none is provided, then
   a :class:`Lock` object is used.

:class:`Condition` objects support the following methods:

.. method:: Condition.locked()

   Return ``True`` if the condition variable is locked.

.. method:: await Condition.acquire(*, timeout=None)

   Acquire the condition variable lock.

.. method:: await Condition.release()

   Release the condition variable lock.

.. method:: await Condition.wait(*, timeout=None)

   Wait on the condition variable with a timeout.  This releases the underlying lock.

.. method:: await Condition.wait_for(predicate, *, timeout=None)

   Wait on the condition variable until a supplied predicate function returns ``True``. *predicate* is
   a callable that takes no arguments.

.. method:: await notify(n=1)

   Notify one or more tasks, causing them to wake from the
   :meth:`Condition.wait` method.

.. method:: await notify_all()

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
         await curio.new_task(producer(cond))
         await curio.new_task(consumer(cond))

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

.. method:: await Queue.get(*, timeout=None)

   Returns an item from the queue with an optional timeout.

.. method:: await Queue.put(item, *, timeout=None)

   Puts an item on the queue with an optional timeout in the event
   that the queue is full.

.. method:: await Queue.join(*, timeout=None)

   Wait for all of the elements put onto a queue to be processed. Consumers
   must call :meth:`Queue.task_done` to indicate completion.

.. method:: await Queue.task_done()

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
        prod_task = await curio.new_task(producer(q))
        cons_task = await curio.new_task(consumer(q))
        await prod_task.join()
        await cons_task.cancel()

Signals
-------

Unix signals are managed by the :class:`SignalSet` class.   This class operates
as an asynchronous context manager.  The recommended usage looks like this::

    import signal

    async def coro():
        ...
        async with SignalSet(signal.SIGUSR1, signal.SIGHUP) as sigset:
              ...
              signo = await sigset.wait()
              print('Got signal', signo)
              ...

For all of the statements inside the context-manager, signals will
be queued.  The `sigset.wait()` operation will return received
signals one at a time from the signal queue.

Signals can be temporarily ignored using a normal context manager::

    async def coro():
        ...
        sigset = SignalSet(signal.SIGINT)
        with sigset.ignore():
              ...
              # Signals temporarily disabled
              ...

Caution: Signal handling only works if the curio kernel is running in Python's
main execution thread.  Also, mixing signals with threads, subprocesses, and other
concurrency primitives is a well-known way to make your head shatter into
small pieces.  Tread lightly.

.. class:: SignalSet(*signals)

   Represents a set of one or more Unix signals.  *signals* is a list of
   signals as defined in the built-in :mod:`signal` module.

The following methods are available on a :class:`SignalSet` instance. They
may only be used in coroutines.

.. method:: await SignalSet.wait(*, timeout=None)

   Wait for one of the signals in the signal set to arrive. Returns the
   signal number of the signal received.  *timeout* gives an optional
   timeout.  Normally this method is used inside an ``async with`` statement
   because this allows received signals to be properly queued.  It can be
   used in isolation, but be aware that this will only catch a single
   signal right at that line of code.  It's possible that you might lose
   signals if you use this method outside of a context manager.

.. method:: SignalSet.ignore()

   Returns a context manager wherein signals from the signal set are
   temporarily disabled.  Note: This is a normal context manager--
   use a normal ``with``-statement.

Exceptions
----------

.. class:: CancelledError

   Exception raised in a coroutine if it has been cancelled.  If ignored, the
   coroutine is silently terminated.  If caught, a coroutine can continue to
   run, but should work to terminate execution.  Ignoring a cancellation
   request and continuing to execute will likely cause some other task to hang.

.. class:: TaskError

   Exception raised by the :meth:`Task.join` method if an uncaught exception
   occurs in a task.  It is a chained exception. The :attr:`__cause__` attribute contains
   the exception that causes the task to fail.

Low-level Kernel System Calls
-----------------------------

The following system calls are available, but not typically used
directly in user code.  They are used to implement higher level
objects such as locks, socket wrappers, and so forth. If you find
yourself using these, you're probably doing something wrong--or
implementing a new curio primitive.

.. function:: await _read_wait(fileobj, timeout=None)

   Sleep until data is available for reading on *fileobj*.  *fileobj* is
   any file-like object with a `fileno()` method.  *timeout*
   gives an optional timeout in seconds.

.. function:: await _write_wait(fileobj, timeout=None)

   Sleep until data can be written on *fileobj*.  *fileobj* is
   any file-like object with a `fileno()` method. *timeout*
   gives an optional timeout in seconds.

.. function:: await _future_wait(future, timeout=None)

   Sleep until a result is set on *future*.  *future* is an instance of
   :class:`Future` as found in the :mod:`concurrent.futures` module.

.. function:: await _join_task(task, timeout=None)

   Sleep until the indicated *task* completes.  The final return value
   of the task is returned if it completed successfully. If the task
   failed with an exception, a ``curio.TaskError`` exception is
   raised.  This is a chained exception.  The ``__cause__`` attribute of this
   exception contains the actual exception raised in the task.

.. function:: await _cancel_task(task, exc=CancelledError, timeout=None)

   Cancel the indicated *task*.  Does not return until the task actually
   completes the cancellation.  Note: It is usually better to use
   ``await task.cancel()`` instead of this function.

.. function:: await _wait_on_queue(kqueue, state_name, timeout=None)

   Go to sleep on a queue. *kqueue* is an instance of a kernel queue
   which is typically a ``collections.deque`` instance. *state_name*
   is the name of the wait state (used in debugging).

.. function:: await _reschedule_tasks(kqueue, n=1, value=None, exc=None)

   Reschedule one or more tasks from a queue. *kqueue* is an instance of a
   kernel queue.  *n* is the number of tasks to release. *value* and *exc*
   specify the return value or exception to raise in the task when it
   resumes execution.

.. function:: await _sigwatch(sigset)

   Tell the kernel to start queuing signals in the given signal set *sigset*.

.. function:: await _sigunwatch(sigset)

   Tell the kernel to stop queuing signals in the given signal set.

.. function:: await _sigwait(sigset, timeout=None)

   Wait for the arrival of a signal in a given signal set. Returns the signal
   number of the received signal.

Again, you're unlikely to use any of these functions directly.  However, here's a small taste
of how they're used.  For example, the ``recv()`` method of ``Socket`` objects
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

This method first tries to receive data.  If none is available, the ``_read_wait()`` call is used to
put the task to sleep until reading can be performed. When it awakes, the receive operation
is retried. Just to emphasize, the ``_read_wait()`` doesn't actually perform any I/O. It's just
scheduling a task for it.

Here's an example of code that implements a mutex lock::

    from collections import deque

    class Lock(object):
        def __init__(self):
            self._acquired = False
            self._waiting = deque()

        async def acquire(self):
            if self._acquired:
                await _wait_on_queue(self._waiting, 'LOCK_ACQUIRE')

        async def release(self):
             if self._waiting:
                 await _reschedule_tasks(self._waiting, n=1)
             else:
                 self._acquired = False

In this code you can see the low-level calls related to managing a wait queue. This
code is not significantly different than the actual implementation of a lock
in curio.   If you wanted to make your own task synchronization objects, the
code would look similar.
