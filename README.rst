curio - concurrent I/O
======================

Curio is a library for performing concurrent I/O and common system
programming tasks such as launching subprocesses and farming work
out to thread and process pools.  It uses Python coroutines and the
explicit async/await syntax introduced in Python 3.5.  Its programming
model is based on cooperative multitasking and existing programming
abstractions such as threads, sockets, files, subprocesses, locks, and
queues.  You'll find it to be small, fast, and fun.

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

News
----
The version 0.9 "release" of curio has a few small improvements to
sockets and some cleanup.

Quick install
-------------

``pip install git+https://github.com/dabeaz/curio.git``

An Example
----------

Here is a simple TCP echo server implemented using sockets and curio:

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

If you have programmed with threads, you find that curio looks similar.
You'll also find that the above server can handle thousands of simultaneous 
client connections even though no threads are being used under the hood.

Of course, if you prefer something a little higher level, you can have
curio take care of the fiddly bits related to setting up the server portion
of the code:

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

This is only a small sample of what's possible.  Read the `official documentation
<https://curio.readthedocs.io>`_ for more in-depth coverage.  The `tutorial 
<https://curio.readthedocs.io/en/latest/tutorial.html>`_ is a good starting point.
The `howto <https://curio.readthedocs.io/en/latest/howto.html>`_ describes how
to carry out various tasks.

Additional Features
-------------------

Curio provides additional support for SSL connections, synchronization
primitives (events, locks, recursive locks, semaphores, and condition variables),
queues, Unix signals, subprocesses, as well as running tasks in
threads and processes. The task model fully supports cancellation,
timeouts, monitoring, and other features critical to writing reliable
code.

Talks Related to Curio
----------------------

* `The Other Async (Threads + Asyncio = Love)` <https://www.youtube.com/watch?v=x1ndXuw7S0s>, Keynote talk
by David Beazley at PyGotham, 2017.

* `Fear and Awaiting in Async <https://www.youtube.com/watch?v=E-1Y4kSsAFc>`_, Keynote talk by David Beazley at PyOhio 2016.

* `Topics of Interest (Async) <https://www.youtube.com/watch?v=ZzfHjytDceU>`_, Keynote talk by David Beazley at Python Brasil 2015.

Other Resources
---------------

* `Trio <https://github.com/python-trio/trio/>`_ A different I/O library that's been inspired by Curio and shares many of its overarching ideas.

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
runs about 20% faster than comparable code using coroutines in
``asyncio`` on Python 3.6. This is on OS-X so your mileage might
vary. Curio is not as fast as servers that utilize threads, low-level
callback-based event handling (e.g., low-level protocols in
``asyncio``), or direct coding in assembly language.  However, those
approaches also don't involve coroutines (which is the whole point of
Curio). See the ``examples/benchmark`` directory of the distribution
for various testing programs.  

**Q: Is curio going to evolve into a framework?**

A: No, because evolving into a framework would mean modifying Curio to
actually do something.  If it actually did something, then people
would start using it to do things.  And then all of those things would
have to be documented, tested, and supported.  People would start
complaining about how all the things related to the various provided
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

A: No.

**Q: How big is curio?**

A: The complete library currently consists of about 3200 statements
as reported in coverage tests.

**Q: I see these warnings about not using Curio. What should I do?**

A: Has programming taught you nothing? Warnings are meant to be ignored.
Of course you should use Curio.

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



