Reference Manual
================

This manual lists the basic functionality provided by curio.

The Kernel
----------

The kernel is responsible for running all of the tasks.  It should normally be created
in the main execution thread.

.. class:: class Kernel([selector=None [, with_monitor=False]])

   Create an instance of a curio kernel.  If *selector* is given, it should be
   an instance of a selector from the :mod:`selectors` module.  If not given,
   then ``selectors.DefaultSelector`` is used to poll for I/O. 
   If *with_monitor* is ``True``, the monitor task executes in the background.
   The monitor responds to the keyboard-interrupt and allows you to inspect
   the state of the running kernel.

There are only a few methods that may be used on a ``Kernel`` outside of coroutines.

.. method:: Kernel.add_task(coro [, daemon=False])

   Adds a new task to the kernel.  *coro* is a newly instantiated coroutine. 
   If *daemon* is ``True``, the task is created without a parent and runs in
   the background.   Returns a :class:`Task` instance.  This method may not
   be used to add a task to a running kernel and may not be used inside a
   coroutine.

.. method:: Kernel.run([pdb=False [, log_errors=True]])
  
   Runs the kernel until all non-daemonic tasks have finished execution.
   If *pdb* is ``True``, then the kernel enters the Python debugger if any
   task crashes with an uncaught exception.  If *log_errors* is ``True``, then
   uncaught exceptions in tasks are logged.

.. method:: Kernel.shutdown()

   Performs a clean shutdown of the kernel by issuing a cancellation request to
   all remaining tasks (including daemonic tasks).  This function will not return
   until all tasks have terminated.  This method may only be invoked on a kernel
   that is not actively running.  It may not be used inside coroutines or from
   separate threads.  Normally, it is not necessary to call this method since
   the kernel runs until all tasks have terminated anyways.

.. method:: Kernel.stop()

   Force the kernel to stop execution.  Since the kernel normally runs in the main
   thread, this operation would normally have to be performed in a separate thread
   or possibly inside a coroutine.  This method merely sets a flag in the kernel
   and returns immediately.  The kernel will stop only after the currently running 
   task yields.

Basic System Calls
------------------

Tasks interact with the kernel by making system calls.  These
functions may only be used inside coroutines.

.. function:: await new_task(coro [, daemon=False])

   Create a new task.  *coro* is a newly called coroutine.  Does not
   return to the caller until the new task has been scheduled and executed for at least
   one cycle.  Returns a :class:`Task` instance as a result.  The *daemon* option,
   if supplied, creates the new task without a parent.  The task will run indefinitely
   in the background.  Note: The kernel only runs as long as there are non-daemonic
   tasks to execute.

.. function:: await sleep(seconds)

   Sleep for a specified number of seconds.  If the number of seconds is 0, the
   kernel merely switches to the next task (if any).

Tasks
-----

Tasks created by :func:`new_task()` are represented as a :class:`Task` instance.
There is no public interface for creating a task instance.   The following methods
are available on tasks:

.. method:: await Task.join([timeout=None])

   Wait for the task to terminate.  Returns the value returned by the task or
   raises a :exc:`curio.TaskError` exception if the task failed with an exception.
   This is a chained exception.  The `__cause__` attribute of this 
   exception contains the actual exception raised in the task.

.. method:: await Task.cancel([timeout=None])

   Cancels the task.  This raises a :exc:`curio.TaskCancelled` exception in the
   task which may choose to handle it.  Does not return until the
   task is actually cancelled.

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

Performing External Work
------------------------

Sometimes you need to perform work outside the kernel.  This includes CPU-intensive
calculations and blocking operations.  Use the following functions to do that:

.. function:: await run_cpu_bound(callable, *args [, timeout=None])

   Run a callable in a process pool created by :mod:`concurrent.futures.ProcessPoolExecutor`.
   Returns the result.

.. function:: await run_blocking(callable, *args [, timeout=None])

   Run a callable in a thread pool created by :mod:`concurrent.futures.ThreadPoolExecutor`.
   Returns the result.

.. function:: await run_in_executor(exc, callable, *args [,timeout=None])

   Run a callable in a user-supplied executor and returns the result.

