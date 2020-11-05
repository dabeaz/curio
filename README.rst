Curio
=====

Curio is a coroutine-based library for concurrent Python systems
programming.  It provides standard programming abstractions such as as
tasks, sockets, files, locks, and queues. It works on Unix and Windows. 
You'll find it to be familiar, small, fast, and fun

A Simple Example
-----------------

Here is a concurrent TCP echo server directly implemented using sockets:

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

If you've done network programming with threads, it looks almost
identical. Moreover, it can handle thousands of clients even though no
threads are being used inside.

Core Features
-------------

Curio supports standard synchronization primitives (events, locks,
recursive locks, semaphores, and condition variables), queues,
subprocesses, as well as running tasks in threads and processes.  The
task model fully supports cancellation, task groups, timeouts,
monitoring, and other features critical to writing reliable code.

Read the `official documentation <https://curio.readthedocs.io>`_ for
more in-depth coverage.  The `tutorial
<https://curio.readthedocs.io/en/latest/tutorial.html>`_ is a good
starting point.  The `howto
<https://curio.readthedocs.io/en/latest/howto.html>`_ describes how to
carry out common programming tasks.

Talks Related to Curio
----------------------

Concepts related to Curio's design and general issues related to async
programming have been described by Curio's creator in various
conference talks and tutorials:

* `Build Your Own Async <https://www.youtube.com/watch?v=Y4Gt3Xjd7G8>`_, Workshop talk by David Beazley at PyCon India, 2019.

* `The Other Async (Threads + Asyncio = Love) <https://www.youtube.com/watch?v=x1ndXuw7S0s>`_, Keynote talk by David Beazley at PyGotham, 2017.

* `Fear and Awaiting in Async <https://www.youtube.com/watch?v=E-1Y4kSsAFc>`_, Keynote talk by David Beazley at PyOhio 2016.

* `Topics of Interest (Async) <https://www.youtube.com/watch?v=ZzfHjytDceU>`_, Keynote talk by David Beazley at Python Brasil 2015.

* `Python Concurrency from the Ground Up (LIVE) <https://www.youtube.com/watch?v=MCs5OvhV9S4>`_, talk by David Beazley at PyCon 2015.

Questions and Answers
---------------------

**Q: What is the point of the Curio project?**

A: Curio is async programming, reimagined as something smaller, faster, and easier 
to reason about. It is meant to be both educational and practical.

**Q: Is Curio implemented using asyncio?**

A: No. Curio is a standalone library directly created from low-level I/O primitives.

**Q: Is Curio meant to be a clone of asyncio?**

A: No. Although Curio provides a significant amount of overlapping
functionality, the API is different.  Compatibility with other
libaries is not a goal.
 
**Q: Can Curio interoperate with other event loops?**

A: It depends on what you mean by the word "interoperate."  Curio's
preferred mechanism of communication with the external world is a
queue.  It is possible to communicate between Curio, threads, and
other event loops using queues.  

**Q: How fast is Curio?**

A: Curio's primary goal is to be an async library that is minimal and
understandable. Performance is not the primary concern.  That said, in
rough benchmarking of a simple echo server, Curio is more than twice
as fast as comparable code using coroutines in ``asyncio`` or
``trio``.  This was last measured on OS-X using Python 3.9.  Keep in
mind there is a lot more to overall application performance than the
performance of a simple echo server so your mileage might
vary. However, as a runtime environment, Curio doesn't introduce a lot of
extra overhead. See the ``examples/benchmark`` directory for various
testing programs.

**Q: What is the future of Curio?**

A: Curio should be viewed as a library of primitives related to
concurrent systems programming.  At this time, it is considered
to be feature-complete--meaning that it is not expected to
sprout many new capabilities.  It may be updated from time to time to
fix bugs or support new versions of Python.

**Q: Can I contribute?**

A: Curio is not a community-based project seeking developers
or maintainers.  However, having it work reliably is important. If you've
found a bug or have an idea for making it better, please feel
file an `issue <https://github.com/dabeaz/curio>`_. 

Contributors
------------

The following people contributed ideas to early stages of the Curio project:
Brett Cannon, Nathaniel Smith, Alexander Zhukov, Laura Dickinson, and Sandeep Gupta.

Who
---
Curio is the creation of David Beazley (@dabeaz) who is also
responsible for its maintenance.  http://www.dabeaz.com

P.S.
----
If you want to learn more about concurrent programming more generally, you should
come take a `course <https://www.dabeaz.com/courses.html>`_!

.. |--| unicode:: U+2013   .. en dash
.. |---| unicode:: U+2014  .. em dash, trimming surrounding whitespace
   :trim:



