Curio - A Tutorial Introduction
===============================

Curio is a modern library for performing reliable concurrent I/O using
Python coroutines and the explicit async/await syntax introduced in
Python 3.5.  Its programming model is based on cooperative
multitasking and common system programming abstractions such as
threads, sockets, files, subprocesses, locks, and queues.  Under
the covers, it is based on a task queuing system, not a callback-based
event loop.  

This tutorial will take you through the basics of creating and 
managing tasks in curio as well as some useful debugging features. 
Various I/O related features come a bit later.

Getting Started
---------------

Here is a simple curio hello world program--a task that prints a simple
countdown as you wait for your kid to put their shoes on::
 
    # hello.py
    import curio
    
    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(countdown(10))

Run it and you'll see a countdown.  Yes, some jolly fun to be
sure. Curio is based around the idea of tasks.  Tasks are functions
defined as coroutines using the ``async`` syntax.  To run a task, you
create a ``Kernel`` instance, then invoke the ``run()`` method with a
task.  A task runs like a separate execution thread with one important
difference--tasks can only be preempted on statements prefaced by an
``await``.  This is cooperative multitasking.  However, just to be clear,
curio is not using threads to implement tasks under the covers.

Tasks
-----

Let's add a few more tasks into the mix::

    # hello.py
    import curio

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    async def kid():
        print('Building the Millenium Falcon in Minecraft')
        await curio.sleep(1000)

    async def parent():
        kid_task = await curio.spawn(kid())
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown(10))
        await count_task.join()

        print("We're leaving!")
        await kid_task.join()
        print("Leaving")

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(parent())

This program illustrates the process of creating and joining with
tasks.  Here, the ``parent()`` task uses the ``curio.spawn()``
coroutine to launch a new child task.  After sleeping briefly, it then
launches the ``countdown()`` task.  The ``join()`` method is used to
wait for a task to finish.  In this example, the parent first joins
with ``countdown()`` and then with ``kid()`` before trying to
leave. If you run this program, you'll see it produce the following
output::

    bash % python3 hello.py
    Building the Millenium Falcon in Minecraft
    Let's go
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    T-minus 6
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    We're leaving!
    .... hangs ....

At this point, the program appears hung.  The child is sleeping for
the next 1000 seconds, the parent is blocked on ``join()`` and nothing
much seems to be happening--this is the mark of all good concurrent
programs (hanging that is).  Change the last part of the program to
create the kernel with the monitor enabled::

    ...
    if __name__ == '__main__':
        kernel = curio.Kernel(with_monitor=True)
        kernel.run(parent())

Run the program again. You'd really like to know what's happening?
Yes?  Open up another terminal window and connect to the monitor as
follows::

    bash % python3 -m curio.monitor
    Curio Monitor:  4 tasks running
    Type help for commands
    curio > 

See what's happening by typing ``ps``::

    curio > ps
    Task   State        Cycles     Timeout Task                                               
    ------ ------------ ---------- ------- --------------------------------------------------
    1      TIME_SLEEP   845        0.05770 Monitor.monitor_task                              
    2      TASK_JOIN    5          None    parent                                            
    3      TIME_SLEEP   1          915.534 kid                                               
    curio > 

In the monitor, you can see a list of the active tasks.  You can see
that the parent is waiting to join and that the kid is sleeping for
another 915 seconds.  If you type ``ps`` again, you'll see the timeout
value change. Although you're in the monitor--the kernel is still
running underneath.  Actually, you'd like to know more about what's
happening. You can get the stack trace of any task using the ``where``
command::

    curio > where 2
    Stack for Task(id=2, <coroutine object parent at 0x1058e7258>, state='TASK_JOIN') (most recent call last):
      File "hello.py", line 23, in parent
        await kid_task.join()
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 86, in join
        await _join_task(self, timeout)
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 631, in _join_task
        yield ('_trap_join_task', task, timeout)

    curio > where 3
    Stack for Task(id=3, <coroutine object kid at 0x1058e7360>, state='TIME_SLEEP') (most recent call last):
      File "hello.py", line 12, in kid
        await curio.sleep(1000)
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 687, in sleep
        await _sleep(seconds)
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 605, in _sleep
        yield ('_trap_sleep', seconds)

    curio > 

