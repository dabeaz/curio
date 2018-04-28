.. curio documentation master file, created by
   sphinx-quickstart on Thu Oct 22 09:54:26 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Curio
=====

- a small and unusual object that is considered interesting or attractive
- A Python library for concurrent I/O and systems programming.

Curio is a library for performing concurrent I/O and common system
programming tasks such as launching subprocesses and farming work
out to thread and process pools.  It uses Python coroutines and the
explicit async/await syntax introduced in Python 3.5.  Its programming
model is based on cooperative multitasking and existing programming
abstractions such as threads, sockets, files, subprocesses, locks, and
queues.  You'll find it to be small and fast.

Contents:
---------
.. toctree::
   :maxdepth: 2

   tutorial
   howto
   reference
   devel

Installation:
-------------

Curio requires Python 3.6 and Unix.  You can install it using ``pip``::

    bash % python3 -m pip install curio

For best results, however, you'll want to grab the version on Github
at https://github.com/dabeaz/curio.

An Example
----------
Here is a simple TCP echo server implemented using sockets and curio::

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
                await spawn(echo_client, client, addr)
    
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
        run(echo_server, ('',25000))

If you have programmed with threads, you'll find that curio looks similar.
You'll also find that the above server can handle thousands of simultaneous 
client connections even though no threads are being used under the covers.

Of course, if you prefer something a little higher level, you can have
curio take of the fiddly bits related to setting up the server portion
of the code::

    # echoserv.py

    from curio import run, tcp_server

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

This is only a small sample of what's possible.  The `tutorial
<https://curio.readthedocs.io/en/latest/tutorial.html>`_ is a good
starting point for more information.  The `howto
<https://curio.readthedocs.io/en/latest/howto.html>`_ has specific
recipes for solving different kinds of problems.

Additional Features
-------------------

Curio provides additional support for SSL connections, synchronization
primitives (events, locks, semaphores, and condition variables),
queues, Unix signals, subprocesses, as well as running tasks in
threads and processes. The task model fully supports cancellation,
timeouts, monitoring, and other features critical to writing reliable
code.

The Big Question: Why?
----------------------

Python already has a variety of libraries for async and event driven
I/O. So, why create yet another library?  There is no simple answer to
that question, but here are a few of the motivations for creating curio.

* Python 3 has evolved considerably as a programming language and has
  adopted many new language features that are well-suited to cleanly
  writing a library like this. For example, improved support for
  non-blocking I/O, support for delegation to subgenerators (`yield
  from`) and the introduction of explicit `async` and `await` syntax
  in Python 3.5. Curio takes full advantage of these features and is
  not encumbered by issues of backwards compatibility with legacy
  Python code written 15 years ago.

* Existing I/O libraries are mainly built on event-loops, callback
  functions, and abstractions that predate Python's proper support for
  coroutines.  As a result, they are either overly complicated or
  dependent on esoteric magic involving C extensions, monkeypatching,
  or reimplementing half of the TCP flow-control protocol.  Curio is a
  ground-up implementation that takes a different approach to the
  problem while relying upon known programming techniques involving
  sockets and files.  If you have previously written synchronous code
  using processes or threads, curio will feel familiar.  That is by
  design.

* Simplicity is an important part of writing reliable systems
  software.  When your code fails, it helps to be able to debug
  it--possibly down to the level of individual calls to the operating
  system if necessary. Simplicity matters a lot.  Simple code also
  tends to run faster. The implementation of Curio aims to be simple.
  The API for using Curio aims to be intuitive.

* It's fun. 


Under the Covers
----------------

Internally, curio is implemented entirely as a task queuing system--
much in the same model of a microkernel based operating system.  Tasks
are represented by coroutine functions declared with the `async`
keyword.  Each yield of a coroutine results in a low-level kernel
"trap" or system call.  The kernel handles each trap by moving the
current task to an appropriate waiting queue. Events (i.e., due to
I/O) and other operations make the tasks move from waiting queues back
into service.

