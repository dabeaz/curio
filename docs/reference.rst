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

    async def main():
          s = await hello('Guido')
          print(s)

Unlike a normal function, a coroutine can never run all on its own.
It always has to execute under the supervision of a manager (e.g., an
event-loop, a kernel, etc.).  In curio, an initial coroutine is
executed by a low-level kernel using the ``run()`` function. For
example::

    import curio
    curio.run(main())

When executed by curio, a coroutine is considered to be a "Task."  Whenever
the word "task" is used, it refers to the execution of a coroutine.

The Kernel
----------

All coroutines in curio are executed by an underlying kernel.  Normally, you would
run a top-level coroutine using the following function:

.. function:: run(coro, *, pdb=False, log_errors=True, selector=None, with_monitor=False)

   Run the coroutine *coro* to completion and return its final return
   value.  If *pdb* is ``True``, pdb is launched if any task crashes.
   If *log_errors* is ``True``, a traceback is written to the log on
   crash.  If *with_monitor* is ``True``, then the monitor debugging
   task executes in the background.  If *selector* is given, it should
   be an instance of a selector from the :mod:`selectors
   <python:selectors>` module.

If you are going to repeatedly run coroutines one after the other, it
will be more efficient to create a ``Kernel`` instance and submit
them using its ``run()`` method as described below:

.. class:: Kernel(pdb=False, log_errors=True, selector=None, with_monitor=False)

   Create an instance of a curio kernel.  The arguments are the same
   as described above for the :func:`run()` function.

There is only one method that may be used on a :class:`Kernel` outside of coroutines.

.. method:: Kernel.run(coro=None, shutdown=False)

   Runs the kernel until all non-daemonic tasks have finished
   execution.  *coro* is a coroutine to run as a task.  If *shutdown*
   is ``True``, the kernel will cancel all daemonic tasks and perform
   a clean shutdown once all regular tasks have completed.  Calling
   this method with no coroutine and *shutdown* set to ``True``
   will make the kernel cancel all remaining tasks and perform a
   clean shut down.

Tasks
-----

The following functions are defined to help manage the execution of tasks.

.. asyncfunction:: spawn(coro, daemon=False)

   Create a new task that runs the coroutine *coro*.  Does not
   return to the caller until the new task has been scheduled and
   executed for at least one cycle.  Returns a :class:`Task`
   instance as a result.  The *daemon* option, if supplied, specifies that the
   new task will run indefinitely in the background.  Curio only runs
   as long as there are non-daemonic tasks to execute.  Note: a
   daemonic task will still be cancelled if the underlying kernel is
   shut down.

.. asyncfunction:: sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, the
   kernel merely switches to the next task (if any).

.. asyncfunction:: wake_at(clock)

   Sleep until the monotonic clock reaches the given clock value.  Returns the
   value of the monotonic clock at the time the task awakes.  Use this function
   if you need to have more precise interval timing.

.. asyncfunction:: switch(clock)

   Voluntarily switch to the next task. This is a convenience utility so users
   do not need to use :func:`sleep` with a 0 time offset. It also faster than
   sleeping for 0 seconds due to the curio's internals.

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
   exception. This is a chained exception.  The `__cause__` attribute of this
   exception contains the actual exception raised by the task when it crashed.
   If called on a task that has been cancelled, the `__cause__`
   attribute is set to :exc:`curio.CancelledError`.

.. asyncmethod:: Task.cancel()

   Cancels the task.  This raises a :exc:`curio.CancelledError` exception in
   the task which may choose to handle it in order to perform cleanup
   actions.  Does not return until the task actually terminates.
   Curio only allows a task to be cancelled once.  If this method is
   somehow invoked more than once on a still running task, the second
   request will merely wait until the task is cancelled from the first
   request.  If the task has already run to completion, this method
   does nothing and returns immediately.  Returns ``True`` if the task
   was actually cancelled. ``False`` is returned if the task was
   already finished prior to the cancellation request.

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

.. attribute:: Task.exc_info

   A tuple of exception information obtained from :py:func:`sys.exc_info` if the
   task crashes for some reason.  Potentially useful for debugging.

.. attribute:: Task.cancelled

   A boolean flag that indicates whether or not the task was cancelled.

.. attribute:: Task.terminated

   A boolean flag that indicates whether or not the task has run to completion.

Task local storage
------------------

Curio supports "task local storage". The API is modeled after the
"thread local storage" provided by :py:class:`threading.local`.

.. class:: Local

   A class representing a bundle of task-local values. Objects of this
   class have no particular attributes or methods. Instead, they serve
   as a blank slate to which you can add whatever attributes you
   like. Modifications made from within one task will only be visible
   to that task -- with one exception: when you create a new task
   using ``curio.spawn``, then any values assigned to
   :py:class:`Local` objects in the parent task will be inherited by
   the child. This inheritance takes the form of a shallow copy --
   further changes in the parent won't affect the child, and further
   changes in the child won't affect the parent.

Timeouts
--------
Any blocking operation in curio can be cancelled after a timeout.  The following
functions can be used for this purpose:

