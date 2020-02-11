Curio
=====

Curio is a coroutine-based library for concurrent Python systems
programming.  It provides standard programming abstractions such as as
tasks, sockets, files, locks, and queues. You'll find it to be
familiar, small, fast, and fun

A Simple Example
-----------------

Here is a concurrent TCP echo server implemented using sockets and
Curio:

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

If you have programmed with threads, you'll find that Curio looks similar.
You'll also find that the above server can handle thousands of simultaneous 
client connections even though no threads are being used under the hood.

Thread Interoperability Example
-------------------------------

A notable aspect of Curio are features that allow it to interoperate
with existing code.  For example, suppose you have a standard function
that reads off a thread-queue like this:

.. code:: python

    def consumer(queue):
        while True:
            item = queue.get()
            if item is None:
                break
            print('Got:', item)

If you want to send this function data from an asynchronous task, you can use
Curio's ``UniversalQueue`` like this:

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

Curio supports standard synchronization primitives (events, locks,
recursive locks, semaphores, and condition variables), queues,
signals, subprocesses, as well as running tasks in threads and
processes. The task model fully supports cancellation, task groups,
timeouts, monitoring, and other features critical to writing reliable
code.

The two examples shown are only a small sample of what's possible.
Read the `official documentation <https://curio.readthedocs.io>`_ for
more in-depth coverage.  The `tutorial
<https://curio.readthedocs.io/en/latest/tutorial.html>`_ is a good
starting point.  The `howto
<https://curio.readthedocs.io/en/latest/howto.html>`_ describes how to
carry out common programming tasks.

Talks Related to Curio
----------------------

Most of the principles behind Curio's design and general issues
related to async programming have been described in various conference
talks and tutorials:

* `Build Your Own Async <https://www.youtube.com/watch?v=Y4Gt3Xjd7G8>`_, Workshop talk by David Beazley at PyCon India, 2019.

* `The Other Async (Threads + Asyncio = Love) <https://www.youtube.com/watch?v=x1ndXuw7S0s>`_, Keynote talk by David Beazley at PyGotham, 2017.

* `Fear and Awaiting in Async <https://www.youtube.com/watch?v=E-1Y4kSsAFc>`_, Keynote talk by David Beazley at PyOhio 2016.

* `Topics of Interest (Async) <https://www.youtube.com/watch?v=ZzfHjytDceU>`_, Keynote talk by David Beazley at Python Brasil 2015.

* `Python Concurrency from the Ground Up (LIVE) <https://www.youtube.com/watch?v=MCs5OvhV9S4>`_, talk by David Beazley at PyCon 2015.

Questions and Answers
---------------------

**Q: Is Curio implemented using asyncio?**

A: No. Curio is a standalone library. Although the core of the library
uses the same basic machinery as ``asyncio`` to poll for I/O events,
the internals of the library are completely different and far less complex.

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

A: In rough benchmarking of the simple echo server shown here, Curio
runs about 90% faster than comparable code using coroutines in
``asyncio``. This was last measured on Linux using Python 3.7b3. Keep
in mind there is a lot more to overall application performance than
the performance of a simple echo server so your mileage might
vary. See the ``examples/benchmark`` directory for various testing
programs.

**Q: Is Curio going to evolve into a framework?**

A: No. It's best to think of Curio as a low-level library of 
primitives related to concurrent systems programming.  You could
certainly use it to build a framework. 

**Q: Can I contribute?**

A: Curio is not a community-based project that is seeking developers
or maintainers.  However, having it work reliably is important. So, if
you've found a bug or have an idea for making it better, please feel
file an `issue <https://github.com/dabeaz/curio>`_.  Issues
are always appreciated. 

Testing
-------

Curio provides an extensive set of unit tests that can be executed using
pytest. Before using Curio on your project, you should run the tests
on your machine.  Type ``python -m pytest`` in the top-level ``curio/`` directory
to run the tests.

Documentation
-------------

Read the official docs here: https://curio.readthedocs.io

Contributors
------------

The following people contributed ideas to early stages of the Curio project:
Brett Cannon, Nathaniel Smith, Alexander Zhukov, Laura Dickinson, and Sandeep Gupta.

About
-----
Curio is the creation of David Beazley (@dabeaz) who is also
responsible for its maintenance.  http://www.dabeaz.com

P.S.
----
If you want to learn more about concurrent programming, you should
come take a `course <https://www.dabeaz.com/courses.html>`_!

.. |--| unicode:: U+2013   .. en dash
.. |---| unicode:: U+2014  .. em dash, trimming surrounding whitespace
   :trim:



