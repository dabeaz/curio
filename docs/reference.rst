Curio Reference Manual
======================

This manual lists the basic functionality provided by curio.

The Kernel
----------

The kernel is responsible for running all of the tasks.  It should normally be created
and used in the main execution thread.

.. class:: Kernel(selector=None, with_monitor=False)

   Create an instance of a curio kernel.  If *selector* is given, it should be
   an instance of a selector from the :mod:`selectors <python:selectors>` module.  If not given,
   then :class:`selectors.DefaultSelector <python:selectors.DefaultSelector>` is used to poll for I/O.
   If *with_monitor* is ``True``, the monitor task executes in the background.
   The monitor responds to the keyboard-interrupt and allows you to inspect
   the state of the running kernel.

There are only a few methods that may be used on a :class:`Kernel` outside of coroutines.

.. method:: Kernel.run(coro=None, pdb=False, log_errors=True)

   Runs the kernel until all non-daemonic tasks have finished execution.
   *coro* is a coroutine to run as a task.  If omitted, then tasks should
   have already been added using the :meth:`add_task` method below.
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

.. asyncfunction:: spawn(coro, daemon=False)

   Create a new task.  *coro* is a newly called coroutine.  Does not
   return to the caller until the new task has been scheduled and executed for at least
   one cycle.  Returns a :class:`Task` instance as a result.  The *daemon* option,
   if supplied, creates the new task without a parent.  The task will run indefinitely
   in the background.  Note: The kernel only runs as long as there are non-daemonic
   tasks to execute.

.. class:: Task

  Tasks created by :func:`spawn` are represented as a :class:`Task` instance.
  It is illegal to create a :class:`Task` instance directly by calling the class.
  The following methods are available on tasks:

.. asyncmethod:: Task.join()

   Wait for the task to terminate.  Returns the value returned by the task or
   raises a :exc:`TaskError` exception if the task failed with an exception.
   This is a chained exception.  The `__cause__` attribute of this
   exception contains the actual exception raised by the task when it crashed.
   If called on a task that has been cancelled, the `__cause__`
   attribute is set to :exc:`CancelledError`.

.. asyncmethod:: Task.cancel(*, exc=CancelledError)

   Cancels the task.  This raises a :exc:`CancelledError` exception in the
   task which may choose to handle it.  Does not return until the
   task is actually cancelled. If you want to change the exception raised,
   supply a different exception as the *exc* argument.  If the task
   has already run to completion, this method does nothing and returns
   immediately.  Returns True if the task is actually cancelled. False
   is returned if the task was already finished prior to cancellation.

The following public attributes are available of :class:`Task` instances:

.. attribute:: Task.id

   The task's integer id.

.. attribute:: Task.coro

   The coroutine associated with the task.

.. attribute:: Task.state

   The name of the task's current state.  Printing it can be potentially useful
   for debugging.

.. attribute:: Task.exc_info

   A tuple of exception information obtained from :py:func:`sys.exc_info` if the
   task crashes for some reason.  Potentially useful for debugging.

If you need to make a task sleep for awhile, use the following function:

.. asyncfunction:: sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, the
   kernel merely switches to the next task (if any).

If a coroutine needs to obtain a reference to the currently running task, use
the following:

.. asyncfunction:: current_task()

   Returns a reference to the :class:`Task` instance corresponding to the
   currently running task.

Performing External Work
------------------------

Sometimes you need to perform work outside the kernel.  This includes CPU-intensive
calculations and blocking operations.  Use the following functions to do that:

.. asyncfunction:: run_in_process(callable, *args, **kwargs)

   Run ``callable(*args, **kwargs)`` in a separate process and returns the result.

.. asyncfunction:: run_in_thread(callable, *args, **kwargs)

   Run ``callable(*args, **kwargs)`` in a separate thread and return the result.

.. asyncfunction:: run_in_executor(exc, callable, *args, **kwargs)

   Run ``callable(*args, **kwargs)`` callable in a user-supplied executor and returns the
   result. *exc* is an executor from the :py:mod:`concurrent.futures` module
   in the standard library.

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
   is set in non-blocking mode when wrapped.

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

   Send all of the data in *data*.

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

   Close the connection.

.. asyncmethod:: do_handshake()

   Perform an SSL client handshake. The underlying socket must have already
   be wrapped by SSL using the :mod:`curio.ssl` module.

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
   where ``reader`` and ``writer`` are streams created by the :meth:`makefile` method.

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
(e.g., the :meth:`Socket.makefile` method).