It's important to emphasize that the underlying kernel is solely
focused on task queuing and scheduling. In fact, the kernel doesn't
even perform any I/O operations or do much of anything.  This means
that it is very small and fast.

Higher-level I/O operations are carried out by a wrapper layer that
uses Python's normal socket and file objects. You use the
same operations that you would normally use in synchronous code except
that you add ``await`` keywords to methods that might block.

Questions and Answers
---------------------

**Q: Is curio implemented using the asyncio module?**

A: No. Curio is a standalone library. Although the core of the library
uses the same basic machinery as ``asyncio`` to poll for I/O events,
the handling of those events is carried out in a completely different
manner.

**Q: Is curio meant to be a clone of asyncio?**

A: No.  Although curio provides a significant amount of overlapping
functionality, the API is different and smaller.  Compatibility with
other libaries is not a goal.

**Q: Is there any kind of overarching design philosophy?**

A: Yes and no. The "big picture" design of Curio is mainly inspired by
the kernel/user space distinction found in operating systems only it's
more of a separation into "synchronous" and "asynchronous" runtime
environments.  Beyond that, Curio tends to take rather pragmatic view
towards concurrent programming techniques more generally.  It's
probably best to view Curio as providing a base set of primitives upon
which you can build all sorts of interesting things.  However, it's
not going to dictate much in the way of religious rules on how you
structure it.

**Q: How many tasks can be created?**

A: Each task involves an instance of a ``Task`` class that
encapsulates a generator. No threads are used. As such, you're really
only limited by the memory of your machine--potentially you could have
hundreds of thousands of tasks.  The I/O functionality in curio is
implemented using the built-in ``selectors`` module.  Thus, the number
of open sockets allowed would be subject to the limits of that library
combined with any per-user limits imposed by the operating system.
 
**Q: Can curio interoperate with other event loops?**

A: It depends on what you mean by the word "interoperate."  Curio's
preferred mechanism of communication with the external world is a
queue.  It is possible to communicate between Curio, threads, and
other event loops using queues.  Curio can also submit work to 
the ``asyncio`` event loop with the provision that it must be running
separately in a different thread.

**Q: How fast is curio?**

A: In rough benchmarking of the simple echo server shown here, Curio
runs about 90% faster than comparable code using coroutines in
``asyncio`` and about 50% faster than similar code written using Trio.
This was last measured on Linux using Python 3.7b3. Keep in mind there
is a lot more to overall application performance than the performance
of a simple echo server so your mileage might vary. See the ``examples/benchmark``
dirctory for various testing programs.

**Q: Is curio going to evolve into a framework?**

A: No, because evolving into a framework would mean modifying Curio to
actually do something.  If it actually did something, then people
would start using it to do things.  And then all of those things would
have to be documented, tested, and supported.  People would start
complaining about how all the things related to the various built-in
things should have new things added to do some crazy thing.  No forget
that, Curio remains committed to not doing much of anything the best
it can.  This includes not implementing HTTP.

**Q: What are future plans?**

A: Future work on curio will primarily focus on features related to
performance, debugging, diagnostics, and reliability.  A main goal is
to provide a robust environment for running and controlling concurrent
tasks.  However, it's also supposed to be fun. A lot of time is
being spent thinking about the API and how to make it pleasant.

**Q: Is there a Curio sticker?**

A: No. However, you can make a `stencil <https://www.youtube.com/watch?v=jOW1X8-_7eI>`_

**Q: How big is curio?**

A: The complete library currently consists of about 3200 statements
as reported in coverage tests.

**Q: I see various warnings about not using Curio. What should I do?**

A: Has programming taught you nothing? Warnings are meant to be ignored.
Of course you should use Curio.  However, be aware that the main reason
you shouldn't be using Curio is that you should be using it.

**Q: Can I contribute?**

A: Absolutely. Please use the Github page at
https://github.com/dabeaz/curio as the primary point of discussion
concerning pull requests, bugs, and feature requests.

About
-----
Curio was created by David Beazley (@dabeaz).  http://www.dabeaz.com

It is a young project.  All contributions welcome.
 