.. asyncfunction:: timeout_after(seconds, coro=None)

   Execute the specified coroutine and return its result. However,
   issue a cancellation request to the calling task after *seconds*
   have elapsed.  When this happens, a :py:exc:`curio.TaskTimeout`
   exception is raised.  If *coro* is ``None``, the result of this
   function serves as an asynchronous context manager that applies a
   timeout to a block of statements.

   :func:`timeout_after` may be composed with other :func:`timeout_after` 
   operations (i.e., nested timeouts).   If an outer timeout expires
   first, then ``curio.TimeoutCancellationError`` is raised
   instead of :py:exc:`curio.TaskTimeout`.  If an inner timeout
   expires and fails to properly catch :py:exc:`curio.TaskTimeout`,
   a ``curio.UncaughtTimeoutError`` is raised in the outer
   timeout.  

.. asyncfunction:: ignore_after(seconds, coro=None, *, timeout_result=None)

   Execute the specified coroutine and return its result. Issue a
   cancellation request after *seconds* have elapsed.  When a timeout
   occurs, no exception is raised.  Instead, ``None`` or the value of
   *timeout_result* is returned.  If *coro* is ``None``, the result is
   an asynchronous context manager that applies a timeout to a block
   of statements.  For the context manager case, ``result`` attribute
   of the manager is set to ``None`` or the value of *timeout_result*
   if the block was cancelled.

   Note: :func:`ignore_after` may also be composed with other timeout
   operations.  ``curio.TimeoutCancellationError`` and
   ``curio.UncaughtTimeoutError`` exceptions might be raised
   according to the same rules as for :func:`timeout_after`.

Here is an example that shows how these functions can be used::

    # Execute coro(args) with a 5 second timeout
    try:
        result = await timeout_after(5, coro(args))
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

    result = await ignore_after(5, coro(args))
    if result is None:
        # Timeout occurred (if you care)
        ...

    # Execute multiple statements with a 5 second timeout
    async with ignore_after(5) as s:
        await coro1(args)
        await coro2(args)
        ...
        s.result = successful_result

    if s.result is None:
        # Timeout occurred

It's important to note that every curio operation can be cancelled by timeout.
Rather than having every possible call take an explicit *timeout* argument,
you should wrap the call using :func:`timeout_after` or :func:`ignore_after` as
appropriate.

Performing External Work
------------------------
.. module:: curio.workers

Sometimes you need to perform work outside the kernel.  This includes CPU-intensive
calculations and blocking operations.  Use the following functions to do that:

.. asyncfunction:: run_in_process(callable, *args, **kwargs)

   Run ``callable(*args, **kwargs)`` in a separate process and returns
   the result.  If the calling task is cancelled, the underlying
   worker process (if started) is immediately cancelled by a ``SIGTERM``
   signal.

.. asyncfunction:: run_in_thread(callable, *args, **kwargs)

   Run ``callable(*args, **kwargs)`` in a separate thread and return
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

.. asyncfunction:: run_in_executor(exc, callable, *args, **kwargs)

   Run ``callable(*args, **kwargs)`` callable in a user-supplied
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

.. asyncmethod:: FileStream.write(bytes)

   Write all of the data in *bytes* to the file.

.. asyncmethod:: FileStream.writelines(lines)

   Writes all of the lines in *lines* to the file.

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

.. function:: wrap_socket(*args, **kwargs)

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

.. asyncfunction:: tcp_server(host, port, client_connected_task, *, family=AF_INET, backlog=100, ssl=None, reuse_address=True)

   Creates a server for receiving TCP connections on
   a given host and port.  *client_connected_task* is a coroutine that
   is to be called to handle each connection.  Family specifies the
   address family and is either :data:`socket.AF_INET` or
   :data:`socket.AF_INET6`.  *backlog* is the argument to the
   :py:meth:`socket.socket.listen` method.  *ssl* specifies an
   :class:`curio.ssl.SSLContext` instance to use. *reuse_address*
   specifies whether to reuse a previously used port.

.. asyncfunction:: unix_server(path, client_connected_task, *, backlog=100, ssl=None)

   Creates a Unix domain server on a given
   path. *client_connected_task* is a coroutine to execute on each
   connection. *backlog* is the argument given to the
   :py:meth:`socket.socket.listen` method.  *ssl* is an optional
   :class:`curio.ssl.SSLContext` to use if setting up an SSL
   connection.

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


file wrapper module
---------------------

.. module:: curio.file

One problem concerning coroutines and async concerns access to files on the
normal file system.  Yes, you can use the built-in ``open()`` function, but 
what happens afterwards is hard to predict.  Under the covers, the operating
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
avoid unintentional errors in your program where you blocking might
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

.. class:: RLock()

   This class provides a recursive lock funtionality, that could be acquired multiple times
   within the same task. The behavior of this lock is identical to the ``threading.RLock``,
   except that the owner of the lock will be a task, wich acquired it, instead of a thread.


:class:`RLock` instances support the following methods:

.. asyncmethod:: Lock.acquire()

   Acquire the lock, incrementing the recursion by 1. Can be used multiple times withing 
   the same task, that owns this lock.

.. asyncmethod:: Lock.release()

   Release the lock, decrementing the rerecurtion level by 1. If recursion level reaches 0,
   the lock is unlocked. Raises ``RuntimeError`` if called not by the owner or if lock
   is not locked.

.. method:: Lock.locked()

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

  Creates a **priority** queue with a maximum number of elements in *maxsize*.

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

    A queue with **"Last In First Out"** retrieving policy

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


Synchronizing with Threads and Processes
----------------------------------------
Curio's synchronization primitives aren't safe to use with externel threads or
processes.   However, Curio can work with existing thread or process-level
synchronization primitives if you use the :func:`abide` function.

.. asyncfunction:: abide(op, *args, **kwargs)

   Makes curio abide by the execution requirements of a given
   function, coroutine, or context manager.  If *op* is coroutine
   function, it is called with the given arguments and returned.  If *op* is an
   asynchronous context manager, it is returned unmodified.  If *op* is
   a synchronous function, ``run_in_thread(op, *args, **kwargs)`` is
   returned.  If *op* is a synchronous context manager, it is wrapped by
   an asynchronous context manager that executes the ``__enter__()`` and
   ``__exit__()`` methods in a backing thread.

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

Here is how you would implement a producer/consumer problem between
threads and curio using a standard thread queue::

    import curio
    import threading
    import queue

    # A thread
    def producer(queue):
        for n in range(10):
            queue.put(n)
        queue.join()
        print('Producer done')
	queue.put(None)

    # A curio task
    async def consumer(queue):
        while True:
            item = await curio.abide(queue.get)
	    if item is None:
	        break
            print('Consumer got', item)
            await curio.abide(queue.task_done)
        print('Consumer done')

    q = queue.Queue()
    threading.Thread(target=producer, args=(q,)).start()
    curio.run(consumer(q))

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

A special circle of hell is reserved for code that combines the use of
the ``abide()`` function with task cancellation.  Although
cancellation is supported, there are a few things to keep in mind
about it.  First, if you are using ``abide(func, arg1, arg2, ...)`` to
run a synchronous function, that function will fully run to completion
in a separate thread regardless of the cancellation.  So, if there are
any side-effects associated with that code executing, you'll need to
take them into account.  Second, if you are using ``async with
abide(lock)`` with a thread-lock and a cancellation request is
received while waiting for the ``lock.__enter__()`` method to execute,
a background thread continues to run waiting for the eventual lock
acquisition.  Once acquired, it will be immediately released again.
Without this, task cancellation would surely cause a deadlock of
threads waiting to use the same lock.

The ``abide()`` function can be used to synchronize with a thread
reentrant lock (e.g., ``threading.RLock``).  However, reentrancy is
not supported.  Each lock acquisition using ``abide()`` involves a
backing thread.  Repeated acquisitions would violate the constraint
that reentrant locks have on only acquired by a single thread.

All things considered, it's probably best to try and avoid code that
synchronizes Curio tasks with threads.  However, if you must, Curio abides.

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

   Exception raised in a coroutine if it has been cancelled.  If ignored, the
   coroutine is silently terminated.  If caught, a coroutine can continue to
   run, but should work to terminate execution.  Ignoring a cancellation
   request and continuing to execute will likely cause some other task to hang.

.. exception:: TaskTimeout

   Exception raised in a coroutine if it has been cancelled by timeout.

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

Traps come in two flavors: *regular* and *synchronous*. A synchronous
trap is implemented by trapping into the kernel, but semantically it
acts like a regular synchronous function call. Specifically, this
means that it always returns immediately without running any other
task, and that it does not act as a cancellation point. Regular traps
might or might not block or yield execution, and can be cancelled or
timed-out.

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
   failed with an exception, a :exc:`curio.TaskError` exception is
   raised.  This is a chained exception.  ``TaskError.__cause__``
   attribute of this exception contains the actual exception raised in
   the task.

.. asyncfunction:: _cancel_task(task)

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

   Synchronous trap. Tell the kernel to start queuing signals in the
   given signal set *sigset*.

.. asyncfunction:: _sigunwatch(sigset)

   Synchronous trap. Tell the kernel to stop queuing signals in the
   given signal set.

.. asyncfunction:: _sigwait(sigset)

   Wait for the arrival of a signal in a given signal set. Returns the signal
   number of the received signal.

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

.. asyncfunction:: _adjust_cancel_defer_depth(n)

   Synchronous trap. For each task, we keep track of how deeply nested
   we are inside ``curio.defer_cancellation`` blocks. This trap is
   used to increment/decrement this count when we enter/exit these
   blocks. If the count reaches zero and a cancellation is pending,
   then raises ``CancelledError``.

.. asyncfunction:: _queue_reschedule_function(queue)

   Synchronous trap. Return a function that allows tasks to be
   rescheduled from a queue without the use of await.  Can be used in
   synchronous code as long as it runs in the same thread as the Curio
   kernel.

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