.. class:: Stream(fileobj)

   Create a file-like wrapper around an existing file.  *fileobj* must be in
   in binary mode.  The file is placed into non-blocking mode
   using :mod:`os.set_blocking(fileobj.fileno())`.

The following methods are available on instances of :class:`Stream`:

.. asyncmethod:: Stream.read(maxbytes=-1)

   Read up to *maxbytes* of data on the file. If omitted, reads as
   much data as is currently available and returns it.

.. asyncmethod:: Stream.readall()

   Return all of the data that's available on a file up until an EOF is read.

.. asyncmethod:: Stream.readline():

   Read a single line of data from a file.

.. asyncmethod:: Stream.write(bytes)

   Write all of the data in *bytes* to the file.

.. asyncmethod:: Stream.writelines(lines)

   Writes all of the lines in *lines* to the file.

.. asyncmethod:: Stream.flush()

   Flush any unwritten data from buffers to the file.

.. asyncmethod:: Stream.close()

   Flush any unwritten data and close the file.

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

subprocess wrapper module
-------------------------
.. module:: curio.subprocess

The :mod:`curio.subprocess` module provides a wrapper around the built-in :mod:`subprocess` module.

.. class:: Popen(*args, **kwargs)

   A wrapper around the :class:`subprocess.Popen` class.  The same arguments are accepted.
   On the resulting ``Popen`` instance, the :attr:`stdin`, :attr:`stdout`, and
   :attr:`stderr` file attributes have been wrapped by the
   :class:`curio.io.Stream` class. You can use these in an asynchronous context.

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


.. asyncmethod:: Popen.wait(timeout=None)

   Wait for a subprocess to exit.

.. asyncmethod:: Popen.communicate(input=b'', timeout=None)

   Communicate with the subprocess, sending the specified input on standard input.
   Returns a tuple ``(stdout, stderr)`` with the resulting output of standard output
   and standard error.

The following functions are also available.  They accept the same arguments as their
equivalents in the :mod:`subprocess` module:

.. asyncfunction:: run(args, stdin=None, input=None, stdout=None, stderr=None, shell=False, timeout=None, check=False)

   Run a command in a subprocess.  Returns a :class:`subprocess.CompletedProcess` instance.

.. asyncfunction:: check_output(args, stdout=None, stderr=None, shell=False, timeout=None)

   Run a command in a subprocess and return the resulting output. Raises a
   :py:exc:`subprocess.CalledProcessError` exception if an error occurred.

ssl wrapper module
------------------

.. module:: curio.ssl

The :mod:`curio.ssl` module provides curio-compatible functions for creating an SSL
layer around curio sockets.  The following functions are redefined (and have the same
calling signature as their counterparts in the standard :mod:`ssl` module:

.. function:: wrap_socket(*args, **kwargs)

.. asyncfunction:: get_server_certificate(*args, **kwargs)

.. function:: create_default_context(*args, **kwargs)

The :class:`SSLContext` class is also redefined and modified so that the :meth:`wrap_socket` method
returns a socket compatible with curio.

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
        kernel.run(curio.run_server('', 10000, handler, ssl=ssl_context))

High Level Networking
---------------------

.. currentmodule:: curio

The following functions are provided to simplify common tasks related to
making network connections and writing servers.

.. asyncfunction:: open_connection(host, port, *, ssl=None, source_addr=None, server_hostname=None)

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
   attacks.

.. asyncfunction:: open_unix_connection(path, *, ssl=None, server_hostname=None):

   Creates a connection to a Unix domain socket with optional SSL applied.

.. function:: create_server(host, port, client_connected_task, *, family=AF_INET, backlog=100, ssl=None, reuse_address=True)

   Creates a :class:`Server` instance for receiving TCP connections on
   a given host and port.  *client_connected_task* is a coroutine that
   is to be called to handle each connection.  Family specifies the
   address family and is either :py:const:`socket.AF_INET` or
   :py:const:`socket.AF_INET6`.  *backlog* is the argument to the
   :py:meth:`socket.socket.listen` method.  *ssl* specifies an
   :class:`curio.ssl.SSLContext` instance to use. *reuse_address*
   specifies whether to reuse a previously used port.  This method
   does not actually start running the created server.  To do that,
   you need to use :meth:`Server.serve_forever` method on the returned
   :class:`Server` instance.  Normally, it's easier to use
   :func:`run_server` instead. Only use :func:`create_server` if you
   need to do something else with the :class:`Server` instance for
   some reason.

.. asyncfunction:: run_server(host, port, client_connected_task, *, family=AF_INET, backlog=100, ssl=None, reuse_address=True)

   Creates a server using :func:`create_server` and immediately starts running it.

.. function:: create_unix_server(path, client_connected_task, *, backlog=100, ssl=None)

   Creates a Unix domain server on a given
   path. *client_connected_task* is a coroutine to execute on each
   connection. *backlog* is the argument given to the
   :py:meth:`socket.socket.listen` method.  *ssl* is an optional
   :class:`curio.ssl.SSLContext` to use if setting up an SSL
   connection.  Returns a :class:`Server` instance.  To start running
   the server use :meth:`Server.serve_forever`.

.. asyncfunction:: run_unix_server(path, client_connected_task, *, backlog=100, ssl=None)

   Creates a Unix domain server using :func:`create_unix_server` and
   immediately starts running it.

Synchronization Primitives
--------------------------

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

.. asyncmethod:: SignalSet.wait()

   Wait for one of the signals in the signal set to arrive. Returns
   the signal number of the signal received.  Normally this method is
   used inside an ``async with`` statement because this allows
   received signals to be properly queued.  It can be used in
   isolation, but be aware that this will only catch a single signal
   right at that line of code.  It's possible that you might lose
   signals if you use this method outside of a context manager.

.. method:: SignalSet.ignore()

   Returns a context manager wherein signals from the signal set are
   temporarily disabled.  Note: This is a normal context manager--
   use a normal ``with``-statement.

Exceptions
----------

.. exception:: CancelledError

   Exception raised in a coroutine if it has been cancelled.  If ignored, the
   coroutine is silently terminated.  If caught, a coroutine can continue to
   run, but should work to terminate execution.  Ignoring a cancellation
   request and continuing to execute will likely cause some other task to hang.

.. exception:: TaskError

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

.. asyncfunction:: _read_wait(fileobj)

   Sleep until data is available for reading on *fileobj*.  *fileobj* is
   any file-like object with a `fileno()` method. 

.. asyncfunction:: _write_wait(fileobj)

   Sleep until data can be written on *fileobj*.  *fileobj* is
   any file-like object with a `fileno()` method. 

.. asyncfunction:: _future_wait(future)

   Sleep until a result is set on *future*.  *future* is an instance of
   :py:class:`concurrent.futures.Future`.

.. asyncfunction:: _join_task(task)

   Sleep until the indicated *task* completes.  The final return value
   of the task is returned if it completed successfully. If the task
   failed with an exception, a :exc:`TaskError` exception is
   raised.  This is a chained exception.  The :attr:`TaskError.__cause__` attribute of this
   exception contains the actual exception raised in the task.

.. asyncfunction:: _cancel_task(task, exc=CancelledError)

   Cancel the indicated *task*.  Does not return until the task actually
   completes the cancellation.  Note: It is usually better to use
   :meth:`Task.cancel` instead of this function.

.. asyncfunction:: _wait_on_queue(kqueue, state_name)

   Go to sleep on a queue. *kqueue* is an instance of a kernel queue
   which is typically a :py:class:`collections.deque` instance. *state_name*
   is the name of the wait state (used in debugging).

.. asyncfunction:: _reschedule_tasks(kqueue, n=1, value=None, exc=None)

   Reschedule one or more tasks from a queue. *kqueue* is an instance of a
   kernel queue.  *n* is the number of tasks to release. *value* and *exc*
   specify the return value or exception to raise in the task when it
   resumes execution.

.. asyncfunction:: _sigwatch(sigset)

   Tell the kernel to start queuing signals in the given signal set *sigset*.

.. asyncfunction:: _sigunwatch(sigset)

   Tell the kernel to stop queuing signals in the given signal set.

.. asyncfunction:: _sigwait(sigset)

   Wait for the arrival of a signal in a given signal set. Returns the signal
   number of the received signal.

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

In this code you can see the low-level calls related to managing a
wait queue. This code is not significantly different than the actual
implementation of a lock in curio.  If you wanted to make your own
task synchronization objects, the code would look similar.