Actually, that kid is just being super annoying.  Let's cancel their
world and let the parent get on with their business::

    curio > cancel 3
    Cancelling task 3
    curio > 

Back in the running program, you should see the "Leaving!" message and
the program quit.

Debugging is an important feature of curio and by using the monitor,
you see what's happening as tasks run.  You can find out where tasks
are blocked and you can cancel any task that you want.  However, it's
not necessary to do this in the monitor.  Change the parent task to
include a timeout and a cancellation request like this::

    async def parent():
        kid_task = await curio.spawn(kid())
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown(10))
        await count_task.join()

        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join())
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print("Leaving!")

If you run this version, the parent will wait 10 seconds for the child to join.  If not, the child is
forcefully cancelled.  Problem solved. Now, if only real life were this easy.

Of course, all is not lost in the child.  If desired, they can catch the cancellation request
and cleanup. For example::

    async def kid():
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

Now your program should produce output like this::

    bash % python3 hello.py
    Building the Millenium Falcon in Minecraft
    Let's go
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    T-minus 6
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    We're leaving!
    I warned you!
    Fine. Saving my work.
    Leaving!

By now, you have the basic gist of the curio task model. You can
create tasks, join tasks, and cancel tasks.  Even if a task appears to
be blocked for a long time, it can be cancelled by another task or a
timeout. You have a lot of control over the environment.

Task Synchronization
--------------------

Although threads are not used to implement curio, you still might have
to worry about task synchronization issues (e.g., if more than one
task is working with mutable state).  For this purpose, curio provides
``Event``, ``Lock``, ``Semaphore``, and ``Condition`` objects.  For
example, let's introduce an event that makes the child wait for the
parent's permission to start playing::

    start_evt = curio.Event()

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

    async def parent():
        kid_task = await curio.spawn(kid())
        await curio.sleep(5)

        print("Yes, go play")
        await start_evt.set()
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown(10))
        await count_task.join()

        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join())
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print("Leaving!")

All of the synchronization primitives work the same way that they do
in the ``threading`` module.  The main difference is that all operations
must be prefaced by ``await``. Thus, to set an event you use ``await
start_evt.set()`` and to wait for an event you use ``await
start_evt.wait()``. 

All of the synchronization methods also support timeouts. So, if the
kid wanted to be rather annoying, they could use a timeout to
repeatedly nag like this::

    async def kid():
        while True:
	    try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait())
                break
            except curio.TaskTimeout:
	        print('Wha!?!')
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

Signals
-------

What kind of helicopter parent lets their child play Minecraft for a measly 5
seconds?  Instead, let's have the parent allow the child to play as
much as they want until a Unix signal arrives, indicating that it's
time to go.  Modify the code to wait on a ``SignalSet`` like this::

    import signal, os

    async def parent():
        print('Parent PID', os.getpid())
        kid_task = await curio.spawn(kid())
        await curio.sleep(5)

        print("Yes, go play")
        await start_evt.set()
        
        await curio.SignalSet(signal.SIGHUP).wait()
     
        print("Let's go")
        count_task = await curio.spawn(countdown(10))
        await count_task.join()
        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join())
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print("Leaving!")

If you run this program, the parent lets the kid play 
indefinitely--well, until a ``SIGHUP`` arrives.  When you run the
program, you'll see this::

    bash % python3 hello.py
    Parent PID 36069
    Can I play?
    Wha!?!
    Can I play?
    Wha!?!
    Can I play?
    Wha!?!
    Can I play?
    Wha!?!
    Can I play?
    Yes, go play
    Building the Millenium Falcon in Minecraft