.. function:: set_cpu_executor(exc)

   Set the default executor used for CPU-bound processing.

.. function:: set_blocking_executor(exc)

   Set the default executor used for blocking processing.

Sockets
-------
The :mod:`curio.socket` module provides a wrapper around the built-in :mod:`socket` module.
The module provides exactly the same functionality except that certain operations have
been replaced by coroutine equivalents.  Sockets in curio are fully compatible with 
timeouts and other socket features.

.. class:: class socket(family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None)

   Creates a wrapper the around :class:`socket` objects created in the built-in :mod:`socket`
   module.  The arguments for construction are identical and have the same meaning.
   The resulting :class:`socket` instance is set in non-blocking mode.  

.. method:: socket.from_sock(sock)

   Class method.  Creates a :mod:`curio.socket` wrapper object from an existing socket.   

The following methods are redefined on :class:`socket` objects to be compatible with coroutines.
Please note that all of the other :class:`socket` methods are available as well.  However,
unless specifically listed here, those methods simply delegate to their original implementation.
Be aware that not all methods have been wrapped and that using a method not listed here might
block the kernel.

.. method:: await socket.recv(maxbytes [, flags=0])

   Receive up to *maxbytes* of data.

.. method:: await socket.recv_into(buffer [, nbytes=0 [, flags=0]])

   Receive up to *nbytes* of data into a buffer object.

.. method:: await socket.recvfrom(maxsize [, flags=0])

   Receive up to *maxbytes* of data.  Returns a tuple `(data, client_address)`.

.. method:: await socket.recvfrom_into(buffer [, nbytes=0 [, flags=0]])

   Receive up to *nbytes* of data into a buffer object. 

.. method:: await socket.send(data [, flags=0])

   Send data.  Returns the number of bytes of data actually sent (which may be
   less than provided in *data*).

.. method:: await socket.sendall(data [, flags=0])

   Send all of the data in *data*.

.. method:: await socket.sendto(data, address):

   Send data to the specified address.

.. method:: await socket.accept()

   Wait for a new connection.  Returns a tuple `(sock, address)`.

.. method:: await socket.connect(address)

   Make a connection.

.. method:: socket.makefile(mode [, buffering=0])

   Make a file-like object that wraps the socket.  The resulting file
   object is a :class:`curio.file.File` instance that supports non-blocking
   I/O.   *mode* specifies the file mode which must be one of ``'rb'``, ``'wb'``,
   or ``'rwb'``.  *buffering* is currently ignored and only provided for compatibility
   with the :mod:`socket` module API. It might be supported in a future version.
   Note: It is not possible to create a file with Unicode text encoding/decoding applied 
   to it so those options are not available.

The following module-level functions have been modified so that the returned socket
objects are compatible with curio:

.. function:: socketpair([ family=AF_UNIX [, type=SOCK_STREAM [, proto=0]]])
.. function:: fromfd(fd, family, type [, proto=])
.. function:: create_connection(address [,timeout [, source_address]])

The following module-level functions have been redefined as coroutines so that they
don't block the kernel:

.. function:: await getaddrinfo(host, port, family=0, type=0, proto=0, flags=0)
.. function:: await getfqdn([name])
.. function:: await gethostbyname(hostname)
.. function:: await gethostbyname_ex(hostname)
.. function:: await gethostname()
.. function:: await gethostbyaddr(ip_address)
.. function:: await getnameinfo(sockaddr, flags)

Files
-----

The :mod:`curio.file` module contains a class :class:`File` that puts a non-blocking
wrapper around an existing file object.  Certain other functions in curio use this (e.g.,
the :func:`socket.makefile()` method).   

.. class:: class File(fileobj)

   Create a file-like wrapper around an existing file.  *fileobj* must be in
   in binary mode and unbuffered.  The file is placed into non-blocking mode
   using :mod:`os.set_blocking()`.

The following methods are available on instances of :class:`File`:

.. method:: await File.read([maxbytes=-1])

   Read up to *maxbytes* of data on the file. If omitted, reads as 
   much data as is currently available and returns it.

.. method:: await File.readall()

   Return all of the data that's available on a file up until an EOF is read.

.. method:: await File.readline():
 
   Read a single line of data from a file.

