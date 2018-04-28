curio - concurrent I/O
======================

Curio is a library of building blocks for performing concurrent I/O
and common system programming tasks such as launching subprocesses,
working with files, and farming work out to thread and process pools.
It uses Python coroutines and the explicit async/await syntax
introduced in Python 3.5.  Its programming model is based on
cooperative multitasking and existing programming abstractions such as
threads, sockets, files, subprocesses, locks, and queues.  You'll find
it to be small, fast, and fun.

Curio has no third-party dependencies and is not built using the
standard asyncio module.  Most users will probably find it to be a bit
too-low level--it's probably best to think of it as a library for building
libraries.  Although you might not use it directly, many of its ideas
have influenced other libraries with similar functionality.

Important Disclaimer
--------------------

Curio is experimental software that currently only works on POSIX
systems (OS X, Linux, etc.).  Although it is a work in progress, it is
extensively documented and has a fairly comprehensive test suite.
Just be aware that the programming API is fluid and could change at
any time.  Although curio can be installed via pip, the version
uploaded on PyPI is only updated occasionally.  You'll probably get
better results using the version cloned from github.  You'll also want
to make sure you're using Python 3.6. Of course, your mileage might
vary.

Quick install
-------------

``pip install git+https://github.com/dabeaz/curio.git``

A Simple Example
-----------------

Curio provides the same basic primitives that you typically find with
thread programming.  For example, here is a simple concurrent TCP echo
server implemented using sockets and Curio:

.. code:: python

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
                await spawn(echo_client, client, addr, daemon=True)
    
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
client connections even though no threads are being used under the hood.

Of course, if you prefer something a little higher level, you can have
curio take care of the fiddly bits related to setting up the server
portion of the code:

.. code:: python

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

A Complex Example
-----------------

The above example only illustrates a few basics.  You'll find Curio to
be a bit more interesting if you try something more complicated.

As an example, one such problem is that of making a client TCP
connection on a dual IPv4/IPv6 network.  On such networks, functions
such as ``socket.getaddrinfo()`` return a series of possible
connection endpoints.  To make a connection, each endpoint is tried
until one of them succeeds.  However, serious usability problems
arise if this is done as a purely sequential process since bad connection
requests might take a considerable time to fail.  It's better to try
several concurrent connection requests and use the first one that
succeeds.

One solution to this problem is the so-called "Happy Eyeballs"
algorithm as described in `RFC 6555
<https://tools.ietf.org/html/rfc6555>`_.  You can read the RFC for more
details, but Nathaniel Smith's `Pyninsula Talk
<https://www.youtube.com/watch?v=i-R704I8ySE>`_ talk gives a pretty good
overview of the problem and one possible implementation solution.  The
gist of the algorithm is that a client makes concurrent time-staggered
connection requests and uses the first connection that is successful.
What makes it tricky is that the algorithm involves a combination of
timing, concurrency, and task cancellation--something that would be
pretty hard to coordinate using a classical approach involving threads.

Here is an example of how the problem can be solved with Curio:

.. code:: python

    from curio import socket, TaskGroup, ignore_after, run
    import itertools

    async def open_tcp_stream(hostname, port, delay=0.3):
        # Get all of the possible targets for a given host/port
        targets = await socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        if not targets:
            raise OSError(f'nothing known about {hostname}:{port}')

        # Cluster the targets into unique address families (e.g., AF_INET, AF_INET6, etc.)
        # and make sure the first entries are from a different family.
        families = [ list(g) for _, g in itertools.groupby(targets, key=lambda t: t[0]) ]
        targets = [ fam.pop(0) for fam in families ]
        targets.extend(itertools.chain(*families))

        # List of accumulated errors to report in case of total failure
        errors = []

        # Task group to manage a collection concurrent tasks.
        # Cancels all remaining once an interesting result is returned.
        async with TaskGroup(wait=object) as group:

            # Attempt to make a connection request
            async def try_connect(sockargs, addr, errors):
                sock = socket.socket(*sockargs)
                try:
                    await sock.connect(addr)
                    return sock
                except Exception as e:
                    await sock.close()
                    errors.append(e)
 
           # Walk the list of targets and try connections with a staggered delay
            for *sockargs, _, addr in targets:
                await group.spawn(try_connect, sockargs, addr, errors)
                async with ignore_after(delay):
                     sock = await group.next_result()
                     if sock:
                         break

        if group.completed:
            return group.completed.result
        else:
            raise OSError(errors)

    # Example use:
    async def main():
        result = await open_tcp_stream('www.python.org', 80)
        print(result)

    run(main)

This might require a bit of study, but the key to this solution is the
Curio ``TaskGroup`` instance which represents a collection of managed
concurrently executing tasks.  Tasks created in the group aren't
allowed to live beyond the lifetime of the code defined in the
associated ``async with`` context manager block.  Inside this block,
you'll find statements that spawn tasks and wait for a result to come
back with a time delay.  When a successful connection is made, it is
returned and any remaining tasks are magically cancelled.   That's 
pretty neat.