Don't forget, if you're wondering what's happening, you can always go to
a different terminal window and drop into the curio monitor::

    bash % python3 -m curio.monitor

    Curio Monitor: 4 tasks running
    Type help for commands
    curio > ps
    Task   State        Cycles     Timeout Task                                               
    ------ ------------ ---------- ------- --------------------------------------------------
    1      TIME_SLEEP   236        0.06724 Monitor.monitor_task                              
    2      SIGNAL_WAIT  5          None    parent                                            
    3      TIME_SLEEP   6          980.676 kid                                               
    4      READ_WAIT    1          None    Kernel._kernel_task                               
    curio > 

Here you see the parent waiting on a signal and the kid sleeping await for another 796 seconds.
If you want to initiate the signal, go to a separate terminal and type this::

    bash % kill -HUP 36069

Alternatively, you can initiate the signal by typing this in the monitor::

    curio > signal SIGHUP

In either case, you'll see the parent wake up, do the countdown and
proceed to cancel the child.  Very good.

Number Crunching and Blocking Operations
----------------------------------------

Now, suppose for a moment that the kid has decided, for reasons
unknown, that building the Millenium Falcon requires computing a sum
of larger and larger Fibonacci numbers using an exponential algorithm
like this::

    def fib(n):
        if n <= 2:
            return 1
        else:
            return fib(n-1) + fib(n-2)

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            total = 0
            for n in range(50):
                 total += fib(n)
        except curio.CancelledError:
            print('Fine. Saving my work.')

If you run this version, you'll find that the entire kernel becomes
unresponsive.  The monitor doesn't work, signals aren't caught, and
there appears to be no way to get control back.  The problem here is
that the kid is hogging the CPU and never yields.  Important lesson:
curio does not provide preemptive scheduling. If a task decides to
compute large Fibonacci numbers or mine bitcoins, everything will block
until it's done. Don't do that.

If you know that work might take awhile, you can have it execute in a
separate process. Change the code to use ``curio.run_cpu_bound()`` like
this::

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            total = 0
            for n in range(50):
                total += await curio.run_cpu_bound(fib, n)
        except curio.CancelledError:
            print('Fine. Saving my work.')

In this version, the kernel remains fully responsive because the CPU
intensive work is being carried out in a subprocess. You should be
able to run the monitor, send the signal, and see the shutdown occur
as before. 

The problem of blocking might also apply to other operations involving
I/O.  For example, accessing a database or calling out to other
libraries.  In fact, any operation not preceded by an explicit
``await`` might block.  If you know that blocking is possible, use the
``curio.run_blocking()`` coroutine.
This arranges to have the computation
carried out in a separate thread. For example::

    import time

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            total = 0
            for n in range(50):
                total += await curio.run_cpu_bound(fib, n)
		# Rest for a bit
		await curio.run_blocking(time.sleep, n)
        except curio.CancelledError:
            print('Fine. Saving my work.')
    
Note: ``time.sleep()`` has only been used to illustrate blocking in an outside
library. ``curio`` already has its own sleep function so if you really need to
sleep, use that instead.

A Caution: When a task delegates work to a subprocess or thread using
the ``run_cpu_bound()`` or ``run_blocking()`` functions, that work runs
outside the direct control of curio.  This means that whatever thread
or process is handling the request will likely run until the requested
work has been fully completed.  You can cancel a task that is waiting
for the result, but be aware that doing so might create a kind of
"zombie" worker left behind.  In this case, the eventual result is
discarded when the worker finally completes.

A Simple Echo Server
--------------------

Now that you've got the basics down, let's look at some I/O. Here
is a simple echo server written directly with sockets using curio::

    from curio import Kernel, spawn
    from curio.socket import *
    
    async def echo_server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen(5)
        print('Server listening at', address)
        async with sock:
            while True:
                client, addr = await sock.accept()
                await spawn(echo_client(client, addr))
    
    async def echo_client(client, addr):
        print('Connection from', addr)
        async with client:
             while True:
                 data = await client.recv(1000)
                 if not data:
                     break
                 await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(echo_server(('',25000)))