.. method:: await File.write(bytes)

   Write all of the data in *bytes* to the file. 

.. method:: await File.writelines(lines)

   Writes all of the lines in *lines* to the file.

.. method:: settimeout(seconds)

   Sets a timeout on all file I/O operations.  If *seconds* is None, any previously set
   timeout is cleared. 

Other file methods (e.g., ``tell()``, ``seek()``, etc.) are available
if the supplied ``fileobj`` also has them.

Synchronization Primitives
--------------------------

The following synchronization primitives are available. Their behavior is
similar to their equivalents in the :mod:`threading` module.  None of these
primitives are thread-safe.

.. class:: class Event()

   An event object.

:class:`Event` instances support the following methods:

.. method:: Event.is_set()

   Return ``True`` if the event is set.

.. method:: Event.clear()

   Clear the event.

.. method:: await Event.wait([timeout=None])

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

.. class:: class Lock()

   This class provides a mutex lock.  It can only be used in tasks. It is not thread safe.

:class:`Lock` instances support the following methods:

.. method:: await Lock.acquire([timeout=None])

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
        await lck.acquire()
        print('Parent has the lock')
	await curio.new_task(child(lck))
	await curio.sleep(5)
	await lck.release()

.. class:: class Semaphore([value=1])

   Create a semaphore.  Semaphores are based on a counter.  If the count is greater
   than 0, it is decremented and the semaphore is acquired.  Otherwise, the task
   has to wait until the count is incremented by another task.

.. class:: class BoundedSemaphore([value=1])

   This class is the same as :class:`Semaphore` except that the 
   semaphore value is not allowed to exceed the initial value.

Semaphores support the following methods:

.. method:: await Semaphore.acquire([timeout=None])

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

.. class:: class Condition([lock=None])

   Condition variable.  *lock* is the underlying lock to use. If none is provided, then
   a :class:`Lock` object is used.

:class:`Condition` objects support the following methods:

.. method:: Condition.locked()

   Return ``True`` if the condition variable is locked.

.. method:: await Condition.acquire([timeout=None])

   Acquire the condition variable lock.

.. method:: await Condition.release()

   Release the condition variable lock.

.. method:: await Condition.wait([timeout=None])

   Wait on the condition variable with a timeout.  This releases the underlying lock.

.. method:: await Condition.wait_for(predicate [, timeout=None])

   Wait on the condition variable until a supplied predicate function returns ``True``. *predicate* is
   a callable that takes no arguments.  

.. method:: await notify([n=1])

   Notify one or more tasks, causing them to wake from the :meth:`wait` method.

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

.. class:: class Queue([maxsize=0])

   Creates a queue with a maximum number of elements in *maxsize*.  If not
   specified, the queue can hold an unlimited number of items.

A :class:`Queue` instance supports the following methods:

.. method:: Queue.empty()

   Returns ``True`` if the queue is empty.

.. method:: Queue.full()

   Returns ``True`` if the queue is full.

.. method:: Queue.qsize()

   Return the number of items currently in the queue.

.. method:: await Queue.get([timeout=None])

   Returns an item from the queue with an optional timeout.

.. method:: await Queue.put(item [, timeout=None])

   Puts an item on the queue with an optional timeout in the event
   that the queue is full.

.. method:: await Queue.join([timeout=None])

   Wait for all of the elements put onto a queue to be processed. Consumers
   must call :meth:Queue.task_done() to indicate completion.

.. method:: await Queue.task_done()

   Indicate that processing has finished for an item.  If all items have
   been processed and there are tasks waiting on ``Queue.join()`` they
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

.. class:: class SignalSet(*signals)

   Represents a set of one or more Unix signals.  *signals* is a list of
   signals as defined in the built-in :mod:`signal` module.

The following methods are available on a :class:`SignalSet` instance. They
may only be used in coroutines.

.. method:: await SignalSet.wait([timeout=None])

   Wait for one of the signals in the signal set to arrive. Returns the
   signal number of the signal received.  *timeout* gives an optional
   timeout.  Normally this method is used inside an `async with:` statement
   because this allows received signals to be properly queued.  It can be
   used in isolation, but be aware that this will only catch a single
   signal right at that line of code.  It's possible that you might lose
   signals if you use this method outside of a context manager. 

.. method:: SignalSet.ignore()

   Returns a context manager wherein signals from the signal set are
   temporarily disabled. 

Exceptions
----------

.. class:: class TaskCancelled

   Exception raised in a coroutine if it has been cancelled.  If ignored, the
   coroutine is silently terminated.  If caught, a coroutine can continue to
   run, but should work to terminate execution.  Ignoring a cancellation 
   request and continuing to execute will likely cause some other task to hang.

.. class:: class TaskError

   Exception raised by the :meth:`Task.join()` method if an uncaught exception
   occurs in a task.  It is a chained exception. The :attr:`__cause__` attribute contains
   the exception that causes the task to fail.

Low-level Kernel System Calls
-----------------------------

The following system calls are available, but not typically used
directly in user code.  They are used to implement higher level
objects such as locks, socket wrappers, and so forth. If you find
yourself using these, you're probably doing something wrong--or
implementing a new curio primitive.

.. function:: await read_wait(fileobj [, timeout=None])

   Sleep until data is available for reading on *fileobj*.  *fileobj* is
   any file-like object with a `fileno()` method.  *timeout*
   gives an optional timeout in seconds.

.. function:: await write_wait(fileobj [, timeout=None])

   Sleep until data can be written on *fileobj*.  *fileobj* is
   any file-like object with a `fileno()` method. *timeout*
   gives an optional timeout in seconds.

.. function:: await future_wait(future [, timeout=None])

   Sleep until a result is set on *future*.  *future* is an instance of
   :class:`Future` as found in the :mod:concurrent.futures module.

.. function:: await join_task(task [, timeout=None])

   Sleep until the indicated *task* completes.  The final return value
   of the task is returned if it completed successfully. If the task
   failed with an exception, a ``curio.TaskError`` exception is
   raised.  This is a chained exception.  The `__cause__` attribute of this 
   exception contains the actual exception raised in the task.

.. function:: await cancel_task(task [, timeout=None])

   Cancel the indicated *task*.  Does not return until the task actually
   completes the cancellation.

.. function:: await wait_on_queue(kqueue, state_name [, timeout=None])

   Go to sleep on a queue. *kqueue* is an instance of a kernel queue
   which is typically a ``collections.deque`` instance. *state_name* 
   is the name of the wait state (used in debugging).

.. function:: await reschedule_tasks(kqueue, [n=1 [, value=None [, exc=None]]])

   Reschedule one or more tasks from a queue. *kqueue* is an instance of a
   kernel queue.  *n* is the number of tasks to release. *value* and *exc*
   specify the return value or exception to raise in the task when it 
   resumes.    

.. function:: await sigwatch(sigset)

   Tell the kernel to start queuing signals in the given signal set *sigset*.

.. function:: await sigunwatch(sigset)

   Tell the kernel to stop queuing signals in the given signal set.

.. function:: await sigwait(sigset [, timeout=None])

   Wait for the arrival of a signal in a given signal set.

Again, you're unlikely to use any of these functions directly.  However, here's a small taste
of how they're used.  For example, here's the ``recv()`` method of ``socket`` objects::

    class socket(object):
        ...
        def recv(self, maxbytes):
            while True:
                try:
                    return self._socket.recv(maxbytes)
                except BlockingIOError:
                    await read_wait(self._socket)
        ...

This method first tries to receive data.  If none is available, the ``read_wait()`` call is used to 
put the task to sleep until reading can be performed. When it awakes, the receive operation 
is retried.

Here's an example of code that implements a lock::

    from collections import deque

    class Lock(object):
        def __init__(self):
            self._acquired = False
            self._waiting = deque()

        async def acquire(self):
            if self._acquired:
                await wait_on_queue(self._waiting, 'LOCK_ACQUIRE')

        async def release(self):
             if self._waiting:
                 await reschedule_tasks(self._waiting, n=1)
             else:
                 self._acquired = False

In this code you can see the low-level calls related to managing a wait queue. This
code is not significantly different than the actual implementation of a lock
in curio.   If you wanted to make your own task synchronization objects, the 
code would look similar.






