Developing with Curio
=====================

(This is a work in progress)

So, you want to write a larger application or library that depends on
Curio? This document describes the overall philosophy behind Curio,
how it works under the covers, and how you might approach software
development using it.

Please, Don't Use Curio!
------------------------

Let's be frank for a moment--you really don't want to use Curio.  All
things equal, you should probably be programming with threads.  Yes,
threads. THOSE threads. Seriously. I'm not kidding.

"But what about the GIL?" you ask.  Yes, yes, that can sometimes be an
issue.

"Or what about the fact that no one is smart enough to program with
threads?"  Okay, yes, a lot of computer science students have exploded
their head trying to solve something like the "Sleeping Barber"
problem on their Operating Systems final exam.  Yes, it can get tricky 
sometimes.

"And what about making everything web-scale?"  Yes, threads might
not let you run the next Facebook on a single server instance.  Point taken.

All of these are perfectly valid concerns.  However, the truth of the
matter is that threads still actually work pretty well for a lot of
problems--most problems really.  For one, it is extremely unlikely
that you're building the next Facebook. If all you need to do is serve
a few hundred clients at once, threads will work fine for that.
Second, there are well-known ways to make thread programming sane.
For example, using functions, avoiding shared state and side effects,
and coordinating threads with queues.  As for the dreaded GIL, that is
mainly a concern for CPU-intensive processing.  Although it's an
annoyance, there are known ways to work around it using process pools,
distributed computation, or C extensions.  Finally, threads have the
benefit of working with almost any existing Python code. All of the
popular packages (e.g., requests, SQLAlchemy, Django, Flask, etc.)
work fine with threads.  I use threads in production.  There, I've
said it.

Now, suppose that you've ignored this advice or that you really do
need to write an application that can handle 10000 concurrent client
connections.  In that case, a coroutine-based library like Curio might
be able to help you.  Before beginning though, be aware that
coroutines are part of a strange new world.  They execute differently
than normal Python code and don't play well with existing libraries.
Nor do they solve the problem of the GIL or give you increased
parallelism.  In addition to seeing new kinds of bugs, coroutines
will likely make you swat your arms in the air as you fight swarms of stinging bats
and swooping manta rays.  Your coworkers will keep their distance more
than usual.  Coroutines are weird, finicky, fun, and amazing
(sometimes all at once).  Only you can decide if this is what you
really want.

Curio makes it all just a bit more interesting by killing off every
beloved character of asynchronous programming in the
first act.  The event loop? Dead. Futures? Dead. Protocols?
Dead. Transports?  You guessed it, dead. And the scrappy hero, Callback
"Buck" Function? Yep, dead. Big time dead--as in not just "pining for
the fjords" dead.  Tried to apply a monkeypatch. It failed.  Now, when
Curio goes to the playlot and asks "who wants to interoperate?", the
other kids are quickly shuttled away by their fretful parents.

And a hollow voice says "plugh."

Say, have you considered using threads?  Or almost anything else?

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

By the way, ``run()`` is basically the only function Curio provides to
the outside world of non-coroutines. Remember that. It's "run". Three letters.

Coroutines Calling Coroutines
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Coroutines can call other coroutines as long as you preface the call
with the ``await`` keyword.  For example::

    async def main():
         names = ['Dave', 'Paula', 'Thomas', 'Lewis']
         for name in names:
             print(await greeting(name))

    from curio import run
    run(main())

For the most part, you can write async functions, methods, and do everything that you
would do with normal Python functions.  The use of the ``await`` in calls is important
though--if you don't do that, the called coroutine won't run and you'll be fighting
the aforementioned swarm of stinging bats trying to figure out what's wrong.

Blocking Calls (i.e., "System Calls")
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a program runs, it executes statements one after the other until
the services of the operating system are needed (e.g., sleeping, reading a file, 
receiving a network packet, etc.).  For example::

     import time
     time.sleep(10)

