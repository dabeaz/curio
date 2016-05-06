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

Can a timeout be applied to a sequence of statements?
-----------------------------------------------------

Yes, use the ``timeout_after()`` or ``ignore_after()`` functions as a context
manager.  For example::

    async with timeout_after(5):
         statement1
         statement2
         ...

This is a cumulative timeout applied to the entire block.   After the 
specified number of seconds has elapsed, a ``TaskTimeout`` exception
will be raised in the current operation blocking in curio.

How do you run external commands in a subprocess?
-------------------------------------------------

How do you communicate between threads and coroutines?
------------------------------------------------------

Can coroutines and threads share a common lock?
-----------------------------------------------


    

