Developing with Curio
=====================

So, you want to write a larger application or library that depends on
Curio? This document describes the overall philosophy behind Curio,
how it works under the covers, and how you might approach software
development using it.

Coroutines
----------

First things, first.  Curio is solely focused on solving one specific
problem--and that's the scheduling of coroutines.   This section covers
some basics.

Defining a Coroutine
^^^^^^^^^^^^^^^^^^^^

A coroutine is a function defined using ``async def`` such as this::

    async def greeting(name):
        return 'Hello ' + name

Unlike a normal function, a coroutine never executes independently.
It has to be driven by some other code.  It's low-level, but you can
drive a coroutine manually if you want::

    >>> g = greeting('Dave')
    >>> g
    <coroutine object greeting at 0x10ded14c0>
    >>> g.send(None)
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration: Hello Dave
    >>> 

Normally, you wouldn't do this though. Curio provides a high-level
function that runs a coroutine and returns its final result::

    >>> from curio import run
    >>> run(greeting('Dave'))
    'Hello Dave'
    >>>

Coroutines Calling Coroutines
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Coroutines can call other coroutines as subroutines as long as you preface the call
with the ``await`` keyword.  For example::

    async def main():
         names = ['Dave', 'Paula', 'Thomas', 'Lewis']
         for name in names:
             print(await greeting(name))

    from curio import run
    run(main())

For the most part, you can write async functions, methods, and do everything that you
would do with normal Python functions.  The use of the ``await`` in calls is important
though--if you don't do that, the called coroutine won't run and you'll start to
get crazy errors.

System Calls
^^^^^^^^^^^^

When a program runs, it executes statements one after the other until
the services of the operating system are needed (e.g., reading a file, 
receiving a network packet, etc.).  For example::

     data = sock.recv(8192)

Under the covers, this operation involves making a "system call."
System calls are different than normal functions in that they involve
making a request to the operating system kernel by executing a "trap."
A trap is like a software-generated interrupt.  When it occurs, the
running process is suspended and the operating system takes over to
handle the request.

Now, what does all of this have to do with coroutines?  As already
noted, a coroutine is not capable of running all by itself.  It has
to be driven by some other code. Go back to the earlier example::

    async def greeting(name):
        return 'Hello ' + name

To drive this code, ``send()`` is used like this:

    >>> g = greeting('Dave')
    >>> g
    <coroutine object greeting at 0x10ded14c0>
    >>> g.send(None)
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration: Hello Dave
    >>> 

The ``StopIteration`` exception looks a little weird, but that's how
coroutines signal termination.  The ``value`` attribute of the
exception holds the result of the ``return`` statement.

Now, what does this have to do with the whole system call concept?
Let's a define a very special kind of coroutine::

   from types import coroutine

   @coroutine
   def sleep(seconds):
       yield ('sleep', seconds)

This coroutine is different than the rest--it doesn't use the
``async`` syntax and it makes direct use of the ``yield`` statement
(which is not allowed in ``async`` functions).  Now, let's write a
coroutine that uses this function::

   async def main():
       print('Yawn. Getting sleepy.')
       await sleep(10)
       print('Awake at last!')

Let's drive it using the same technique as before::
 
    >>> c = main()
    >>> request = c.send(None)
    Yawn! Getting sleepy.
    >>> request
    ('sleep', 10)
    >>> 

You now see the first message and the return value
of the ``send()`` call is the tuple produced by the ``yield``
statement in the ``sleep()`` coroutine.  This is exactly the same 
concept as a trap.  The coroutine
has suspended itself and made a request (in this case, a
request to sleep for 10 seconds).   It is now up to the driver
of the code to satisfy the request.  To resume execution of
the coroutine, you call ``send()`` again with return result.
For example::

    >>> c.send(None)
    Awake at last!
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration
    >>> 

All of this might seem very low-level, but this is precisely the 
execution model of Curio.  Coroutines execute statements under the
supervision of a small kernel.  When a coroutine executes a system
call (e.g., a special coroutine that makes use of ``yield``), 
the kernel takes over and handles the request.

Keep in mind that all of this machinery is hidden from view.  Your
application code doesn't actually see the Curio kernel or involve code
that directly uses the ``yield`` statement. Those are implementation
details.  Your code will simply make a high-level call such as ``await
sleep(10)`` and it will just work.

Coroutines and Multitasking
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In many cases, system calls involve waiting or blocking.  For example,
waiting for time to elapse, waiting to receive a network packet, etc.
While waiting, it might be possible for the kernel to switch to
another coroutine that's able to run--this is multitasking.  If there are
multiple coroutines, the kernel can cycle between them by running each
one until it executes a system call, then switching to the next ready 
coroutine at that point.   Your operating system does exactly the same
thing when processes execute actual system calls.

Coroutines versus Threads
^^^^^^^^^^^^^^^^^^^^^^^^^

Code written using coroutines is very similar to code written using
threads.  To see this, here is a simple echo server that handles
concurrent clients using Python's ``threading`` module::

    # echoserv.py
    
    from socket import *
    from threading import Thread
    
    def echo_server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen(5)
        print('Server listening at', address)
        with sock:
            while True:
                client, addr = sock.accept()
                Thread(target=echo_client, args=(client, addr), daemon=True).start()
    
    def echo_client(client, addr):
        print('Connection from', addr)
        with client:
             while True:
                 data = client.recv(100000)
                 if not data:
                     break
                 client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        echo_server(('',25000))

Now, here is the same code written using coroutines and Curio::

    # echoserv.py
    
    from curio import run, spawn
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
                 data = await client.recv(100000)
                 if not data:
                     break
                 await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(echo_server(('',25000)))

Both versions of code involve the same statements and the same overall
control flow.  The key difference is that threads support
preemption whereas coroutines do not. This means that in the threaded
code, the operating system can switch threads on any statement. With
coroutines, task switching can only occur on statements that involve
``await``.

Both approaches have advantages and disadvantages.  One potential
advantage of the coroutine approach is that you explicitly know where
task switching might occur. Thus, if you're writing code that involves
tricky task synchronization or coordination, it might be easier to
reason about about its behavior.  One disadvantage of coroutines is that
any kind of long-running calculation or blocking operation can't be
preempted.  So, a coroutine might hog the CPU for an extended period
and force other coroutines to wait.  Another downside
is that code must be written to explicitly take advantage of coroutines.
Threads, on the other hand, can work with any existing Python code. 

Coroutines versus Callbacks
^^^^^^^^^^^^^^^^^^^^^^^^^^^

For I/O handling, libraries and frameworks will sometimes make use of
callback functions.  For example, here is an echo server written in
the callback style using Python's ``asyncio`` module::

    import asyncio
    from socket import *

    class EchoProtocol(asyncio.Protocol):
        def connection_made(self, transport):
            self.transport = transport
            sock = transport.get_extra_info('socket')
            try:
                sock.setsockopt(IPPROTO_TCP, TCP_NODELAY, 1)
            except (OSError, NameError):
                pass

        def connection_lost(self, exc):
            self.transport = None

        def data_received(self, data):
            self.transport.write(data)

    if __name__ == '__main__':
        loop = asyncio.get_event_loop()
        coro = loop.create_server(EchoProtocol, '', 25000)
        srv = loop.run_until_complete(coro)
        loop.run_forever()

In this code, different methods of the ``EchoProtocol`` class are
triggered in response to I/O events. 

Programming with callbacks is a well-known technique for I/O handling
that is often used in programming languages without proper support for
coroutines.  It can be efficient, but it also tends to result in code
that's described as a kind of "callback hell."  These programs can
easily consist of thousands of tiny functions with no immediately
obvious strand of control flow tying them together. 

Coroutines restore a lot of sanity to the overall programming model.
The overall control-flow is much easier to follow and the number of
required functions tends to be significantly less. 

Historical Perspective
^^^^^^^^^^^^^^^^^^^^^^

Coroutines were first invented in the earliest days of computing to
solve programs related to multitasking and concurrency.  Given the
simplicity and benefits of the programming model, one might wonder why
they haven't been used more often.

A big part of this is really due to the lack of proper support in
mainstream programming languages used to write production software.
For example, languages such as Pascal, C/C++, and Java don't support
coroutines. Thus, it's not a technique that most programmers would
consider.  Even in Python, proper support for coroutines has taken a
long time to emerge.  Over the years, various projects have explored
coroutines in various forms, usually involving sneaky hacks surrounding
generator functions and C extensions.  The addition of the ``yield from``
construct in Python 3.3 greatly simplified the program of writing
coroutine libraries.  The emergence of ``async/await`` in Python 3.5
takes a huge stride in making coroutines more of a first-class object
in the Python world.   This is really the starting point for Curio.

Scheduling Layer
----------------

Programming Techniques
----------------------