Run this program and try connecting to it using a command such as ``nc``
or ``telnet``.  You'll see the program echoing back data to you.  Open
up multiple connections and see that it handles multiple client
connections perfectly well::

    bash % nc localhost 25000
    Hello                 (you type)
    Hello                 (response)
    Is anyone there?      (you type)
    Is anyone there?      (response)
    ^C
    bash %
    
If you've written a similar program using sockets and threads, you'll
find that this program looks nearly identical except for the use of
``async`` and ``await``.  Any operation that involves I/O, blocking, or
the services of the kernel is prefaced by ``await``.  

Carefully notice that we are using the module ``curio.socket`` instead
of the built-in ``socket`` module here.  Under the covers, ``curio.socket``
is actually just a wrapper around the existing ``socket`` module.  All
of the existing functionality of ``socket`` is available, but all of the
operations that might block have been replaced by coroutines and must be
preceded by an explicit ``await``. 

The use of an asynchronous context manager might be something new.  For
example, you'll notice the code uses this::

    async with sock:
        ...

Normally, a context manager takes care of closing a socket when you're
done using it.  The same thing happens here.  However, because you're
operating in an environment of cooperative multitasking, you should
use the asynchronous variant instead.   As a general rule, all I/O
related operations in curio will use the ``async`` form.

A lot of the above code involving sockets is fairly repetitive.  Instead
of writing the part that sets up the server, you can simplify the above example
using ``run_server()`` like this::

    from curio import Kernel, spawn, run_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(1000)
            if not data:
                break
            await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(run_server('', 25000, echo_client))

The ``run_server()`` coroutine takes care of a few low-level details 
such as creating the server socket and binding it to an address.  It
also takes care of properly closing the client socket so you no longer
need the extra ``async with client`` statement from before.

A Stream-Based Echo Server
--------------------------

In certain cases, it might be easier to work with a socket connection
using a file-like stream interface.  Here is an example::

    from curio import Kernel, spawn, run_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        reader, writer = client.make_streams()
        while True:
            data = await reader.read(1000)
            if not data:
                break
            await writer.write(data)
        print('Connection closed')

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(run_server('', 25000, echo_client))

The ``socket.make_streams()`` method can be used to create a pair of
file-like objects for reading and writing.  On this objects, you would
now use standard file methods such as ``read()``, ``readline()``, and
``write()``.  One feature of streams is that you can easily read data
line-by-line using an ``async for`` statement like this::

    from curio import Kernel, spawn, run_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        reader, writer = client.make_streams()
        async for line in reader:
            await writer.write(line)
        print('Connection closed')
	await reader.close()
	await writer.close()

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(run_server('', 25000, echo_client))

This is potentially useful if you're writing code to read HTTP headers or
some similar task.

A Managed Echo Server
---------------------

Let's make a slightly more sophisticated echo server that responds
to a Unix signal::

    import signal
    from curio import Kernel, spawn, SignalSet, CancelledError, run_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        try:
            while True:
                data = await client.recv(1000)
                if not data:
                    break
                await client.sendall(data)
            print('Connection closed')
        except CancelledError:
            await client.sendall(b'Server going down\n')
    
    async def main(host, port):
        while True:
            async with SignalSet(signal.SIGHUP) as sigset:
                print('Starting the server')
                serv_task = await spawn(run_server(host, port, echo_client))

		# Wait for a restart signal
                await sigset.wait()

		# Cancel the server and all of its child tasks
                print('Server shutting down')
                await serv_task.cancel_children()
                await serv_task.cancel()

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(main('', 25000))