Under the covers, this operation ultimately involves making a "system call."
System calls are different than normal functions in that they involve
making a request to the operating system kernel by executing a "trap."
A trap is like a software-generated interrupt.  When it occurs, the
running process is suspended and the operating system takes over to
handle the request. Control doesn't return until the operating system
completes the request and reschedules the process.

Now, what does all of this have to do with coroutines?  Let's define
a very special kind of coroutine::

   from types import coroutine

   @coroutine
   def sleep(seconds):
       yield ('sleep', seconds)

This coroutine is different than the rest--it doesn't use the
``async`` syntax and it makes direct use of the ``yield`` statement
(which is not normally allowed in ``async`` functions).  The ``@coroutine``
decorator is there so that it can be called with ``await``.
Now, let's write a coroutine that uses this::

   async def main():
       print('Yawn. Getting sleepy.')
       await sleep(10)
       print('Awake at last!')

Let's manually drive it using the same technique as before::
 
    >>> c = main()
    >>> request = c.send(None)
    Yawn! Getting sleepy.
    >>> request
    ('sleep', 10)
    >>> 

The output from the first ``print()`` function appears, but the
coroutine is now suspended. The return value of the
``send()`` call is the tuple produced by the ``yield`` statement in
the ``sleep()`` coroutine.  This is exactly the same concept as a
trap.  The coroutine has suspended itself and made a request (in this
case, a request to sleep for 10 seconds).  It is now up to the driver
of the code to satisfy that request.  As far as the coroutine is
concerned, the details of how this is done don't matter.  It's just
assumed that the coroutine will be resumed after 10 seconds have
elapsed.  To do that, you call ``send()`` again on the coroutine (with a
return result if any).   For example::

    >>> c.send(None)
    Awake at last!
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration
    >>> 

All of this might seem very low-level, but this is precisely what
Curio is doing. Coroutines execute statements under the
supervision of a small kernel.  When a coroutine executes a system
call (e.g., a special coroutine that makes use of ``yield``), 
the kernel receives that request and acts upon it.  The coroutine
resumes once the request has completed.

Keep in mind that all of this machinery is hidden from view.  Your
application doesn't actually see the Curio kernel or use code that
directly involves the ``yield`` statement. Those are low-level
implementation details--like machine code.  Your code will simply make
a high-level call such as ``await sleep(10)`` and it will just work.

Coroutines and Multitasking
^^^^^^^^^^^^^^^^^^^^^^^^^^^

As noted, systems calls almost always involve waiting or blocking.  For
example, waiting for time to elapse, waiting to receive a network
packet, etc.  While waiting, it might be possible to switch to another
coroutine that's able to run--this is multitasking.  If there are
multiple coroutines, the kernel can cycle between them by running each
one until it executes a system call, then switching to the next ready
coroutine at that point.  Your operating system does exactly the same
thing when processes execute actual system calls.  The ability to 
switch between coroutines is why they are useful for concurrent
programming.

Coroutines versus Threads
^^^^^^^^^^^^^^^^^^^^^^^^^

Code written using coroutines looks very similar to code written using
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

Both versions of code involve the same statements and have the same overall
control flow.  The key difference is that threads support
preemption whereas coroutines do not. This means that in the threaded
code, the operating system can switch threads on any statement. With
coroutines, task switching can only occur on statements that involve
``await``.

Both approaches have advantages and disadvantages.  One potential
advantage of the coroutine approach is that you explicitly know where
task switching might occur. Thus, if you're writing code that involves
tricky task synchronization or coordination, it might be easier to
reason about about its behavior.  One disadvantage of coroutines is
that any kind of long-running calculation or blocking operation can't
be preempted.  So, a coroutine might hog the CPU for an extended
period and force other coroutines to wait.  Another downside is that
code must be written to explicitly take advantage of coroutines (e.g.,
explicit use of ``async`` and ``await``).  Threads, on the other hand,
can work with any existing Python code.

