.. curio documentation master file, created by
   sphinx-quickstart on Thu Oct 22 09:54:26 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Curio
=====

- a small and unusual object that is considered interesting or attractive
- A Python library for concurrent I/O.

Curio is a modern library for performing reliable concurrent I/O using
Python coroutines and the explicit async/await syntax introduced in
Python 3.5.   Its programming model is based on cooperative
multitasking and common system programming abstractions such as
threads, sockets, files, subprocesses, locks, and queues.  Under
the covers, it is based on a task queuing system that is small, fast,
and powerful.

Contents:
---------
.. toctree::
   :maxdepth: 2

* :doc:`tutorial` 
* :doc:`reference`

Installation:
-------------

Curio requires Python 3.5 and Unix.  You can install it using ``pip``::

    bash % python3 -m pip install curio

An Example
----------
Here is a simple TCP echo server implemented using sockets and curio::

    # echoserv.py
    
    from curio import Kernel, new_task
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
                await new_task(echo_client(client, addr))
    
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

If you have programmed with threads, you'll find that curio looks similar.
You'll also find that the above server can handle thousands of simultaneous 
client connections even though no threads are being used under the covers.

Of course, if you prefer something a little higher level, you can have
curio take of the fiddly bits related to setting up the server portion
of the code::

    # echoserv.py

    from curio import Kernel, new_task, run_server

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

This is only a small sample of what's possible.  The `tutorial 
<https://curio.readthedocs.org/en/latest/tutorial.html>`_ is a good starting point
for more information.

Additional Features
-------------------

Curio provides additional support for SSL connections, synchronization
primitives (events, locks, semaphores, and condition variables),
queues, Unix signals, subprocesses, as well as thread and process
pools.  In addition, the task model fully supports cancellation,
timeouts, monitoring, and other features critical to writing reliable
code.

The Big Question: Why?
----------------------

Python already has a variety of libraries for async and event driven
I/O. So, why create yet another library?  There is no simple answer to
that question, but here are a few of the motivations for creating curio.

* Python 3 has evolved considerably as a programming language and has
  adopted many new features that are well-suited to cleanly
  writing a new I/O library. For example, improved support for
  non-blocking I/O, support for delegation to subgenerators (``yield from``) 
  and the introduction of explicit ``async`` and ``await`` syntax
  in Python 3.5. Curio takes full advantage of these features and is
  not encumbered by issues of backwards compatibility with legacy
  Python code written 15 years ago.

* Existing I/O libraries are mostly built on event-loops, callback
  functions, and custom I/O abstractions--this includes Python's own
  asyncio module.  Curio takes a completely different approach to the
  problem that focuses almost entirely on task scheduling while
  relying upon known I/O techniques involving sockets and files.  If
  you have previously written synchronous code using processes or
  threads, curio will feel familiar.

* Simplicity is an important part of writing reliable systems
  software.  When your code fails, it helps to be able to debug
  it--possibly down to the level of individual calls to the operating
  system if necessary. Simplicity matters a lot.  Simple code also
  tends to run faster. Simplicity is a major goal of Curio.

* It's fun. 

Under the Covers
----------------

Internally, curio is implemented entirely as a task queuing system--
much in the same model as how an actual operating system kernel
works. Tasks are represented by coroutine functions declared with the
``async`` keyword.  Each yield of a coroutine results in a low-level
kernel "trap" or system call.  The kernel handles each trap by moving
the current task to an appropriate waiting queue. Events (i.e., due to
I/O) and other operations make the tasks move from waiting queues back
into service.

It's important to emphasize that the kernel is solely focused on task
management, scheduling, and nothing else. In fact, the kernel doesn't
even perform any I/O operations. 
Higher-level I/O operations are carried out by a wrapper layer that
uses Python's normal socket and file objects. You use the
same operations that you would normally use in synchronous code except
that you add ``await`` keywords to methods that might block.

Questions and Answers
---------------------

**Q: Is curio implemented using the asyncio module?**

A: No. Curio is a standalone library. Although the core of the library
uses the same basic machinery as ``asyncio`` to poll for I/O events,
the handling of those events is done in a completely different manner.

**Q: Is curio meant to be a compatible clone of asyncio?**

A: No.  Although curio provides a significant amount of overlapping
functionality, some of the APIs are slightly different.  Compatibility
with other libraries is not a goal.

**Q: How many tasks can be created?**

A: Each task involves an instance of a ``Task`` class that
encapsulates a generator. No threads are used. As such, you're really
only limited by the memory of your machine--potentially you could have
hundreds of thousands of tasks.  The I/O functionality in curio is
implemented using the built-in ``selectors`` module.  Thus, the number
of open sockets allowed is subject to the limits of that library
combined with any limits imposed by the operating system.
 
**Q: Can curio interoperate with other event loops?**

A: At this time, no.  However, curio is a young project. It's
something that might be added later.

**Q: How fast is curio?**

A: In preliminary benchmarking of a simple echo server, curio runs
about 50-70% faster than ``asyncio``.  It runs about 30-40% faster
than Twisted and about 10-15% slower than gevent, both running on
Python 2.7.  This is on OS-X so your mileage might vary. See the
``examples/benchmark`` directory of the distribution for this testing
code.

**Q: Is curio going to evolve into a framework?**

A: No. The current goal is merely to provide a small, simple library
for performing concurrent I/O. It is not anticipated that curio would
evolve into a framework for implementing application level protocols
such as HTTP.  Instead, serves as a foundation for other packages
that want to provide that kind of functionality.

**Q: What are future plans?**

A: Future work on curio will primarily focus on features related to debugging, 
diagnostics, and reliability.  A primary goal is to provide a solid 
environment for running and controlling concurrent tasks.

**Q: How big is curio?**

A: The complete library currently consists of fewer than 1500 lines of
source statements.  This does not include blank lines and comments.

**Q: Can I contribute?**

A: Absolutely. Please use the Github page at
https://github.com/dabeaz/curio as the primary point of discussion
concerning pull requests, bugs, and feature requests.

About
-----
Curio was created by David Beazley (@dabeaz).  http://www.dabeaz.com

 