In this code, the ``main()`` coroutine launches the server, but then
waits for the arrival of a ``SIGHUP`` signal.  When received, it first
cancels all of the child tasks created by the server, then cancels the
server itself, and restarts.  An interesting thing about this
cancellation is that each task keeps a record of its active
children (i.e., all of the connected clients).  The ``task.cancel_children()``
method sends a cancellation request to the child tasks. The ``echo_client()``
coroutine has been programmed to catch the resulting cancellation
exception and perform a clean shutdown, sending a message back to the
client that a shutdown is occurring.  Just to be clear, if there were
a 1000 connected clients at the time the restart occurs, the server
would drop all 1000 clients at once and start fresh with no active
connections.   

Making Connections
------------------

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
        kernel = curio.Kernel()
        kernel.run(main())

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
        kernel = curio.Kernel()
        kernel.run(main())

At this point it's worth noting that the primary purpose of curio is
merely concurrency and I/O.  You can create sockets and you can apply
things such as SSL to them. However, curio doesn't implement any
application-level protocols such as HTTP.  Think of curio as a base-layer
for doing that.

An SSL Server
-------------

Since we're on the subject of SSL, here's an example of a server that speaks
SSL::

    import curio
    from curio import ssl
    import time

    KEYFILE = "privkey_rsa"       # Private key
    CERTFILE = "certificate.crt"  # Server certificate
 
    async def handler(client, addr):
        reader, writer = client.make_streams()

	# Read the HTTP request
        async for line in reader:
           line = line.strip()
           if not line:
               break
           print(line)

	# Send a response
        await writer.write(
    b'''HTTP/1.0 200 OK\r
    Content-type: text/plain\r
    \r
    If you're seeing this, it probably worked. Yay!
    ''')
        await writer.write(time.asctime().encode('ascii'))
	await reader.close()
	await writer.close()

    if __name__ == '__main__':
        kernel = curio.Kernel()
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)
        kernel.run(curio.run_server('', 10000, handler, ssl=ssl_context))

The ``curio.ssl`` submodule is a wrapper around the ``ssl`` module in the standard
library.  It has been modified slightly so that functions responsible for wrapping
sockets return a socket compatible with curio.  Otherwise, you'd use it the same
way as the normal ``ssl`` module.

To test this out, point a browser at ``https://localhost:10000`` and see if you
get a readable response.  The browser might yell at you with some warnings
about the certificate if it's self-signed or misconfigured in some way. However, the
example shows the basic steps involved in using SSL with curio.

Blocking I/O
------------

Normally, all of the I/O you perform in curio will be non-blocking,
using functions that make explicit use of ``await``.  However, you may
encounter situations where you want to interoperate with existing
synchronous code outside of curio.  To do this, you can temporarily put sockets and
streams into blocking mode and expose the raw socket or file
underneath.  Use the ``blocking()`` context manager method as shown here::

    from curio import Kernel, spawn, run_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(1000)
            if not data:
                break

	    # Temporarily enter blocking mode and use as a normal socket
            with client.blocking() as _client:
                _client.sendall(data)

        print('Connection closed')

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(run_server('', 25000, echo_client))