Coroutines versus Callbacks
^^^^^^^^^^^^^^^^^^^^^^^^^^^

For I/O handling, libraries and frameworks will sometimes make use of
callback functions.  For example, here is an echo server written in
the callback style using Python's ``asyncio`` module::

    import asyncio

    class EchoProtocol(asyncio.Protocol):
        def connection_made(self, transport):
            print('Got connection')
            self.transport = transport

        def connection_lost(self, exc):
            print('Connection closed')
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

Programming with callbacks is a well-known technique for asynchronous
I/O handling that is used in programming languages without proper
support for coroutines.  It can be efficient, but it also tends to
result in code that's described as a kind of "callback hell"--a large
number of tiny functions with no easily discerned strand of control
flow tying them together.

Coroutines restore a lot of sanity to the overall programming model.
The control-flow is much easier to follow and the number of
required functions tends to be significantly less.  In fact, the main
motivation for adding ``async`` and ``await`` to Python and other languages is
to simplify asynchronous I/O by avoiding callback hell.

Historical Perspective
^^^^^^^^^^^^^^^^^^^^^^

Coroutines were first invented in the earliest days of computing to
solve problems related to multitasking and concurrency.  Given the
simplicity and benefits of the programming model, one might wonder why
they haven't been used more often.

A big part of this is really due to the lack of proper support in
mainstream programming languages used to write production software.
For example, languages such as Pascal, C/C++, and Java don't support
coroutines. Thus, it's not a technique that most programmers would even think to 
consider.  Even in Python, proper support for coroutines has taken a
long time to emerge.  Over the years, various projects have explored
coroutines in various forms, usually involving sneaky hacks surrounding
generator functions and C extensions.  The addition of the ``yield from``
construct in Python 3.3 greatly simplified the problem of writing
coroutine libraries.  The emergence of ``async/await`` in Python 3.5
takes a huge stride in making coroutines more of a first-class object
in the Python world.   This is really the starting point for Curio.

Layered Architecture
--------------------

One of the most important design principles of systems programming is
layering. Layering is an essential part of understanding how Curio works
so let's briefly discuss this idea.

Operating System Design and Programming Libraries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Think about how I/O works in the operating system for a moment. At the
lowest level, you'll find device drivers and
other hardware-specific code.  However, the bulk of the operating
system is not written to operate at this low-level. Instead, those
details are hidden behind a device-independent abstraction layer that
manages file descriptors, I/O buffering, flow control, and other
details. 

.. image:: _static/layers.png

The same layering principal applies to user applications.  The operating
system provides a set of low-level system calls (traps).  These calls
vary between operating systems, but you don't really care as a
programmer.  That's because the implementation details are hidden
behind a layer of standardized programming libraries such as the C
standard library, various POSIX standards, Microsoft Windows APIs,
etc.  Working in Python removes you even further from
platform-specific library details. For example, a network program
written using Python's ``socket`` module will work virtually
everywhere.  This is layering and abstraction in action.

The Curio Scheduler
^^^^^^^^^^^^^^^^^^^

Curio primarily operates as a coroutine scheduling layer that sits
between an application and the Python standard library.  This layer
doesn't actually carry out any useful functionality---it is only
concerned with task scheduling.  Just to emphasize, the scheduler
doesn't perform any kind of I/O.  There are no internal protocols,
streams, buffering, or anything you'd commonly associate with the
implementation of an I/O library.

.. image:: _static/curiolayer.png

To make the scheduling process work, Curio relies on non-blocking I/O.
With non-blocking I/O, any system call that would ordinarily cause the
calling process to block fails with an exception.   You can try it
out manually::

    >>> from socket import *
    >>> s = socket(AF_INET, SOCK_STREAM)
    >>> s.bind(('',25000))
    >>> s.listen(1)
    >>> s.setblocking(False)
    >>> c, a = s.accept()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "/usr/local/lib/python3.5/socket.py", line 195, in accept
        fd, addr = self._accept()
    BlockingIOError: [Errno 35] Resource temporarily unavailable
    >>> 

