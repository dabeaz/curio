curio - concurrent I/O
======================

Curio is a library for performing concurrent I/O and common systems
programming tasks such as controlling subprocesses and farming work
out to thread and process pools.  It uses Python coroutines and the
explicit async/await syntax introduced in Python 3.5.  Its programming
model is based on cooperative multitasking and existing programming
abstractions such as threads, sockets, files, subprocesses, locks, and
queues.  Under the covers, it implements a task queuing system that is
small, flexible, and fast.

Important Disclaimer
--------------------
Curio is experimental software that currently only works on POSIX systems
(OS X, Linux, etc.).  Use at your own peril. 

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
        run(echo_server(('',25000)))

If you have programmed with threads, you find that curio looks similar.
You'll also find that the above server can handle thousands of simultaneous 
client connections even though no threads are being used under the covers.

Of course, if you prefer something a little higher level, you can have
curio take care of the fiddly bits related to setting up the server portion
of the code:

.. code:: python

    # echoserv.py

    from curio import run, run_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(1000)
            if not data:
                break
            await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(run_server('', 25000, echo_client))

This is only a small sample of what's possible.  Read the `official documentation
<https://curio.readthedocs.org>`_ for more in-depth coverage.  The `tutorial 
<https://curio.readthedocs.org/en/latest/tutorial.html>`_ is a good starting point.

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
  writing a new I/O library. For example, improved support for
  non-blocking I/O, support for delegation to subgenerators (`yield
  from`) and the introduction of explicit `async` and `await` syntax
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

* Curio is a powerful library in a small package.  An emphasis is
  placed on implementation simplicity.  Simplicity is an important
  part of writing reliable systems software.  When your code fails, it
  helps to be able to debug it--possibly down to the level of
  individual calls to the operating system if necessary. Simplicity
  matters a lot.  Simple code also tends to run faster.


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
focused on task management and scheduling. In fact, the kernel doesn't
even perform any I/O operations.  This means that it is very small and
fast.

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

**Q: Is curio meant to be a clone of asyncio?**

A: No.  Although curio provides a significant amount of overlapping
functionality, the API is different (and frankly much simpler). 
Compatibility with other libaries is not a goal.

**Q: How many tasks can be created?**

A: Each task involves an instance of a ``Task`` class that
encapsulates a generator. No threads are used. As such, you're really
only limited by the memory of your machine--potentially you could have
hundreds of thousands of tasks.  The I/O functionality in curio is
implemented using the built-in ``selectors`` module.  Thus, the number
of open sockets allowed would be subject to the limits of that library
combined with any per-user limits imposed by the operating system.
 
**Q: Can curio interoperate with other event loops?**

A: At this time, no.  However, curio is a young project. It's
something that might be added later.

**Q: How fast is curio?**

A: In benchmarking of a simple echo server, curio runs more than 100%
faster than ``asyncio``.  It runs about 50-60% faster than Twisted and
at about the same speed as gevent. This is on OS-X so your mileage
might vary. See the ``examples/benchmark`` directory of the
distribution for this testing code.

**Q: Is curio going to evolve into a framework?**

A: No. The current goal is merely to provide a small, simple library
for performing concurrent I/O and common systems operations involving
interprocess communication and subprocesses. It is not anticipated
that curio would evolve into a framework for implementing application
level protocols such as HTTP.  Instead, it might serve as a foundation
for other packages that want to provide that kind of functionality.

**Q: What are future plans?**

A: Future work on curio will primarily focus on features related to
debugging, diagnostics, and reliability.  A primary goal is to provide
a solid environment for running and controlling concurrent tasks.

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

It is a young project.  Contributions welcome.








 