The ``blocking()`` method unwraps the low-level socket, places it in
blocking mode, and returns it back to you.  In this example the
``_client`` variable is the raw ``socket`` object as created by Python's
``socket`` module.  You could pass it to any function that expects to
work with a normal socket.  Just be aware that any I/O operations on
it could potentially block the curio kernel.  If you're not sure,
combine your operation with the ``run_blocking()`` function. For
example::

    from curio import Kernel, spawn, run_server, run_blocking

    async def echo_client(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(1000)
            if not data:
                break

	    # Temporarily enter blocking mode
            with client.blocking() as _client:
                await run_blocking(_client.sendall, data)

        print('Connection closed')

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.run(run_server('', 25000, echo_client))

Normally, you wouldn't do this for such a operation like ``sendall()``.  However,
the combination of the ``blocking()`` method and ``run_blocking()`` function
could be used to implement a hybrid server design where you use curio
to coordinate a very large collection of mostly inactive connections and a
thread-pool to carry operations in previously written synchronous
code.

Subprocesses
------------

Curio provides a wrapper around the ``subprocess`` module for launching subprocesses.
For example, suppose you wanted to write a task to watch the output of the ``ping``
command in real time::

    from curio import subprocess
    import curio

    async def main():
        p = subprocess.Popen(['ping', 'www.python.org'], 
	                     stdout=subprocess.PIPE)
        async for line in p.stdout:
            print('Got:', line.decode('ascii'), end='')

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(main())

In addition to ``Popen()``, you can also use higher level functions
such as ``subprocess.run()`` and ``subprocess.check_output()``.  For example::

    from curio import subprocess
    async def main():
        try:
            out = await subprocess.check_output(['netstat', '-a'])
        except subprocess.CalledProcessError as e:
            print('It failed!', e)

These functions operate exactly as they do in the normal
``subprocess`` module except that they're written on top of the
``curio`` kernel.  There is no blocking and no use of hidden threads.

Intertask Communication
-----------------------

If you have multiple tasks and want them to communicate, use a ``Queue``.
For example::

    # prodcons.py

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
        kernel = curio.Kernel()
        kernel.run(main())

Curio provides the same synchronization primitives as found in the built-in
``threading`` module.  The same techniques used by threads can be used with
curio.

Programming Advice
------------------

At this point, you should have enough of the core concepts to get going. 
Here are a few programming tips to keep in mind:

- When writing code, think thread programming and synchronous code.
  Tasks execute like threads and would need to be synchronized in much
  the same way.  However, unlike threads, tasks can only be preempted
  on statements that explicitly use ``await`` or ``async``.

- Curio uses the same I/O abstractions that you would use in normal
  synchronous code (e.g., sockets, files, etc.).  Methods have the
  same names and perform the same functions.  However, all operations
  that potentially involve I/O or blocking will always be prefaced by an
  explicit ``await`` keyword.  

- Be extra wary of any library calls that do not use an explicit
  ``await``.  Although these calls will work, they could potentially
  block the kernel on I/O or long-running calculations.  If you know
  that either of these are possible, consider the use of the
  ``run_cpu_bound()`` or ``run_blocking()`` functions to execute the work.

Debugging Tips
--------------

A common programming mistake is to forget to use ``await``.  For example::

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            curio.sleep(5)        # Missing await
            n -= 1

This will usually result in a warning message::
   
    example.py:8: RuntimeWarning: coroutine 'sleep' was never awaited

Another possible source of failure involves attempts to use curio-wrapped sockets
and files with existing synchronous code.  Doing so might result in a ``TypeError`` or
some kind of problem related to non-blocking behavior.   If you need
to interoperate with external code, make sure you use the ``blocking()`` method
to expose the raw socket or file being used behind the scenes. For example::

    # sock is a curio socket
    with sock.blocking() as _sock:
        external_function(_sock)       # Pass to external function
        ...

For debugging a program that is otherwise running, but you're not
exactly sure what it might be doing (perhaps it's hung or deadlocked),
consider the use of the curio monitor.  For example::

    import curio
    ...
    kernel = curio.Kernel(with_monitor=True)

The monitor can show you the state of each task and you can get stack 
traces. Remember that you enter the monitor by running ``python3 -m curio.monitor``
in a separate window.

As another possible debugging tool, you can have curio launch ``pdb``
when a task crashes.  Do this::

    kernel = curio.Kernel()
    kernel.run(..., pdb=True)

Be aware that launching ``pdb`` causes the entire kernel to stop.  When
you quit ``pdb``, the kernel will resume.

More Information
----------------

The official Github page at https://github.com/dabeaz/curio should be used for bug reports,
pull requests, and other activities. 

A reference manual can be found at https://curio.readthedocs.org/en/latest/reference.html.















    