To handle the exception, the calling process has to wait for an incoming connection.
Curio provides a special system call for this called ``_read_wait()``.   Here's a
coroutine that uses it::

    >>> from curio import run
    >>> from curio.traps import _read_wait
    >>> async def accept_connection(s):
    ...      while True:
    ...          try:
    ...              return s.accept()
    ...          except BlockingIOError:
    ...              await _read_wait(s)
    ...
    >>> c, a = run(accept_connection(s))

With that code running, try making a connection using ``telnet``, ``nc`` or similar command.
You should see the ``run()`` function return the result after the connection is made.

Now, a couple of important details about what's happening:

* The actual I/O operation is performed using the normal ``accept()`` method of
  a socket.  It is the same method that's used in synchronous code not involving coroutines.

* Curio only enters the picture if the attempted I/O operation raises a
  ``BlockingIOError`` exception.  In that case, the coroutine must wait for I/O
  and retry the I/O operation later (the retry is why it's enclosed in a ``while`` loop).

* Curio does not actually perform any I/O. It is only responsible for waiting.
  The ``_read_wait()`` call sleeps until the associated socket can be read.

* Incoming I/O is not handled as an "event" nor are there any
  associated callback functions.  If an incoming connection is received, the coroutine
  wakes up.  That's it.  There is no "event loop."

With the newly established connection, write a coroutine that receives some data::

    >>> async def read_data(s, maxsize):
    ...     while True:
    ...         try:
    ...              return s.recv(maxsize)
    ...         except BlockingIOError:
    ...              await _read_wait(s)
    ... 
    >>> data = run(read_data(c, 1024))

Try typing some input into your connection.  You should see that data
returned.  Notice that the code is basically the same as before.  An
I/O operation is attempted using the normal socket ``recv()``
method. If it fails, then the coroutine waits using the
``_read_wait()`` call.  Just to be clear.  There is no event loop and
Curio is not performing any I/O. Curio is only responsible for
waiting--that is basically the core of it.

On the subject of waiting, here is a list of the things that
Curio knows how to wait for:

* Expiration of a timer (e.g., sleeping).
* I/O operations (read, write).
* Completion of a ``Future`` from the ``concurrent.futures`` standard library.
* Arrival of a Unix signal.
* Removal of a coroutine from a wait queue.
* Termination of a coroutine.

Everything else is built up from those low-level primitives.

The Proxy Layer
^^^^^^^^^^^^^^^

If you wanted to, you could program directly with low-level calls like
``_read_wait()`` as shown in the previous part.  However, no one
really wants to do that.  Instead, it's easier to create a collection
of proxy objects that hide the details.  For example, you could make a
coroutine-based socket proxy class like this::

    from curio.traps import _read_wait

    class Socket(object):
        def __init__(self, sock):
            self._sock = sock
            self._sock.setblocking(False)

        async def accept(self):
            while True:
                try:
                    client, addr = self._sock.accept()
                    return Socket(client), addr
                except BlockingIOError:
                    await _read_wait(self._sock)

        async def recv(self, maxsize):
            while True:
                try:
                    return self._sock.recv(maxsize)
                except BlockingIOError:
                    await _read_wait(self._sock)

        # Other socket methods follow
        ...

        # Delegate other socket methods
        def __getattr__(self, name):
            return getattr(self._sock, name)

This class invokes the standard socket methods, but has a small amount
of extra code to deal with coroutine scheduling.  Using this, your
code starts to look much more normal. For example::

     async def echo_server(address):
          sock = Socket(socket(AF_INET, SOCK_STREAM))
          sock.bind(address)
          sock.listen(1)
          while True:
               client, addr = await sock.accept()
               print('Connection from', addr)
               await spawn(echo_client(client))
 
     async def echo_client(sock):
          while True:
               data = await sock.recv(100000)
               if not data:
                   break
               await sock.sendall(data)

This is exactly what's happening in something like the
``curio.socket`` module.  It provides a coroutine wrapper around a
normal socket and let's you write normal-looking socket code.

It's important to emphasize that a proxy doesn't change how you
interact with an object.  You use the same method names as you did
before coroutines and you should assume that they have the same
underlying behavior. Curio is really only concerned with the
scheduling problem--not I/O.

The Curio Task Model
--------------------

When a coroutine runs inside Curio, it becomes a "Task."  This 
section describes the overall task model and operations on tasks.

Creating Tasks
^^^^^^^^^^^^^^

An application that uses Curio is always launched by providing an initial
coroutine to the ``run()`` function.  For example::

    import curio

    async def main():
        print('Starting')
        ...

    curio.run(main())

That first coroutine becomes the initial task.  If you want to create
more tasks that execute concurrently, use the ``spawn()`` coroutine.
For example::

    import curio
    
    async def child(n):
        print('Sleeping')
        await curio.sleep(n)
        print('Awake again!')

    async def main():
        print('Starting')
        await curio.spawn(child(5))

    curio.run(main())

If you want to wait for a task to finish, save the result of ``spawn()`` and use its
``join()`` method.  For example::

    async def main():
        print('Starting')
        task = await curio.spawn(child(5))
        await task.join()
        print('Quitting')

If you've programmed with threads, the programming model is similar.  One important
point though---you only use ``spawn()`` if you want concurrent task execution.
If a coroutine merely wants to call another coroutine in a synchronous manner like a
library function, just use ``await``.  For example::

    async def main():
        print('Starting')
        await child(5)      
        print('Quitting')

Task Cancellation
^^^^^^^^^^^^^^^^^

Curio allows any task to be cancelled.  Here's an example::

    import curio
    
    async def child(n):
        print('Sleeping')
        await curio.sleep(n)
        print('Awake again!')

    async def main():
        print('Starting')
        task = await curio.spawn(child(5))
        await time.sleep(1)
        await task.cancel()     # Cancel the child

    curio.run(main())

Cancellation only occurs on blocking operations (e.g., the ``curio.sleep()`` call in the child).
When a task is cancelled, the current operation fails with a ``CancelledError`` exception. This
exception can be caught::

    async def child(n):
        print('Sleeping')
        try:
            await curio.sleep(n)
            print('Awake again!')
        except curio.CancelledError:
            print('Rudely cancelled')

A cancellation should not be ignored.  In fact, the ``task.cancel()`` method blocks until the
task actually terminates.  If ignored, the cancelling task would simply hang forever waiting.
That's probably not what you want.

Returning Results
^^^^^^^^^^^^^^^^^

The ``task.join()`` returns the final result of a coroutine.  For example::

    async def add(x, y):
        return x + y

    async def main():
        task = await curio.spawn(add(2,3))
        result = await task.join()
        print('Result ->', result)    # Prints 5

If an exception occurs in the task, it is wrapped in a ``TaskError``
exception.  This is a chained exception where the ``__cause__``
attribute contains the actual exception that occurred.  For example::

    async def main():
        task = await curio.spawn(add(2, 'Hello'))   # Fails due to TypeError
        try:
            result = await task.join()
        except curio.TaskError as err:
            # Reports the resulting TypeError
            print('It failed. Cause:', repr(err.__cause__))

The use of ``TaskError`` serves an important, but subtle, purpose
here.  Due to cancellation and timeouts, the ``task.join()`` operation
might raise an exception that's unrelated to the underlying task
itself.  This means that you need to have some way to separate
exceptions related to the ``join()`` operation versus an
exception that was raised inside the task.  The ``TaskError`` solves
this issue--if you get that exception, it means that the task being joined exited 
with an exception.  If you get other exceptions, they
are related to some aspect of the ``join()`` operation (i.e.,
cancellation), not the underlying task.

Timeouts
^^^^^^^^

Getting a Task Self-Reference
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^













