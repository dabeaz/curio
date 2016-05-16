Curio How-To
============

This document provides some recipes for using Curio to perform common tasks.

How do you write a simple TCP server?
-------------------------------------

Here is an example of a simple TCP echo server::

    from curio import run, spawn, tcp_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(100000)
            if not data:
                break
            await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server('', 25000, echo_client))

This server uses sockets directly.  If you want to a use a file-like streams
interface, use the ``as_stream()`` method like this::

    from curio import run, spawn, tcp_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        s = client.as_stream()
        while True:
            data = await s.read(100000)
            if not data:
                break
            await s.write(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server('', 25000, echo_client))

How do you write a UDP Server?
-----------------------------

Here is an example of a simple UDP echo server using sockets::

    import curio
    from curio import socket

    async def udp_echo(addr):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(addr)
        while True:
            data, addr = await sock.recvfrom(10000)
            print('Received from', addr, data)
            await sock.sendto(data, addr)

    if __name__ == '__main__':
        curio.run(main(('', 26000)))

At this time, there are no high-level function (i.e., similar to
``tcp_server()``) to run a UDP server. 

How do you perform a blocking operation?
----------------------------------------

If you need to perform a blocking operation that runs outside of curio,
use ``run_in_thread()``.  For example::

    import time
    import curio

    result = await curio.run_in_thread(time.sleep, 100)

How do you perform a CPU intensive operation?
---------------------------------------------

If you need to run a CPU-intensive operation, you can either run it
in a thread (see above) or have it run in a separate process. For example::

    import curio

    def fib(n):
        if n <= 2:
           return 1
        else:
           return fib(n-1) + fib(n-2)

    ...
    result = await curio.run_in_process(fib, 40)

How do you apply a timeout?
---------------------------

You can make any curio operation timeout using ``timeout_after(seconds, coro)``. For
example::

    from curio import timeout_after, TaskTimeout
    try:
         result = await timeout_after(5, coro(args))
    except TaskTimeout:
         print('Timed out')

Since wrapping a timeout in an exception is common, you can also use ``ignore_after()``
which returns ``None`` instead.  For example::

    from curio import ignore_after

    result = await ignore_after(5, coro(args))
    if result is None:
        print('Timeout out')

How can a timeout be applied to a block of statements?
------------------------------------------------------

Use the ``timeout_after()`` or ``ignore_after()`` functions as a context
manager.  For example::

    async with timeout_after(5):
         statement1
         statement2
         ...

This is a cumulative timeout applied to the entire block.   After the 
specified number of seconds has elapsed, a ``TaskTimeout`` exception
will be raised in the current operation blocking in curio.

How do you shield a coroutine from cancellation?
------------------------------------------------

The easiest way to shield a coroutine from cancellation is to spawn
it as a separate task.  For example::

     async def func():
         ...
         child = await spawn(coro(args))
         result = await child.join()
         ...

Cancellation only applies to the immediate task on which it is
performed.  So, if the outer coroutine ``func()`` is cancelled, the
inner task created by ``spawn()`` will continue to run to completion.

How do you make cancellation apply to child tasks?
--------------------------------------------------

If you want to make a parent coroutine cancel all of its children
when it's cancelled, it needs to keep track of the children and
cancel them explicitly. For example::

     async def func():
         ...
         child = await spawn(coro(args))
         try:
              ...
              ...
              await child.join()
         except CancelledError:
              await child.cancel()

How does a coroutine get its enclosing Task instance?
-----------------------------------------------------

Use the ``current_task()`` function like this::

     from curio import current_task
     ...
     async def func():
         ...
         myself = await current_task()
         ...

Once you have a reference to the ``Task``, it can be passed
around and use in other operations.  For example, a different
task could use it to cancel.

How can tasks communicate?
--------------------------

Similar to threads, one of the easiest ways to communicate between
tasks is to use a queue.  For example::

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

    if __name__ == '__main__':
        curio.run(main())

How can a task and a thread communicate?
----------------------------------------

The most straightforward way to communicate between curio tasks and
threads is to use a thread-safe queue from the built-in ``queue``
module in combination with the curio ``abide()`` function::

    import curio
    import queue
    import threading

    # A thread - standard python
    def producer(queue):
        for n in range(10):
            queue.put(n)
        queue.join()
        print('Producer done')

    # A task - Curio
    async def consumer(queue):
        while True:
            item = await curio.abide(queue.get)
            print('Consumer got', item)
            await curio.abide(queue.task_done)

    async def main():
        q = queue.Queue()     # Thread-safe queue
        prod_task = threading.Thread(target=producer, args=(q,)).start()
        cons_task = await curio.spawn(consumer(q))
        prod_task.join()
        await cons_task.cancel()

    if __name__ == '__main__':
        curio.run(main())

``abide()`` is a special function that allows curio to adapt to
foreign functions and synchronization primitives typically associated
with threads and processes.  In this example, the ``queue.get()`` and
``queue.task_done()`` functions will be executed in a separate thread
to avoid blocking other running tasks.  It is important to note that
``curio.abide(queue.get)`` is not a typo.  ``abide()`` will call the
supplied function on your behalf.  If you try to use
``curio.abide(queue.get())``, you'll not only block the whole kernel
loop, you'll also get an error when it finally wakes up.

There's one other interesting feature of ``abide()``. If you use it on
a coroutine that's native to curio, it will still work. Thus, the
``consumer()`` function above would actually work if the supplied queue
is either a ``Queue`` from the built-in ``queue`` module or an async
compatible ``Queue`` provided by curio.  It's magic.

How can coroutines and threads share a common lock?
---------------------------------------------------

A lock can be shared as the lock in question is one from the
``threading`` module and you use the curio ``abide()`` function.  For
example::

    import threading
    import curio

    lock = threading.Lock()      # Must be a thread-lock

    # Function running in a thread
    def func():
        ...
        with lock:
             critical_section
             ...

    # Coroutine running curio
    async def coro():
        ...
        async with curio.abide(lock):
             critical_section
             ...

``curio.abide()`` adapts the given lock to work safely inside
curio.  If given a thread-lock, the various locking operations
are executed in threads to avoid blocking other curio tasks. 

How do you run external commands in a subprocess?
-------------------------------------------------

Curio provides it's own version of the subprocess module.  Use
the ``check_output()`` function as you would in normal Python code.
For example::

    from curio import subprocess

    async def func():
        ...
        out = await subprocess.check_output(['cmd','arg1','arg2','arg3'])
        ...

The ``check_output()`` function takes the same arguments and raises the
same exceptions as its standard library counterpart.  The underlying 
implementation is built entirely using the async I/O primitives of curio.
It's fast and no backing threads are used. 

How can you communicate with a subprocess over a pipe?
------------------------------------------------------
Use the ``curio.subprocess`` module just like you would use the
normal ``subprocess`` module. For example::

    from curio import subprocess

    async def func():
         ...
         p = subprocess.Popen(['cmd', 'arg1', 'arg2', ...],
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE)
         await p.stdin.write(b'Some data')
         ...
         resp = await p.stdout.read(maxsize)

In this example, the ``p.stdin`` and ``p.stdout`` streams are
replaced by curio-compatible file streams.  You use the same
I/O operations as before, but make sure you preface them
with ``await``. 