Thread Interoperability Example
-------------------------------

One of the more notable features of Curio is how it can interoperate with
traditional synchronous code.  For example, maybe you have a standard
function that reads off a queue like this:

.. code:: python

    def consumer(queue):
        while True:
            item = queue.get()
            if item is None:
                break
            print('Got:', item)

There is nothing too special here. This is something you might write using standard thread-programming. 
However, it's easy to make this code read data sent from a Curio async task.  Use a ``UniversalQueue``
object like this:

.. code:: python
   
    from curio import UniversalQueue, run, sleep, spawn
    from threading import Thread

    async def producer(n, queue):
        for x in range(n):
            await queue.put(x)
            await sleep(1)
        await queue.put(None)

    async def main():
        q = UniversalQueue()
        Thread(target=consumer, args=(q,)).start()
        t = await spawn(producer, 10, q)
        await t.join()

    run(main)

As the name implies, ``UniversalQueue`` is a queue that can be used in
both synchronous and asynchronous code.  The API is the same. It just
works.

Additional Features
-------------------

Curio provides additional support for SSL connections, synchronization
primitives (events, locks, recursive locks, semaphores, and condition
variables), queues, Unix signals, subprocesses, as well as running
tasks in threads and processes. The task model fully supports
cancellation, timeouts, monitoring, and other features critical to
writing reliable code.

The two examples shown are only a small sample of what's possible.
Read the `official documentation <https://curio.readthedocs.io>`_ for
more in-depth coverage.  The `tutorial
<https://curio.readthedocs.io/en/latest/tutorial.html>`_ is a good
starting point.  The `howto
<https://curio.readthedocs.io/en/latest/howto.html>`_ describes how to
carry out various tasks.  The `developer guide <https://curio.readthedocs.io/en/latest/devel.html>`_
describes the general design of Curio and how to use it in more detail.

Talks Related to Curio
----------------------

Much of Curio's design and issues related to async programming more generally have
been described in various conference talks.

* `The Other Async (Threads + Asyncio = Love) <https://www.youtube.com/watch?v=x1ndXuw7S0s>`_, Keynote talk by David Beazley at PyGotham, 2017.

* `Fear and Awaiting in Async <https://www.youtube.com/watch?v=E-1Y4kSsAFc>`_, Keynote talk by David Beazley at PyOhio 2016.

* `Topics of Interest (Async) <https://www.youtube.com/watch?v=ZzfHjytDceU>`_, Keynote talk by David Beazley at Python Brasil 2015.

* `Python Concurrency from the Ground Up (LIVE) <https://www.youtube.com/watch?v=MCs5OvhV9S4>`_, talk by David Beazley at PyCon 2015.

Additional Resources
--------------------

* `Trio <https://github.com/python-trio/trio/>`_ A different I/O library that was initially inspired by Curio.

* `Some thoughts on asynchronous API design in a post-async/await world <https://vorpus.org/blog/some-thoughts-on-asynchronous-api-design-in-a-post-asyncawait-world/>`_, by Nathaniel Smith.

* `A Tale of Event Loops <https://github.com/AndreLouisCaron/a-tale-of-event-loops>`_, by André Caron.


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
  functions, futures, and various abstractions that predate Python's
  proper support for coroutines.  As a result, they are either overly
  complicated or dependent on esoteric magic involving C extensions,
  monkeypatching, or reimplementing half of the TCP flow-control
  protocol.  Curio is a ground-up implementation that takes a
  different approach to the problem while relying upon known
  programming techniques involving sockets and files.  If you have
  previously written synchronous code using processes or threads,
  curio will feel familiar.  That is by design.

* Simplicity is an important part of writing reliable systems
  software.  When your code fails, it helps to be able to debug
  it--possibly down to the level of individual calls to the operating
  system if necessary. Simplicity matters a lot.  Simple code also
  tends to run faster. The implementation of Curio aims to be simple.
  The API for using Curio aims to be intuitive. 

* It's fun. 

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

Documentation
-------------

Read the official docs here: https://curio.readthedocs.io

Discussion Forum
----------------

A discussion forum for Curio is available at http://forum.dabeaz.com/c/curio.  
Please go there to ask questions and find out whats happening with the project.

Contributors
------------

- David Beazley
- Brett Cannon
- Nathaniel Smith
- Alexander Zhukov
- Laura Dickinson

About
-----
Curio was created by David Beazley (@dabeaz).  http://www.dabeaz.com

It is a young project.  All contributions welcome.


.. |--| unicode:: U+2013   .. en dash
.. |---| unicode:: U+2014  .. em dash, trimming surrounding whitespace
   :trim:



