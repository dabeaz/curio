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
        run(tcp_server, '', 25000, echo_client)

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
        run(tcp_server, '', 25000, echo_client)

How do you write a UDP Server?
------------------------------

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
        curio.run(udp_echo, ('', 26000))

At this time, there are no high-level function (i.e., similar to
``tcp_server()``) to run a UDP server. 


How do you make an outgoing connection?
---------------------------------------

Curio provides some high-level functions for making outgoing connections.
For example, here is a task that makes a connection to ``www.python.org``::

    import curio

    async def main():
        sock = await curio.open_connection('www.python.org', 80)
        async with sock:
            await sock.sendall(b'GET / HTTP/1.0\r\nHost: www.python.org\r\n\r\n')
            chunks = []
            while True:
                chunk = await sock.recv(10000)
                if not chunk:
                    break
                chunks.append(chunk)

        response = b''.join(chunks)
        print(response.decode('latin-1'))

    if __name__ == '__main__':
        curio.run(main)

If you run this, you should get some output that looks similar to this::

    HTTP/1.1 301 Moved Permanently
    Server: Varnish
    Retry-After: 0
    Location: https://www.python.org/
    Content-Length: 0
    Accept-Ranges: bytes
    Date: Fri, 30 Oct 2015 17:33:34 GMT
    Via: 1.1 varnish
    Connection: close
    X-Served-By: cache-dfw1826-DFW
    X-Cache: HIT
    X-Cache-Hits: 0
    Strict-Transport-Security: max-age=63072000; includeSubDomains

Ah, a redirect to HTTPS.  Let's make a connection with SSL applied to it::

    import curio

    async def main():
        sock = await curio.open_connection('www.python.org', 443, 
	                                   ssl=True, 
					   server_hostname='www.python.org')
        async with sock:
            await sock.sendall(b'GET / HTTP/1.0\r\nHost: www.python.org\r\n\r\n')
            chunks = []
            while True:
                chunk = await sock.recv(10000)
                if not chunk:
                    break
                chunks.append(chunk)

        response = b''.join(chunks)
        print(response.decode('latin-1'))

    if __name__ == '__main__':
        curio.run(main)

It's worth noting that the primary purpose of curio is
merely concurrency and I/O.  You can create sockets and you can apply
things such as SSL to them. However, curio doesn't implement any
application-level protocols such as HTTP.  Think of curio as a base-layer
for doing that.

How do you write an SSL-enabled server?
---------------------------------------

Here's an example of a server that speaks SSL::

    import curio
    from curio import ssl
    import time

    KEYFILE = 'privkey_rsa'       # Private key
    CERTFILE = 'certificate.crt'  # Server certificate
 
    async def handler(client, addr):
        client_f = client.as_stream()

	# Read the HTTP request
        async for line in client_f:
           line = line.strip()
           if not line:
               break
           print(line)

	# Send a response
        await client_f.write(
    b'''HTTP/1.0 200 OK\r
    Content-type: text/plain\r
    \r
    If you're seeing this, it probably worked. Yay!
    ''')
        await client_f.write(time.asctime().encode('ascii'))
	await client.close()

    if __name__ == '__main__':
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
        curio.run(curio.tcp_server, '', 10000, handler, ssl=ssl_context)

The ``curio.ssl`` submodule is a wrapper around the ``ssl`` module in the standard
library.  It has been modified slightly so that functions responsible for wrapping
sockets return a socket compatible with curio.  Otherwise, you'd use it the same
way as the normal ``ssl`` module.

To test this out, point a browser at ``https://localhost:10000`` and see if you
get a readable response.  The browser might yell at you with some warnings
about the certificate if it's self-signed or misconfigured in some way. However, the
example shows the basic steps involved in using SSL with curio.

How do you perform a blocking operation?
----------------------------------------

If you need to perform a blocking operation that runs outside of curio,
use ``run_in_thread()`` to have it run in a backing thread.  For example::

    import time
    import curio

    result = await curio.run_in_thread(time.sleep, 100)

How do you perform a CPU intensive operation?
---------------------------------------------

If you need to run a CPU-intensive operation, you can either run it in
a thread (see above) or have it run in a separate process. For
example::

    import curio

    def fib(n):
        if n <= 2:
           return 1
        else:
           return fib(n-1) + fib(n-2)

    ...
    result = await curio.run_in_process(fib, 40)

Note: Since the operation in question runs in a separate interpreter,
it should not involve any shared state.  Make sure you pass all
required information in the function's input arguments.

How do you apply a timeout?
---------------------------

You can make any curio operation timeout using ``timeout_after(seconds, coro)``. For
example::

    from curio import timeout_after, TaskTimeout
    try:
         result = await timeout_after(5, coro, args)
    except TaskTimeout:
         print('Timed out')

Since wrapping a timeout in an exception is common, you can also use ``ignore_after()``
which returns ``None`` instead.  For example::

    from curio import ignore_after

    result = await ignore_after(5, coro, args)
    if result is None:
        print('Timed out')

How can a timeout be applied to a block of statements?
------------------------------------------------------

Use the ``timeout_after()`` or ``ignore_after()`` functions as a context
manager.  For example::

    try:
        async with timeout_after(5):
            statement1
            statement2
            ...
    except TaskTimeout:
        print('Timed out')


This is a cumulative timeout applied to the entire block.   After the 
specified number of seconds has elapsed, a ``TaskTimeout`` exception
will be raised in the current operation blocking in curio.

How do you shield operations from timeouts or cancellation?
-----------------------------------------------------------

To protect a block of statements from being aborted due to a timeout
or cancellation, use ``disable_cancellation()`` as a context manager
like this::

     async def func():
         ...
         async with disable_cancellation():
             await coro1()
             await coro2()
             ...

         await blocking_op()      # Cancellation delivered here

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
        prod_task = await curio.spawn(producer, q)
        cons_task = await curio.spawn(consumer, q)
        await prod_task.join()
        await cons_task.cancel()

    if __name__ == '__main__':
        curio.run(main)


How can a task and a thread communicate?
----------------------------------------

The most straightforward way to communicate between curio tasks and
threads is to use curio's ``UniversalQueue`` class::

    import curio
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
            item = await queue.get()
            print('Consumer got', item)
            await queue.task_done()

    async def main():
        q = curio.UniversalQueue()
        prod_task = threading.Thread(target=producer, args=(q,))
        prod_task.start()
        cons_task = await curio.spawn(consumer, q)
        await curio.run_in_thread(prod_task.join)
        await cons_task.cancel()

    if __name__ == '__main__':
        curio.run(main)

A ``UniversalQueue`` can be used by any combination of threads or
curio tasks.  The same API is used in both cases.  However,
when working with coroutines, queue operations must be
prefaced by an ``await`` keyword.

How can synchronous code set an asynchronous event?
---------------------------------------------------

If you need to coordinate events between async and synchronous code, use
a ``UniversalEvent`` object.  For example::

    from curio import UniversalEvent

    evt = UniversalEvent()

    def sync_func():
        ...
        evt.set()

    async def async_func():
        await evt.wait()
        ...

A ``UniversalEvent`` allows setting and waiting in both synchronous and asynchronous
code.  You can flip the roles around as well::

    def sync_func():
        evt.wait()
        ...

    async def async_func():
        ...
        await evt.set()

Note: Waiting on an event in a synchronous function should take place in a separate
thread to avoid blocking the kernel loop.

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


How can two different Python interpreters send messages to each other?
----------------------------------------------------------------------

Use a Curio ``Channel`` instance to set up a communication channel.
For example, you could make a producer program like this::

    # producer.py
    from curio import Channel, run

    async def producer(ch):
        c = await ch.accept(authkey=b'peekaboo')
        for i in range(10):
            await c.send(i)          # Send some data
        await c.send(None)

    if __name__ == '__main__':
       ch = Channel(('localhost', 30000))
       run(producer, ch)

Now, make a consumer program::

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
        run(consumer, ch)

Run each program separately and you should see messages received
by the consumer program.

Channels allow arbitrary Python objects to be sent and received
as messages as long as they are compatible with ``pickle``. 

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
