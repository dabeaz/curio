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
message passing, or C extensions.  Finally, threads have the
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
beloved character of asynchronous programming in the first act.  The
event loop? Dead. Futures? Dead. Protocols?  Dead. Transports?  You
guessed it, dead. And the scrappy hero, Callback "Buck" Function? Yep,
dead. Big time dead--as in not just "pining for the fjords" dead.
Tried to apply a monkeypatch. It failed.  Now, when Curio goes to the
playlot and asks "who wants to interoperate?", the other kids are
quickly shuttled away by their fretful parents.

And a hollow voice says "plugh."

Say, have you considered using threads?  Or almost anything else?

Coroutines
----------

First things, first.  Curio is solely focused on solving one specific
problem--and that's the concurrent execution and scheduling of
coroutines.  This section covers some coroutine basics and takes
you into the heart of why they're used for concurrency.

Defining a Coroutine
^^^^^^^^^^^^^^^^^^^^

A coroutine is a function defined using ``async def`` such as this::

    >>> async def greeting(name):
    ...     return 'Hello ' + name

Unlike a normal function, a coroutine never executes independently.
It has to be driven by some other code.  It's low-level, but you can
drive a coroutine manually if you want::

    >>> g = greeting('Dave')
    >>> g
    <coroutine object greeting at 0x10978ee60>
    >>> g.send(None)
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration: Hello Dave
    >>> 

Normally, you wouldn't do this though. Curio provides a high-level
function that runs a coroutine and returns its final result::

    >>> from curio import run
    >>> run(greeting, 'Dave')
    'Hello Dave'
    >>>

By the way, ``run()`` is basically the only function Curio provides to
the outside world of non-coroutines. Remember that. It's "run". Three
letters.

Coroutines Calling Coroutines
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Coroutines can call other coroutines as long as you preface the call
with the ``await`` keyword.  For example::

    >>> async def main():
    ...      names = ['Dave', 'Paula', 'Thomas', 'Lewis']
    ...      for name in names:
    ...          print(await greeting(name))
    >>> from curio import run
    >>> run(main)
    Hello Dave
    Hello Paula
    Hello Thomas
    Hello Lewis

For the most part, you can write async functions, methods, and do
everything that you would do with normal Python functions.  The use of
the ``await`` in calls is important though--if you don't do that, the
called coroutine won't run and you'll be fighting the aforementioned
swarm of stinging bats trying to figure out what's wrong.

The Coroutine Menagerie
^^^^^^^^^^^^^^^^^^^^^^^

For the most part, coroutines are centered on ``async`` function
definitions.  However, there are a few additional language features
that are "async aware."  For example, you can define an asynchronous
context manager::

    from curio import run

    class AsyncManager(object):
        async def __aenter__(self):
            print('Entering')

        async def __aexit__(self, ty, val, tb):
            print('Exiting')

    async def main():
        m = AsyncManager()
        async with m:
            print('Hey there!')

    >>> run(main)
    Entering
    Hey there!
    Exiting
    >>>

You can also define an asynchronous iterator::

    from curio import run

    class AsyncCountdown(object):
        def __init__(self, start):
            self.start = start

        async def __aiter__(self):
            return AsyncCountdownIter(self.start)

    class AsyncCountdownIter(object):
        def __init__(self, n):
            self.n = n

        async def __anext__(self):
            self.n -= 1
            if self.n <= 0:
                raise StopAsyncIteration
            return self.n

    async def main():
        async for n in AsyncCountdown(5):
            print('T-minus', n)

    >>> run(main)
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    >>> 

Last, but not least, you can define an asynchronous generator as an
alternative implementation of an asynchronous iterator::

    from curio import run

    async def countdown(n):
        while n > 0:
            yield n
            n -= 1

    async def main():
        async for n in countdown(5):
            print('T-minus', n)

    run(main)

An asynchronous generator feeds values to an async-for loop.  
In all of these cases, the essential feature enhancement is that
you can call other async-functions in the implementation.  That is,
since certain method such as ``__aenter__()``, ``__aiter__()``, and
``__anext__()`` are all async, they can use the ``await`` statement
to call other coroutines as normal functions.

Try not to worry too much about the low-level details of all of this.
Stay focused on the high-level--the world of "async" programming is
mainly going to involve combinations of async functions, async context
managers, and async iterators.  They are all meant to work together.
These are also core features of the Python language itself--they are
not part of a specific library module or runtime environment.

Blocking Calls (i.e., "System Calls")
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a program runs, it executes statements one after the other until
the services of the operating system are needed (e.g., sleeping,
reading a file, receiving a network packet, etc.).  For example, 
consider this function::

     import time

     def sleepy(seconds):
         print('Yawn. Getting sleepy.')
         time.sleep(seconds)
         print('Awake at last!')

If you call this function, you'll see a message and the program will
go to sleep for awhile.  While it's sleeping, nothing is happening
at all.  If you look at the CPU usage, it will show 0%. 
Under the covers, the program has made a "system call" to the 
operating system which has suspended the program.  At some point
the timer will expire and the operating system will reschedule the
program to run again.   Just to emphasize, the ``time.sleep()``
call suspends the Python interpreter entirely.  At some point, Python
will resume, but that's outside of its control.

The mechanism for making a system call is different than that of a
normal function in that it involves executing a special machine
instruction known as a "trap."  A trap is basically a
software-generated interrupt.  When it occurs, the running process is
suspended and control is passed to the operating system kernel so that
it can handle the request.  There are all sorts of other magical
things that happen on trap-handling, but you're really not supposed to
worry about it as a programmer.

Now, what does all of this have to do with coroutines?  Let's define
a very special kind of coroutine::

   from types import coroutine
   @coroutine
   def sleep(seconds):
       yield ('sleep', seconds)

This coroutine is different than the rest--it doesn't use the
``async`` syntax and it makes direct use of the ``yield`` statement.
The ``@coroutine`` decorator is there so that it can be called with
``await``.  Now, let's write a coroutine that uses this::

   async def sleepy(seconds):
       print('Yawn. Getting sleepy.')
       await sleep(seconds)
       print('Awake at last!')

Let's manually drive it using the same technique as before::
 
    >>> c = sleepy(10)
    >>> request = c.send(None)
    Yawn. Getting sleepy.
    >>> request
    ('sleep', 10)

The output from the first ``print()`` function appears, but the
coroutine is now suspended. The return value of the ``send()`` call is
the tuple produced by the ``yield`` statement in the ``sleep()``
coroutine.  Now, step back and think about what has happened here.
Focus carefully. Focus on a special place.  Focus on the
breath. Breathe in.... Breathe out...... Focus.

Basically the code has executed a trap!  The ``yield`` statement
caused the coroutine to suspend.  The returned tuple is
a request (in this case, a request to sleep for 10 seconds). It
is now up the driver of the code to satisfy that request.  But
who's driving this show?  Wait, that's YOU!
So, start counting... "T-minus 10, T-minus 9, 
T-minus 8, ... T-minus 1."   Time's up!  Put the coroutine
back to work::

    >>> c.send(None)
    Awake at last!
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
    StopIteration

Congratulations!  You just passed your first test on the way to
getting a job as an operating system.

Here's some minimal code that executes what you just did::

    import time
    def run(coro):
        while True:
             try:
                 request, *args = coro.send(None)
                 if request == 'sleep':
                     time.sleep(*args)
                 else:
                     print('Unknown request:', request)
             except StopIteration as e:
                 return e.value

All of this might seem very low-level, but this is precisely what
Curio is doing. Coroutines execute statements under the supervision of
a small kernel.  When a coroutine executes a system call (e.g., a
special coroutine that makes use of ``yield``), the kernel receives
that request and acts upon it.  The coroutine resumes once the request
has completed.  

Keep in mind that all of this machinery is hidden from view.  The
coroutine doesn't actually know anything about the ``run()`` function
or use code that directly involves the ``yield`` statement. Those are
low-level implementation details--like machine code.  The coroutine
simply makes a high-level call such as ``await sleep(10)`` and it will
just work.  Somehow.

Coroutines and Multitasking
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's continue to focus on the fact that a defining feature of
coroutines is that they can suspend their execution.  When a coroutine
suspends, there's no reason why the ``run()`` function needs to wait
around doing nothing.  In fact, it could switch to a different coroutine
and run it instead.   This is a form of multitasking.  Let's write
a slightly different variant of the ``run()`` function::

    from collections import deque
    from types import coroutine

    @coroutine
    def switch():
        yield ('switch',)
 
    tasks = deque()

    def run():
        while tasks:
            coro = tasks.popleft()
            try:
                request, *args = coro.send(None)
                if request == 'switch':
                    tasks.append(coro)
                else:
                    print('Unknown request:', request)
            except StopIteration as e:
                print('Task done:', coro)

In this code, the ``run()`` function implements a simple round-robin
scheduler and a single request for switching tasks as provided by
the ``switch()`` coroutine.  Here are some sample coroutine
functions to run::

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await switch()
            n -= 1

    async def countup(stop):
        n = 1
        while n <= stop:
            print('Up we go', n)
            await switch()
            n += 1

    tasks.append(countdown(10))
    tasks.append(countup(15))
    run()

When you run this code, you'll see the ``countdown()`` and ``countup()`` coroutines
rapidly alternating like this::

    T-minus 10
    Up we go 1
    T-minus 9
    Up we go 2
    T-minus 8
    Up we go 3
    ...
    T-minus 1
    Up we go 10
    Task done: <coroutine object countdown at 0x102a3ee08>
    Up we go 11
    Up we go 12
    Up we go 13
    Up we go 14
    Up we go 15
    Task done: <coroutine object countup at 0x102a3ef10>

Excellent. We're running more than one coroutine concurrently. The
only catch is that the ``switch()`` function isn't so interesting.  To
make this more useful, you'd need to expand the ``run()`` loop to
understand more operations such as requests to sleep and for I/O.
Let's add sleeping::

    import time
    from collections import deque
    from types import coroutine
    from bisect import insort

    @coroutine
    def switch():
        yield ('switch',)

    @coroutine
    def sleep(seconds):
        yield ('sleep', seconds)

    tasks = deque()
    sleeping = [ ]

    def run():
        while tasks:
            coro = tasks.popleft()
            try:
                request, *args = coro.send(None)
                if request == 'switch':
                    tasks.append(coro)
                elif request == 'sleep':
                    seconds = args[0]
                    deadline = time.time() + seconds
                    insort(sleeping, (deadline, coro))
                else:
                    print('Unknown request:', request)
            except StopIteration as e:
                print('Task done:', coro)

            while not tasks and sleeping:
                now = time.time()
                duration = sleeping[0][0] - now
                if duration > 0:
                    time.sleep(duration)
                _, coro = sleeping.pop(0)
                tasks.append(coro)

Things are starting to get a bit more serious now.  For sleeping, the
coroutine is set aside in a holding list that's sorted by sleep
expiration time (aside: the ``bisect.insort()`` function is a useful way
to construct a sorted list).  The bottom part of the ``run()``
function now sleeps if there's nothing else to do. On the conclusion
of sleeping, the task is put back on the task queue.

Here are some modified tasks that sleep::

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await sleep(2)
            n -= 1

    async def countup(stop):
        n = 1
        while n <= stop:
            print('Up we go', n)
            await sleep(1)
            n += 1

    tasks.append(countdown(10))
    tasks.append(countup(15))
    run()

If you run this program, you should see output like this::

    T-minus 10
    Up we go 1
    Up we go 2
    T-minus 9
    Up we go 3
    Up we go 4
    T-minus 8
    Up we go 5
    Up we go 6
    ...

You're now well on your way to writing your own little operating
system--and Curio.  This is essentially the whole idea.  Curio is
basically a small coroutine scheduler.  In addition to sleeping, it
allows coroutines to switch on other kinds of blocking operations
involving I/O, waiting on synchronization primitives, Unix signals,
and so forth.  Your operating system does exactly the same thing when
processes execute actual system calls.  The ability to switch between
coroutines is why they are useful for concurrent programming.  This
is really the big idea in a nutshell.

Coroutines versus Threads
^^^^^^^^^^^^^^^^^^^^^^^^^

Code written using coroutines looks very similar to code written using
threads.  This is by design. For example, you could take the code in
the previous section and write it to use threads like this::

    import time
    import threading

    def countdown(n):
        while n > 0:
            print('T-minus', n)
            time.sleep(2)
            n -= 1

    def countup(stop):
        n = 1
        while n <= stop:
            print('Up we go', n)
            time.sleep(1)
            n += 1

    threading.Thread(target=countdown, args=(10,)).start()
    threading.Thread(target=countup, args=(15,)).start()

Not only does it look almost identical, it runs in essentially the
same way.  Of course, nobody really cares about code that counts up
and down.  What they really want to do is write network servers.  So,
here's a more realistic thread-programming example involving sockets::

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
                Thread(target=echo_client, args=(client, addr)).start()
    
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

Now, here is that same code written with coroutines and Curio::

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

Both versions of code involve the same statements and have the same
overall control flow.  The key difference is that the code involving
coroutines is executed entirely in a single thread by the ``run()``
function which is scheduling and switching the coroutines on its own
without any assistance from the operating system.   The code using threads
spawns actual system threads (e.g., POSIX threads) that are scheduled
by the operating system.

The coroutine approach has certain advantages and disadvantages.  One
potential advantage of the coroutine approach is that task switching
can only occur on statements involving the ``await`` keyword.  Thus, it
might be easier to reason about the behavior (in contrast, threads are
fully preemptive and might switch on any statement).  Coroutines are
also far more resource efficient--you can creates hundreds of
thousands of coroutines without much concern.  A hundred thousand
threads? Good luck.

Sadly, a big disadvantage of coroutines is that any kind of
long-running calculation or blocking operation can't be preempted.
So, a coroutine might hog the CPU for an extended period and force
other coroutines to wait.  If you love staring at the so-called
"beachball of death" on your laptop, coroutines are for you.  The
other downside is that code must be written to explicitly take
advantage of coroutines (e.g., explicit use of ``async`` and
``await``).  As a general rule, you can't just plug someone's
non-coroutine network package into your coroutine code and expect it
to work.  Threads, on the other hand, already work with most existing
Python code.   So, there are always going to be tradeoffs. 

Coroutines versus Callbacks
^^^^^^^^^^^^^^^^^^^^^^^^^^^

For asynchronous I/O handling, libraries and frameworks will sometimes
make use of callback functions.  For example, here is an echo server
written in the callback style using Python's ``asyncio`` module::

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
The control-flow is much easier to follow and the number of required
functions tends to be significantly less.  In fact, the main
motivation for adding ``async`` and ``await`` to Python and other
languages is to simplify asynchronous I/O by avoiding callback hell.

Historical Perspective
^^^^^^^^^^^^^^^^^^^^^^

Coroutines were first invented in the earliest days of computing to
solve problems related to multitasking and concurrency.  Given the
simplicity and benefits of the programming model, one might wonder why
they haven't been used more often.

A big part of this is really due to the lack of proper support in
mainstream programming languages used to write systems software.  For
example, languages such as Pascal, C/C++, and Java don't support
coroutines. Thus, it's not a technique that most programmers would
even think to consider.  Even in Python, proper support for coroutines
took a long time to emerge.  Projects such as Stackless Python
supported concepts related to coroutines more than 15 years ago, but
it was probably too far ahead of its time to be properly
appreciated. Later on, various projects have explored coroutines in
different forms, usually involving sneaky hacks surrounding generator
functions and C extensions.  The addition of the ``yield from``
construct in Python 3.3 greatly simplified the problem of writing
coroutine libraries.  The emergence of ``async/await`` in Python 3.5
takes a huge stride in making coroutines more of a first-class object
in the Python world.  This is really the starting point for Curio.

Layered Architecture
--------------------

One of the most important design principles of systems programming is
layering. Layering is an essential part of understanding how Curio works
so let's briefly discuss this idea.

Operating System Design and Programming Libraries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Think about how I/O works in the operating system for a moment. At the
lowest level, you'll find device drivers and other hardware-specific
code.  However, the bulk of the operating system is not written to
operate at this low-level. Instead, those details are hidden behind a
device-independent abstraction layer that manages file descriptors,
I/O buffering, flow control, and other details.

.. image:: _static/layers.png

The same layering principal applies to user applications.  The
operating system provides a set of low-level system calls (traps).
These calls vary between operating systems, but you don't really care
as a programmer.  That's because the implementation details are hidden
behind a layer of standardized programming libraries such as the C
standard library, various POSIX standards, Microsoft Windows APIs,
etc.  Working in Python removes you even further from
platform-specific library details. For example, a network program
written using Python's ``socket`` module will work virtually
everywhere.  This is layering and abstraction in action.

Curio in a Nutshell
^^^^^^^^^^^^^^^^^^^

Curio primarily operates as a coroutine scheduling layer that sits
between an application and the Python standard library.  This layer
doesn't actually carry out any useful functionality---it is mainly
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
Curio provides a special "trap" call for this called ``_read_wait()``.   Here's a
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
    >>> c, a = run(accept_connection, s)

With that code running, try making a connection using ``telnet``, ``nc`` or similar command.
You should see the ``run()`` function return the result after the connection is made.

Now, a couple of important details about what's happening:

* The actual I/O operation is performed using the normal ``accept()`` method of
  a socket.  It is the same method that's used in synchronous code not involving coroutines.

* Curio only enters the picture if the attempted I/O operation raises a
  ``BlockingIOError`` exception.  In that case, the coroutine must wait for I/O
  and retry the I/O operation later (the retry is why it's enclosed in a ``while`` loop).

* Curio does not actually perform any I/O. It is only responsible for waiting.
  The ``_read_wait()`` call suspends until the associated socket can be read.

* Incoming I/O is not handled as an "event" nor are there any
  associated callback functions.  If an incoming connection is received, the coroutine
  is scheduled to run again. That's it.  There is no "event loop."  There are no
  callback functions.

With the newly established connection, write a coroutine that receives some data::

    >>> async def read_data(s, maxsize):
    ...     while True:
    ...         try:
    ...              return s.recv(maxsize)
    ...         except BlockingIOError:
    ...              await _read_wait(s)
    ... 
    >>> data = run(read_data c, 1024)

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
* Release from a wait queue.
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
               await spawn(echo_client, client)
 
     async def echo_client(sock):
          while True:
               data = await sock.recv(100000)
               if not data:
                   break
               await sock.sendall(data)

This is exactly what's happening with sockets in Curio.  It provides a
coroutine wrapper around a normal socket and let's you write
normal-looking socket code.   It doesn't change the behavior or semantics of
how sockets work.

It's important to emphasize that a proxy doesn't change how you
interact with an object.  You use the same method names as you did
before coroutines and you should assume that they have the same
underlying behavior. Curio is really only concerned with the
scheduling problem--not I/O.

Supported Functionality
^^^^^^^^^^^^^^^^^^^^^^^

For the most part, Curio tries to provide the same I/O functionality
that one would typically use in a synchronous program involving
threads.  This includes sockets, subprocesses, files, synchronization
primitives, queues, and various odds-and-ends such as TLS/SSL.  You
should consult the reference manual or the howto guide for more
details and specific programming recipes.   The rest of this document
focuses more on the higher-level task model and other programming
considerations related to using Curio.

The Curio Task Model
--------------------

When a coroutine runs inside Curio, it becomes a "Task."  A major portion
of Curio concerns the management and coordination of tasks.  This 
section describes the overall task model and operations involving tasks.

Creating Tasks
^^^^^^^^^^^^^^

An application that uses Curio is always launched by providing an initial
coroutine to the ``run()`` function.  For example::

    import curio

    async def main():
        print('Starting')
        ...

    curio.run(main)

That first coroutine becomes the initial task.  If you want to create
more tasks that execute concurrently, use the ``spawn()`` coroutine. 
``spawn()`` is only valid inside other coroutines so you might use it to
launch more tasks inside ``main()`` like this::

    import curio
    
    async def child(n):
        print('Sleeping')
        await curio.sleep(n)
        print('Awake again!')

    async def main():
        print('Starting')
        await curio.spawn(child, 5)

    curio.run(main)

As a general rule, it's not great style to launch a task and to simply forget about it.
Instead, you should pick up its result at some point.  Use the ``join()`` method to do that.
For example::

    async def main():
        print('Starting')
        task = await curio.spawn(child, 5)
        await task.join()
        print('Quitting')

If you've programmed with threads, the programming model is similar.  One important
point though---you only use ``spawn()`` if you want concurrent task execution.
If a coroutine merely wants to call another coroutine in a synchronous manner like a
library function, you just use ``await``.  For example::

    async def main():
        print('Starting')
        await child(5)      
        print('Quitting')

Returning Results
^^^^^^^^^^^^^^^^^

The ``task.join()`` method returns the final result of a coroutine.  For example::

    async def add(x, y):
        return x + y

    async def main():
        task = await curio.spawn(add, 2,3)
        result = await task.join()
        print('Result ->', result)    # Prints 5

If an exception occurs in the task, it is wrapped in a ``TaskError``
exception.  This is a chained exception where the ``__cause__``
attribute contains the actual exception that occurred.  For example::

    async def main():
        task = await curio.spawn(add, 2, 'Hello')   # Fails due to TypeError
        try:
            result = await task.join()
        except curio.TaskError as err:
            # Reports the resulting TypeError
            print('It failed. Cause:', repr(err.__cause__))

The use of ``TaskError`` serves an important, but subtle, purpose
here.  Due to cancellation and timeouts, the ``task.join()`` operation
might raise an exception that's unrelated to the underlying task
itself.  This means that you need to have some way to separate
exceptions related to the ``join()`` operation versus an exception
that was raised inside the task.  The ``TaskError`` solves this
issue--if you get that exception, it means that the task being joined
exited with an exception.  If you get other exceptions, they are
related to some aspect of the ``join()`` operation itself (i.e.,
cancellation), not the underlying Task.

Task Exit
^^^^^^^^^

Normally, a task exits when it returns.  If you're deeply buried into
the guts of a bunch of code and you want to force a task exit, raise
a ``TaskExit`` exception.  For example::

    from curio import *

    async def coro1():
        print('About to die')
        raise TaskExit()

    async def coro2():
        try:
            await coro1()
        except Exception as e:
            print('Something went wrong')

    async def coro3():
        await coro2()

    try:
        run(coro3())
    except TaskExit:
        print('Task exited')

Like the ``SystemExit`` built-in exception, ``TaskExit`` is a subclass
of ``BaseException`` and won't be caught by exception handlers that
look for ``Exception``.  

If you want all tasks to die, raise a ``SystemExit`` or ``KernelExit``
exception instead.  If this is raised in a task, the entire Curio
kernel stops. In most situations, the leads to an orderly shutdown of
all remaining tasks--each task being given a cancellation request.

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
        task = await curio.spawn(child, 5)
        await time.sleep(1)
        await task.cancel()     # Cancel the child

    curio.run(main)

Cancellation only occurs on blocking operations involving the
``await`` keyword (e.g., the ``curio.sleep()`` call in the child).
When a task is cancelled, the current operation fails with a
``TaskCancelled`` exception. This exception can be caught, but if
doing so, you usually use its base class ``CancelledError``::

    async def child(n):
        print('Sleeping')
        try:
            await curio.sleep(n)
            print('Awake again!')
        except curio.CancelledError:
            print('Rudely cancelled')
            raise

A cancellation can be caught, but should not be ignored.  In fact, the
``task.cancel()`` method blocks until the task actually terminates.
If ignored, the cancelling task would simply hang forever waiting.
That's probably not what you want.  In most cases, code that catches
cancellation should perform some cleanup and then re-raise the
exception as shown above.

Cancellation does not propagate to child tasks.
For example, consider this code::

    from curio import sleep, spawn, run, CancelledError

    async def sleeper(n):
        print('Sleeping for', n)
        await sleep(n)
        print('Awake again')

    async def coro():
        task = await spawn(sleeper, 10)
        try:
            await task.join()
        except CancelledError:
            print('Cancelled')
            raise

    async def main():
        task = await spawn(coro)
        await sleep(1)
        await task.cancel()

    run(main)

If you run this code, the ``coro()`` coroutine is cancelled, but its
child task continues to run afterwards.  The output looks like this::

    Sleeping for 10
    Cancelled
    Awake again

To cancel children, they must be explicitly cancelled.  Rewrite ``coro()`` like this::

    async def coro():
        task = await spawn(sleeper, 10)
        try:
            await task.join()
        except CancelledError:
            print('Cancelled')
            await task.cancel()        # Cancel child task
            raise

Since cancellation doesn't propagate except explicitly as shown, one
way to shield a coroutine from cancellation is to launch it as a
separate task using ``spawn()``. Unless it's directly cancelled, a
task always runs to completion.

Daemon Tasks
^^^^^^^^^^^^

Normally Curio runs tasks until all tasks have completed.  As an
option, you can launch a so-called "daemon" task.  For example::

    async def spinner():
        while True:
            print('Spinning')
            await sleep(5)

    async def main():
        await spawn(spinner, daemon=True)
        await sleep(20)
        print('Main. Goodbye')


    run(main)     # Runs until main() returns
    
A daemon task runs in the background, potentially forever.  The
``Kernel.run()`` method will execute tasks until all non-daemon tasks
are finished.  If you call the kernel ``run()`` method again with a
new coroutine, the daemon tasks will still be there.  If you shut down
the kernel, the daemon tasks are cancelled.  Note: the high-level
``run()`` function performs a shutdown so it would shut down all
of the daemon tasks on your behalf.

Timeouts
^^^^^^^^

Curio allows every blocking operation to be aborted with a timeout.
However, instead of instrumenting every possible API call with a
``timeout`` argument, it is applied through ``timeout_after(seconds [,
coro])``.  The specified timeout serves as a completion deadline for
the supplied coroutine. For example::

    from curio import *

    async def child():
        print('Yawn. Getting sleeping')
        await sleep(10)
        print('Back awake')

    async def main():
        try:
            await timeout_after(1, child)
        except TaskTimeout:
            print('Timeout')

    run(main)

After the specified timeout period expires, a ``TaskTimeout``
exception is raised by whatever blocking operation happens to be in
progress.  ``TaskTimeout`` is a subclass of ``CancelledError`` so code
that catches the latter exception can be used to catch both kinds of
cancellation.  It is critical to emphasize that timeouts can only
occur on operations that block in Curio.  If the code runs away to go
mine bitcoins for the next ten hours, a timeout won't be
raised--remember that coroutines can't be preempted except on blocking
operations.

The ``timeout_after()`` function can also be used as a context
manager.  This allows it to be applied to an entire block of
statements. For example::

    try:
        async with timeout_after(5):
             await coro1()
             await coro2()
             ...
    except TaskTimeout:
        print('Timeout')

Sometimes you might just want to stop an operation and silently move
on. For that, you can use the ``ignore_after()`` function.  It works
like ``timeout_after()`` except that it doesn't raise an exception.
For example::

    result = await ignore_after(seconds, coro)
    
In the event of a timeout, the return result is ``None``. So, instead
of using ``try-except``, you could do this::

    if await ignore_after(seconds, coro) == None:
        print('Timeout')

The ``ignore_after()`` function also works as a context-manager. When
used in this way, a ``expired`` attribute is set to ``True`` when a
timeout occurs. For example::

    async with ignore_after(seconds) as t:
        await coro1()
        await coro2()

    if t.expired:
        print('Timeout')

Nested Timeouts
^^^^^^^^^^^^^^^

Timeouts can be nested, but the semantics are a bit hair-raising and
surprising at first. To illustrate, consider this bit of code::

    async def coro1():
        print('Coro1 Start')
        await sleep(10)
        print('Coro1 Success')

    async def coro2():
        print('Coro2 Start')
        await sleep(1)
        print('Coro2 Success')

    async def child():
        try:
            await timeout_after(50, coro1)
        except TaskTimeout:
            print('Coro1 Timeout')

        await coro2()

    async def main():
        try:
            await timeout_after(5, child)
        except TaskTimeout:
            print('Parent Timeout')

In this code, an outer coroutine ``main()`` applies a 5-second timeout
to an inner coroutine ``child()``.  Internally, ``child()`` applies a
50-second timeout to another coroutine ``coro1()``.  If you run this
program, the outer timeout fires, but the inner one remains silent.
You'll get this output::

    Coro1 Start
    Parent Timeout        (appears after 5 seconds)

To understand this output and why the ``'Coro1 Timeout'`` message
doesn't appear, there are some important rules in play.  First, the
actual timeout period in effect is always the smallest of all of the
applied timeout values. In this code, the outer ``main()`` coroutine
applies a 5 second timeout to the ``child()`` coroutine.  Even though
the ``child()`` coroutine attempts to apply a 50 second timeout to
``coro1()``, the 5 second expiration of the outer timeout is kept in
force.  This is why ``coro1()`` is cancelled when it sleeps for 10
seconds.

The second rule of timeouts is that only the outer-most timeout that
expires receives a ``TaskTimeout`` exception.  In this case, the
``timeout_after(5)`` operation in ``main()`` is the timeout that has
expired.  Thus, it gets the exception.  The inner call to
``timeout_after(50)`` also aborts with an exception, but it is a
``TimeoutCancellationError``.  This signals that the code is being
cancelled due to a timeout, but not the one that was requested.  That
is, the operation is NOT being cancelled due to 50 seconds
passing. Instead, some kind of outer timeout is responsible.
Normally, ``TimeoutCancellationError`` would not be caught.  Instead,
it silently propagates to the outer timeout which handles it.

Admittedly, all of this is a bit subtle, but the key idea is that 
an outer timeout is always allowed to cancel an inner timeout. Moreover,
the ``TaskTimeout`` exception will only arise out of the ``timeout_after()``
call that has expired.   This arrangement allows for tricky corner cases
such as this example::

    async def child():
         while True:
              try:
                   result = await timeout_after(1, coro)
                   ...
              except TaskTimeout:
                   print('Timed out. Retrying')

    async def parent():
         try:
             await timeout_after(5, child)
         except TaskTimeout:
             print('Timeout')

In this code, it might appear that ``child()`` will never terminate
due to the fact that it catches ``TaskTimeout`` exceptions and
continues to loop forever.  Not so--when the ``timeout_after()``
operation in ``parent()`` expires, a ``TimeoutCancellationError`` is
raised in ``child()`` instead.  This causes the loop to stop.

There are are still some ways that timeouts can go wrong and you'll
find yourself battling a sky full of swooping manta rays.  The best
way to make your head explode is to catch ``TaskTimeout`` exceptions
in code that doesn't use ``timeout_after()``.  For example::

    async def child():
         while True:
              try:
                   print('Sleeping')
                   await sleep(10)
              except TaskTimeout:
                   print('Ha! Nope.')

    async def parent():
         try:
             await timeout_after(5, child)
         except TaskTimeout:
             print('Timeout')

In this code, the ``child()`` catches ``TaskTimeout``, but basically
ignores it--running forever.  The ``parent()`` coroutine will hang
forever waiting for the ``child()`` to exit.  The output of the
program will look like this::

    Sleeping
    Ha! Nope.       (after 5 seconds)
    Sleeping
    Sleeping
    ... forever...

Bottom line:  Don't catch free-floating ``TaskTimeout`` exceptions unless your code
immediately re-raises them.

Optional Timeouts
^^^^^^^^^^^^^^^^^

As a special case, you can also supply ``None`` as a timeout for the
``timeout_after()`` and ``ignore_after()`` functions.  For example::

    await timeout_after(None, coro)

When supplied, this leaves any previously set outer timeout in effect.
If an outer timeout expires, a ``TimeoutCancellationError`` is
raised.  If no timeout is effect, it does nothing.

The primary use case of this is to more cleanly write code that
involves an optional timeout setting.  For example::

    async def func(..., timeout=None):
        try:
            async with timeout_after(timeout):
                statements
                ...
        except TaskTimeout as e:
            # Timeout occurred directly due to the supplied timeout argument
            ...
        except TimeoutCancellationError as e:
            # Timeout occurred, but it was due to an outer timeout
            # (Normally you wouldn't catch this exception)
            ...
            raise

Without this feature, you would have to special case the timeout. For example::

    async def func(..., timeout=None):
        if timeout:
            # Code with a timeout applied
            try:
                async with timeout_after(timeout):
                    statements
                    ...
            except TaskTimeout as e:
                # Timeout occurred directly due to the supplied timeout argument
                ...
        else:
            # Code without a timeout applied
            statements
            ...

That's rather ugly--don't do that.  Prefer to use ``timeout_after(None)`` to deal with
an optional timeout.

Cancellation Control
^^^^^^^^^^^^^^^^^^^^

Sometimes it is advantageous to block the delivery of cancellation
exceptions at specific points in your code.  Perhaps your program is
performing a critical operation that shouldn't be interrupted.  To
block cancellation, use the ``disable_cancellation()`` function as a
context manager like this::

    async def coro():
        ...
        async with disable_cancellation():
            await op1()
            await op2()
            ...

       await blocking_op()     # Cancellation delivered here (if any)

When used, the enclosed statements are guaranteed to never abort with
a ``CancelledError`` exception (this includes timeouts).  If any kind
of cancellation request has occurred, it won't be processed until the
next blocking operation outside of the context manager. 

If you are trying to shield a single operation, you can also pass a coroutine to
``disable_cancellation()`` like this::

    async def coro():
        ...
        await disable_cancellation(op)
        ...

Code that disables cancellation can explicitly poll for the presence
of a cancellation request using ``check_cancellation()`` like this::

    async def coro():
        ...
        async with disable_cancellation():
            while True:
                await op1()
                await op2()
                 ...
                if await check_cancellation():
                    break    # We're done

       await blocking_op()     # Cancellation delivered here (if any)

The ``check_cancellation()`` function returns the pending
exception. You can use the result to find out more specific
information if you want. For example::

    async def coro():
        ...
        async with disable_cancellation():
            while True:
                await op1()
                await op2()
                 ...
                cancel_exc = await check_cancellation()
                if isinstance(cancel_exc, TaskTimeout):
                     print('Time expired (shrug)')
                     await set_cancellation(None)
		else:
                     break

       await blocking_op()     # Cancellation delivered here (if any)

The ``set_cancellation()`` function can be used to clear or change the
pending cancellation exception to something else.  The above code ignores
the ``TaskTimeout`` exception and keeps running.

When cancellation is disabled, it can be selectively enabled again using
``enable_cancellation()`` like this::

    async def coro():
        ...
        async with disable_cancellation():
            while True:
                await op1()
                await op2()

                async with enable_cancellation():
                    # These operations can be cancelled
                    await op3()
                    await op4()

                if await check_cancellation():
                    break    # We're done

       await blocking_op()     # Cancellation delivered here (if any)

When cancellation is re-enabled, it allows the enclosed statements to 
receive cancellation requests and timeouts as exceptions as normal.

An important feature of ``enable_cancellation()`` is that it does not
propagate cancellation exceptions--meaning that it does not allow
such exceptions to be raised in the outer block of statements
where cancellation is disabled.  Instead, if there is a cancellation,
it becomes "pending" at the conclusion of the ``enable_cancellation()``
context.  It will be delivered at the next blocking operation where 
cancellation is allowed.   Here is a concrete example that illustrates
this behavior::

    async def coro():
        async with disable_cancellation():
            print('Hello')
            async with enable_cancellation():
                print('About to die')
                raise CancelledError()
                print('Never printed')
            print('Yawn')
            await sleep(2)

        print('About to deep sleep')
        await sleep(5000)

    run(coro)

If you run this code, you'll get output like this::

    Hello
    About to die
    Yawn
    About to deep sleep
    Traceback (most recent call last):
    ...
    curio.errors.CancelledError

Carefully observe that cancellation is being reported on the first blocking operation
outside the ``disable_cancellation()`` block.  There will be a quiz later.

It is fine for ``disable_cancellation()`` blocks to be nested.   This makes them
safe for use in subroutines.  For example::

    async def coro1():
         async with disable_cancellation():
              await coro2()

         await blocking_op1()  # <-- Cancellation reported here

    async def coro2():
         async with disable_cancellation():
              ...

         await blocking_op2()

    run(coro1)

If nested, cancellation is reported at the first blocking operation
that occurs when cancellation is re-enabled.   

It is illegal for ``enable_cancellation()`` to be used outside of a
``disable_cancellation()`` context.  Doing so results in a
``RuntimeError`` exception.  Cancellation is normally enabled in Curio
so it makes little sense to use this feature in isolation.  Correct
usage also tends to require careful coordination with code in which
cancellation is disabled.  For that reason, it can't be used by
itself.  

It is also illegal for any kind of cancellation exception to be raised
in a ``disable_cancellation()`` context. For example::

    async def coro():
        async with disable_cancellation():
            ...
            raise CancelledError()    # ILLEGAL
            ...

Doing this causes your program to die with a ``RuntimeError``.  The
``disable_cancellation()`` feature is meant to be a strong guarantee
that cancellation-related exceptions are not raised in the given block
of statements.  If you raise such an exception, you're violating the
rules.  

It is legal for cancellation exceptions to be raised inside a
``enable_cancellation()`` context.  For example::

    async def coro():
        async with disable_cancellation():
            ...
            async with enable_cancellation():
                ...
                raise CancelledError()    # LEGAL

            # Exception becomes "pending" here
            ...

        await blocking_op()  # Cancellation reported here

Cancellation exceptions that escape ``enable_cancellation()`` become
pending and are reported when blocking operations are performed later.

Programming Considerations for Cancellation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Cancellation and timeouts are an important part of Curio and there
are a few considerations to keep in mind when writing library
functions.

If you need to perform some kind of cleanup action such as
killing a helper task, you'll probably want to wrap it in a
``try-finally`` block like this::

    async def coro():
        task = await spawn(helper)
        try:
            ...
        finally:
            await task.cancel()

This will make sure you properly clean up after yourself.  Certain
objects might work as asynchronous context managers.  Prefer to
use that if available.  For example::

    async def coro():
        task = await spawn(helper)
        async with task:
            ...
        # task cancelled here

If you must catch cancellation errors, make sure you re-raise them.
It's not legal to simply ignore cancellation. Correct cancellation
handling code will typically look like this::

    async def coro():
        try:
            ...
        except CancelledError:
            # Some kind of cleanup
            ...
            raise

If you are going to perform cleanup actions in response to
cancellation or timeout, be extremely careful with blocking operations
in exception handlers.  In rare instances, it's possible that your
code could receive ANOTHER cancellation exception while it's handling
the first one (e.g., getting a direct cancellation request while
handling a timeout).  Here's where things might go terribly wrong::

    async def coro():
        try:
            ...
        except CancelledError:
            ...
            await blocking_op()     # Could receive cancellation/timeout
            other_op()              # Won't execute
            raise

If that happens, the sky will suddenly turn black from an incoming
swarm of howling locusts. It will not end well as you try to figure
out what combination of mysterious witchcraft led to part of your
exception handler not fully executing.  If you absolutely must block
to perform a cleanup action, shield that operation from cancellation like this::

    async def coro():
        try:
            ...
        except CancelledError:
            ...
            await disable_cancellation(blocking_op)  # Will not be cancelled
            other_op()                               # Will execute
            raise

You might consider writing code that returns partially completed
results on cancellation.  Partial results can be attached to the
resulting exception.  For example::

    async def sendall(sock, data):
        bytes_sent = 0
        try:
            while data:
                nsent = await sock.send(data)
                bytes_sent += nsent
                data = data[nsent:]
        except CancelledError as e:
            e.bytes_sent = bytes_sent
            raise

This allows code further up the call-stack to take action and maybe
recover in some sane way.  For example::

    async def send_message(sock, msg):
         try:
             await sendall(sock, msg)
         except TaskTimeout as e:
             print('Well, that sure is slow')
             print('Only sent %d bytes' % e.bytes_sent)

Finally, be extremely careful writing library code that involves infinite
loops.  You will need to make sure that the code can terminate
through cancellation in some manner.   This either means making
sure than cancellation is enabled (the default) or explicitly checking
for it in the loop using ``check_cancellation()``.   For example::

    async def run_forever():
        while True:
            await coro()
            ...
            if await check_cancellation():
                break

Just to emphasize, you normally don't need to check for cancellation
by default though--you'd only need this if it were disabled prior to
calling ``run_forever()``.

Waiting for Multiple Tasks and Concurrency
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a task is launched using ``spawn()``, it executes concurrently with the
creating coroutine.  If you need to wait for the task to finish, you normally
use ``join()`` as described in the previous section.

If you create multiple tasks, you might want to wait for them to complete in 
more advanced ways.  For example, obtaining results one at a time in the order
that tasks finish.  Or waiting for the first result to come back and cancelling
the remaining tasks afterwards. 

For these kinds of problems, you can create a ``TaskGroup`` instance.
Here is an example that obtains results in the order that
tasks are completed::

    async def main():
        async with TaskGroup() as g:
            # Create some tasks
            await g.spawn(coro1)
            await g.spawn(coro2)
            await g.spawn(coro3)
            async for task in g:
                 try:
                     result = await task.join()
                     print('Success:', result)
                 except TaskError as e:
                     print('Failed:', e)

To wait for any task to complete and to have remaining tasks
cancelled, modify the code as follows::

    async def main():
        async with TaskGroup(wait=any) as g:
            # Create some tasks
            await g.spawn(coro1)
            await g.spawn(coro2)
            await g.spawn(coro3)

        # Get result on first completed task
        result = g.completed.result()

If any task in a task group fails with an unexpected exception, all of
the tasks in the group are cancelled and a ``TaskGroupError``
exception is raised.  This exception contains more information 
about what happened including all of the tasks that failed.  For
example::

    async def bad1():
        raise ValueError('Bad value')

    async def bad2():
        raise RuntimeError('Whoa!')

    async def main():
        try:
            async with TaskGroup() as g:
                await g.spawn(bad1)
                await g.spawn(bad2)
        except TaskGroupError as e:
            print(e.errors)   # The set { ValueError, RuntimeError }

            # Iterate over all failed tasks and print their exception
            for task in e:
                print(task, e)  

If a taskgroup is cancelled while waiting, all tasks in the group are
also cancelled. 

Sometimes you might want to launch a task where the result is discarded.
To do that, use the ``ignore_result`` option to ``spawn()`` like this::

    async def main():
        async with TaskGroup() as g:
            await g.spawn(sometask, ignore_result=True)
            ...

When this is used, the task is still managed by the group in the usual
way with respect to waiting and cancellation.  However, the final result
of the task is never inspected--even if the task aborts with an error.
This option is useful in contexts when a task group might be long-lived,
such as use in a server. 

Getting a Task Self-Reference
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a coroutine is running in Curio, there is always an associated ``Task`` instance.
It is returned by the ``spawn()`` function. For example::

    task = await spawn(coro)

The ``Task`` instance is normally only needed for operations
involving joining or cancellation and typically those steps are performed
in the same code that called ``spawn()``.   If for some reason, you need
the ``Task`` instance and don't have a reference to it available, you can
use ``current_task()`` like this::

    from curio import current_task

    async def coro():
        #  Get the Task that's running me
        task = await current_task()      # Get Task instance
        ...

Here's a more interesting example of a function that applies a watchdog
to the current task, cancelling it if nothing happens within a certain
time period::

    from curio import *

    async def watchdog(interval):
        task = await current_task()
        async def watcher():
            while not task.terminated:
                cycles = task.cycles
                await sleep(interval)
                if cycles == task.cycles:
                    print('Cancelling', task)
                    await task.cancel()
        await spawn(watcher)


   async def coro():
       await watchdog(30)     # Enable a watchdog timer
       await sleep(10000)

   run(coro)

In this code, you can see how ``current_task()`` is used to get a Task
self-reference in the ``watchdog()`` coroutine.  ``watchdog()`` then
uses it to monitor the number of execution cycles completed and to
issue a cancellation if nothing seems to be happening.

At a high level, obtaining a task self-reference simplifies the API.
For example, the ``coro()`` code merely calls ``watchdog(30)``.
There's no need to pass an extra ``Task`` instance around in the
API--it can be easily obtained if it's needed.

Programming with Threads
------------------------

Asynchronous I/O is often viewed as an alternative to thread
programming (e.g., Threads Bad!).  However, it's really not an
either-or question.  Threads are still useful for a variety of of
things.  In this section, we look at some strategies for programming
and interacting with threads in Curio.

Execution of Blocking Operations
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Blocking operations are a serious problem for any asynchronous code. 
Of particular concern are calls to normal synchronous functions that
might perform some kind of hidden I/O behind the scenes. 
For example, suppose you had some code like this::

    import socket

    async def handler(client, addr):
        hostinfo = socket.gethostbyaddr(addr[0])
        ...

In this code, the ``gethostbyaddr()`` function performs a reverse-DNS
lookup on an address.  It's not CPU intensive, but while it completes,
it's going to completely block the Curio kernel loop from executing any
other work.  It's not the sort of thing that you'd want in
your program.  Under heavy load, you might find your program to be sort
of glitchy or laggy.

To fix the problem, you could rewrite the operation entirely using
asynchronous I/O operations.  However, that's not always practical.
So, an alternative approach is to offload it to a background thread
using ``run_in_thread()`` like this::

    import socket
    from curio import run_in_thread

    async def handler(client, addr):
        hostinfo = await run_in_thread(socket.gethostbyaddr, addr[0])
        ...

In this code, the execution of ``gethostbyaddr()`` takes place in its
own thread, freeing the Curio kernel loop to work on other tasks in
the meantime.

Under the covers, Curio maintains a pool of preallocated threads
dedicated for performing synchronous operations like this (by default
the pool consists of 64 worker threads). The ``run_in_thread()``
function uses this pool. You're not really supposed to worry about
those details though.

Various parts of Curio use ``run_in_thread()`` behind the scenes. For
example, the ``curio.socket`` module provides replacements for various
blocking operations::

    from curio import socket

    async def handler(client, addr):
        hostinfo = await socket.gethostbyaddr(addr[0])  # Uses threads
        ...

Another place where threads are used internally is in file I/O with
standard files on the file system.  For example, if you use the Curio
``aopen()`` function::

    from curio import aopen
  
    async def coro(filename):
        async with aopen(filename) as f:
            data = await f.read()
        ...

In this code, it might appear as if asynchronous I/O is being
performed on files.  Not really--it's all smoke and mirrors with
background threads (if you must know, this approach to files is not
unique to Curio though).

One caution with ``run_in_thread()`` is that it should probably only
be used on operations where there is an expectation of it completing
in the near future. Technically, you could use it to execute blocking
operations that might wait for long time periods.  For example,
waiting on a thread-event::

    import threading
    from curio import run_in_thread

    evt = threading.Event()     # A thread-event (not Curio)
    
    async def worker():
        await run_in_thread(evt.wait)    # Danger
        ...

Yes, this "works", but it also consumes a worker thread and makes it
unavailable for other use as long as it waits for the event.
If you launched a large number of worker tasks, there is a
possibility that you would exhaust all of the available threads in
Curio's internal thread pool.  At that point, all further
``run_in_thread()`` operations will block and your code will likely
deadlock.  Don't do that.  Reserve the ``run_in_thread()`` function
for operations that you know are basically going to run to completion 
at that moment.

For blocking operations involving a high degree of concurrency and
usage of shared resources such as thread locks and events, prefer to
use ``block_in_thread()`` instead.  For example::

    import threading
    from curio import block_in_thread

    evt = threading.Event()     # A thread-event (not Curio)
    
    async def worker():
        await block_in_thread(evt.wait)   # Better
        ...

``block_in_thread()`` still uses a background thread, but only one
background thread is used regardless of how many tasks try to execute
the same callable.  For example, if you launched 1000 worker tasks and
they all called ``block_in_thread(evt.wait)`` on the same event, they are
serviced by a single thread.  If you used ``run_in_thread(evt.wait)``
instead, each request would use its own thread and you'd exhaust the
thread pool.  It is important to note that this throttling is 
based on each unique callable.  If two different workers used 
``block_in_thread()`` on two different events, then they each get
their own background thread because the ``evt.wait()`` operation 
would represent a different callable.

Behind the scenes, ``block_in_thread()`` coordinates and throttles
tasks using a semaphore.  You can use a similar technique more
generally for throttling the use of threads (or any resource).  For
example::

    from curio import run_in_thread, Semaphore

    throttle = Semaphore(5)   # Allow 5 workers to use threads at once

    async def worker():
        async with throttle:
            await run_in_thread(some_callable)
        ...

Threads and Cancellation
^^^^^^^^^^^^^^^^^^^^^^^^

Both the ``run_in_thread()`` and ``block_in_thread()`` functions allow
the pending operation to be cancelled.  However, if the operation in
question has already started execution, it will fully run to
completion behind the scenes.  Sadly, threads do not provide any
mechanism for cancellation.  Thus, there is no way to make them stop
running once they've started.

If work submitted to a thread is cancelled, Curio sets the thread aside
and removes it from Curio's internal thread pool.  The thread will
continue to run to completion, but at least it won't block progress
of future operations submitted to ``run_in_thread()``.  Once the work
completes, the thread will self-terminate.  Be aware that there is still
a chance you could make Curio consume a lot of background threads
if you submitted a large number of long-running tasks and had them
all cancelled. Here's an example::

    from curio import ignore_after, run_in_thread, run
    import time

    async def main():
        for i in range(1000):
            await ignore_after(0.01, run_in_thread(time.sleep, 100))
   
    run(main)

In this code, Curio would spin up 1000 background worker threads--all
of which end up as "zombies" just waiting to finish their work (which is
now abandoned because of the timeout).  Try not to do this.

The ``run_in_thread()`` and ``block_in_thread()`` functions optionally
allow a cancellation callback function to be registered.  This function
will be triggered in the event of cancellation and gives a thread an
opportunity to perform some kind of cleanup action.  For example::

    import time

    def add(x, y):
        time.sleep(10)
        return x + y

    def on_cancel(future):
        print('Where did everyone go?')
        print('Result was:', future.result())

    async def main():
        await ignore_after(1, run_in_thread(add, 2, 3, call_on_cancel=on_cancel))
        print('Yawn!')
        await sleep(20)
        print('Goodbye')

    run(main)

If you run this code, you'll get output like this::

    Yawn!
    Where did everyone go?
    Result was: 5
    Goodbye

The function given to ``call_on_cancel`` is a synchronous function
that receives the underlying ``Future`` instance that was being used
to execute the background work.  This function executes in the same
thread that was performing the work itself.

The ``call_on_cancel`` functionality is critical for certain kinds of
operations where the cancellation of a thread would cause unintended
mayhem.  For example, if you tried to acquire a thread lock using
``run_in_thread()``, you should probably do this::

    import threading

    lock = threading.Lock()

    async def coro():
        await run_in_thread(lock.acquire, 
                            call_on_cancel=lambda fut: lock.release())
        ...
        await run_in_thread(lock.release)

If you don't do this and the operation got cancelled, the thread would
run to completion, the lock would be acquired, and then nobody would
be around to release it again.  The ``call_on_cancel`` argument is a
safety net that ensures that the lock gets released in the event
that Curio is no longer paying attention.

Thread-Task Synchronization
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Acknowledging the reality that some work still might have to be
performed by threads, even in code that uses asynchronous I/O, you may
faced with the problem of coordinating Curio tasks and external
threads in some way.

One problem concerns task-thread coordination on thread locks and
events.  Generally, it's not safe for coroutines to wait on a foreign
thread lock.  Doing so can block the whole underlying kernel and
everything will come to a grinding halt.  To wait on a foreign lock,
use the ``abide()`` function.  For example::

    import threading
    from curio import abide
    
    lock = threading.Lock()
    
    # Curio task
    async def coro():
        async with abide(lock):
            # Critical section
            ...

    # Synchronous code (in a thread)
    def func():
        with lock:
            # Critical section
            ...
        
``abide()`` adapts a foreign lock to an asynchronous context-manager
and guides its execution using a backing thread.  Under the covers,
``abide()`` is using an asynchronous context manager that is roughly
equivalent to this::

    class AbideManager(object):
        def __init__(self, manager):
            self.manager = manager

        async def __aenter__(self):
            curio.block_in_thread(self.manager.__enter__)
            return self

        async def __aexit__(self, *args):
            curio.run_in_thread(self.manager.__exit__, *args)

The exact details vary due to some tricky corner cases, but the overall
gist is that threads are used to run it and it won't block the
Curio kernel.

You can use ``abide()`` with any foreign ``Lock`` or ``Semaphore`` object
(e.g., it also works with locks defined in the ``multiprocessing``
module).  ``abide()`` tries to be efficient with how it utilizes
threads.  For example, if you spawn up 10000 Curio tasks and have them
all wait on the same lock, only one backing thread gets used.

``abide()`` can work with reentrant locks and condition variables, but there
are some issues concerning the backing thread used to execute the various
locking operations.  In this case, the same thread needs to be used 
for all operations.  To indicate this, use the ``reserve_thread`` keyword
argument::

    import threading
    
    cond = threading.Condition()
    
    # Curio task
    async def coro():
        async with abide(cond, reserve_thread=True) as c:
            # c is a wrapped version of cond() with async methods
            ...
            # Executes on the same thread as used to acquire cond
            await c.wait()    

    # Synchronous code (in a thread)
    def func():
        with cond:
            ...
            cond.notify()
            ...

When the ``reserve_thread()`` option is used, a background thread is
reserved for the entire execution of the ``with``-block. Be aware
that a high degree of concurrency could cause a lot of threads
to be used.

As of this writing, Curio can synchronize with an ``RLock``, but full
reentrancy is not supported--that is nested ``abide()`` calls on the
same lock won't work correctly.  This limitation may be lifted in a
future version.

``abide()`` also works with operations involving events.
For example, here is how you wait for an event::

    import threading

    evt = threading.Event()     # Thread event

    async def waiter():
        await abide(evt.wait)
        print('Awake!')

A curious aspect of ``abide()`` is that it also works with Curio's own
synchronization primitives.   So, this code also works fine::

    import curio
    
    lock = curio.Lock()
    
    # Curio task
    async def coro():
        async with abide(lock):
            # Critical section
            ...

If the provided lock already works asynchronously, ``abide()`` turns
into an identity function.  That is, it doesn't really do anything.
For lack of a better description, this gives you the ability to have a
kind of "duck-synchronization" in your program.  If a lock looks like
a lock, ``abide()`` will probably work with it regardless of where it
came from.

Finally, a caution: having Curio synchronize with foreign locks is not
the fastest thing.  There are backing threads and a fair bit of
communication across the async-synchronous boundary.  If you're doing
a bunch of fine-grained locking where performance is critical, don't
use ``abide()``.  In fact, try to do almost anything else.

Thread-Task Queuing
^^^^^^^^^^^^^^^^^^^

If you must bridge the world of asynchronous tasks and threads,
perhaps the most sane way to do it is to use a queue.  Curio provides
a modestly named ``UniversalQueue`` class that does just that.  Basically,
a ``UniversalQueue`` is a queue that fully supports queuing operations
from any combination of threads or tasks.  For example, you
can have async worker tasks reading data written by a producer thread::

    from curio import run, UniversalQueue, spawn, run_in_thread

    import time
    import threading

    # An async task
    async def consumer(q):
        print('Consumer starting')
        while True:
            item = await q.get()
            if item is None:
                break
            print('Got:', item)
            await q.task_done()
        print('Consumer done')

    # A threaded producer
    def producer(q):
        for i in range(10):
            q.put(i)
            time.sleep(1)
        q.join()
        print('Producer done')

    async def main():
        q = UniversalQueue()

        t1 = await spawn(consumer, q)
        t2 = threading.Thread(target=producer, args=(q,))
        t2.start()
        await run_in_thread(t2.join)
        await q.put(None)
        await t1.join()

    run(main)

Or you can flip it around and have a threaded consumer read
data from async tasks::

    from curio import run, UniversalQueue, spawn, run_in_thread, sleep

    import threading

    def consumer(q):
        print('Consumer starting')
        while True:
            item = q.get()
            if item is None:
                break
            print('Got:', item)
            q.task_done()
        print('Consumer done')

    async def producer(q):
        for i in range(10):
            await q.put(i)
            await sleep(1)
        await q.join()
        print('Producer done')

    async def main():
        q = UniversalQueue()

        t1 = threading.Thread(target=consumer, args=(q,))
        t1.start()
        t2 = await spawn(producer, q)

        await t2.join()
        await q.put(None)
        await run_in_thread(t1.join)

    run(main)

Or, if you're feeling particularly diabolical, you can even use a ``UniversalQueue`` to communicate between
tasks running in two different Curio kernels::

    from curio import run, UniversalQueue, sleep

    import threading

    # An async task
    async def consumer(q):
        print('Consumer starting')
        while True:
            item = await q.get()
            if item is None:
                break
            print('Got:', item)
            await q.task_done()
        print('Consumer done')

    # An async task
    async def producer(q):
        for i in range(10):
            await q.put(i)
            await sleep(1)
        await q.join()
        print('Producer done')

    def main():
        q = UniversalQueue()

        t1 = threading.Thread(target=run, args=(consumer, q))
        t1.start()
        t2 = threading.Thread(target=run, args=(producer, q))
        t2.start()
        t2.join()
        q.put(None)
        t1.join()

    main()

The programming API is the same in both worlds.  For synchronous code, you use
the ``get()`` and ``put()`` methods.  For asynchronous code, you use the same methods,
but preface them with an await.

The underlying implementation is efficient for a large number of waiting
asynchronous tasks.  There is no difference between a single task
waiting for data and ten thousand tasks waiting for data.  Obviously the
situation is a bit different for threads (you probably wouldn't want to
have 10000 threads waiting on a queue, but if you did, an ``UniversalQueue``
would still work).   

One notable feature of ``UniversalQueue`` is that it is cancellation and
timeout safe on the async side.  For example, you can write code like
this::

    # An async task
    async def consumer(q):
        print('Consumer starting')
        while True:
            try:
                item = await timeout_after(5, q.get)
	    except TaskTimeout:
                print('Timeout!')
		continue
            if item is None:
                break
            print('Got:', item)
            await q.task_done()
        print('Consumer done')

In the event of a timeout, the ``q.get()`` operation will abort, but
no queue data is lost.  Should an item be made available, the next
``q.get()`` operation will return it.  This is different than
performing get operations on a standard thread-queue.  For example, if
you you used ``run_in_thread(q.get)`` to get an item on a standard
thread queue, a timeout or cancellation actually causes a queue item
to be lost.

Asynchronous Threads
^^^^^^^^^^^^^^^^^^^^

Come closer. No, I mean real close.  Let's have a serious talk about
threads for a moment.  If you're going to write a SERIOUS thread
program, you're probably going to want a few locks. And once you have
a few locks, you'll probably want some semaphores. Those semaphores
are going to be lonely without a few events and condition variables to
keep them company.  All these things will live together in a messy
apartment along with a pet queue. It will be chaos. It all
sounds a bit better if you put in an internet-connected coffee pot and
call the apartment a coworking space.  But, I digress.

But wait a minute, Curio already provides all of these wonderful things.
Locks, semaphores, events, condition variables, pet queues and more. 
You might think that they can only be used for this funny world of 
coroutines though.  No!  "Get out!"

Let's start with a little thread code::

    import time
    
    def worker(name, lock, n, interval):
        while n > 0:
            with lock:
                print('%s working %d' % (name, n))
                time.sleep(interval)
                n -= 1

    def main():
        from threading import Thread, Semaphore

        s = Semaphore(2)
        t1 = Thread(target=worker, args=('curly', s, 2, 2))
        t1.start()
        t2 = Thread(target=worker, args=('moe', s, 4, 1))
        t2.start()
        t3 = Thread(target=worker, args=('larry', s, 8, 0.5))
        t3.start()

        t1.join()
        t2.join()
        t3.join()

    if __name__ == '__main__':
        start = time.time()
        main()
        print('Took %s seconds' % (time.time() - start))

In this code, there are three workers.  They operate on different time intervals,
but they all execute concurrently.  However, there is a semaphore
thrown into the mix to throttle them so that only two workers can run
at once. The output might vary a bit due to thread scheduling, but
it could look like this::

    curly working 2
    moe working 4
    moe working 3
    curly working 1
    moe working 2
    moe working 1
    larry working 8
    larry working 7
    larry working 6
    larry working 5
    larry working 4
    larry working 3
    larry working 2
    larry working 1
    Took 8.033247709274292 seconds

Each worker performs about 4 seconds of execution.  However, only
two can run at once.  So, the total execution time will be more than 6
seconds.  We see that.

Now, take that code and only change the ``main()`` function::

    async def main():
        from curio import Semaphore
        from curio.thread import AsyncThread

        s = Semaphore(2)
        t1 = AsyncThread(target=worker, args=('curly', s, 2, 2))
        await t1.start()
        t2 = AsyncThread(target=worker, args=('moe', s, 4, 1))
        await t2.start()
        t3 = AsyncThread(target=worker, args=('larry', s, 8, 0.5))
        await t3.start()
        await t1.join()
        await t2.join()
        await t3.join()

    if __name__ == '__main__':
        from curio import run
        run(main)

Make no other changes and run it in Curio.  You'll get very similar
output. The scheduling will be a bit different, but you'll get
something comparable::

    curly working 2
    moe working 4
    larry working 8
    moe working 3
    larry working 7
    curly working 1
    larry working 6
    moe working 2
    larry working 5
    moe working 1
    larry working 4
    larry working 3
    larry working 2
    larry working 1
    Took 6.5362467765808105 seconds

Very good.  But, wait a minute?  Did you just run some unmodified
synchronous thread function (``worker()``) within Curio?  Yes, yes,
you did.  That function not only performed a blocking operation
(``time.sleep()``), it also used a synchronous context-manager on a
Curio ``Semaphore`` object just like it did when it used a
``Semaphore`` from the ``threading`` module.  What devious magic is
this???

In short, an asynchronous thread is a real-life fully realized thread.
A POSIX thread.  A thread created with the ``threading`` module.  Yes,
one of THOSE threads your parents warned you about.  You can perform
blocking operations and everything else you might do in this thread.
However, sitting behind this thread is a Curio task. That's the magic
part.  This hidden task takes over and handles any kind of operation
you might perform on synchronization objects that originate from Curio.  That
``Semaphore`` object you passed in was handled by that task.  So, in
the worker, there was this code fragment::

    with lock:
        print('%s working %d' % (name, n))
        time.sleep(interval)
        n -= 1

The code sitting behind the ``with lock:`` part executes in a Curio
backing task.  The body of statement runs in the thread. 

It gets more wild.  You can have both Curio tasks and asynchronous threads
sharing synchronization primitives.  For example, this code also works fine::

    import time
    import curio

    # A synchronous worker (traditional thread programming)
    def worker(name, lock, n, interval):
        while n > 0:
            with lock:
                print('%s working %d' % (name, n))
                time.sleep(interval)
                n -= 1

    # An asynchronous worker
    async def aworker(name, lock, n, interval):
        while n > 0:
            async with lock:
                print('%s working %d' % (name, n))
                await curio.sleep(interval)
                n -= 1

    async def main():
        from curio.thread import AsyncThread
        from curio import Semaphore

        s = Semaphore(2)

        # Launch some async-threads
        t1 = AsyncThread(target=worker, args=('curly', s, 2, 2))
        await t1.start()
        t2 = AsyncThread(target=worker, args=('moe', s, 4, 1))
        await t2.start()

	# Launch a normal curio task
        t3 = await curio.spawn(aworker, 'larry', s, 8, 0.5)

        await t1.join()
        await t2.join()
        await t3.join()

Just to be clear, this code involves asynchronous tasks and threads
sharing the same synchronization primitive and all executing
concurrently.  No problem.

It gets better.  You can use ``await`` in an asynchronous thread if
you use the ``AWAIT()`` function. For example, consider this code::

    from curio.thread import await, AsyncThread
    import curio

    # A synchronous function
    def consumer(q):
        while True:
            item = AWAIT(q.get())   # <- !!!!
            if not item:
                break
            print('Got:', item)
        print('Consumer done')

    async def producer(n, q):
        while n > 0:
            await q.put(n)
            await curio.sleep(1)
            n -= 1
        await q.put(None)

    async def main():
        q = curio.Queue()

        t = AsyncThread(target=consumer, args=(q,))
        await t.start()
        await producer(10, q)
        await t.join()

    if __name__ == '__main__':
        curio.run(main)

Good Guido, what madness is this?  The code creates a Curio ``Queue``
object that is used from both a task and an asynchronous thread.
Since queue operations normally require the use of ``await``, it's used in
both places.  In the ``producer()`` coroutine, you use ``await
q.put(n)`` to put an item on the queue.  In the ``consumer()``
function, you use ``AWAIT(q.get())`` to get an item.  There's a bit of
asymmetry there, but ``consumer()`` is just a normal synchronous
function.  You can't use the ``await`` keyword in such a function, but
Curio provides a function that takes its place. All is well. Maybe.

And on a related note, why is it ``AWAIT()`` in all-caps like that?
Mostly it's because of all of those coders who continuously and loudly
rant about how you should never program with threads.  Forget that.
Clearly they have never seen async threads before.  It's AWAIT!
AWAIT! AWAIT!  It's shouted so it can be more clearly heard above all
of that ranting.  To be honest, it's also pretty magical--so maybe
it's not such a bad thing for it to jump out of the code at you. Boo!
And there's the tiny detail of ``await`` being a reserved
keyword. Let's continue.

A curious thing about the Curio ``AWAIT()`` is that it does nothing
if you give it something other than a coroutine.  So, you could
still use that ``consumer()`` function with a normal thread.
Just pop into the REPL and try this::

    >>> import queue
    >>> import threading
    >>> q = queue.Queue()
    >>> t = threading.Thread(target=consumer, args=(q,))
    >>> t.start()
    >>> q.put(1)
    Got: 1
    >>> q.put(2)
    Got: 2
    >>> q.put(None)
    Consumer done
    >>> 

Just to be clear about what's happening here,  ``consumer()`` is a normal synchronous
function.  It uses the ``AWAIT()`` function on a queue.  We just gave
it a normal thread queue and launched it into a normal thread at the
interactive prompt.  It still works. Curio is not running at all.

Running threads within Curio have some side benefits.  If you're
willing to abandon the limitations of the ``threading`` module, you'll
find that Curio's features such as timeouts and cancellation work
fine in a thread.  For example::

    from curio.thread import await, AsyncThread
    import curio

    def consumer(q):
        try:
            while True:
                try:
                    with curio.timeout_after(0.5):
                        item = AWAIT(q.get())
                except curio.TaskTimeout:
                    print('Ho, hum...')
		    continue
                print('Got:', item)
                AWAIT(q.task_done())
        except curio.CancelledError:
            print('Consumer done')
            raise

    async def producer(n, q):
        while n > 0:
            await q.put(n)
            await curio.sleep(1)
            n -= 1
        print('Producer done')

    async def main():
        q = curio.Queue()

        t = AsyncThread(target=consumer, args=(q,))
        await t.start()
        await producer(10, q)
        await q.join()
        await t.cancel()

    if __name__ == '__main__':
        curio.run(main)

Here the ``t.cancel()`` cancels the async-thread.  As with normal Curio
tasks, the cancellation is reported on blocking operations involving ``AWAIT()``.
The ``timeout_after()`` feature also works fine.  You don't use it as an
asynchronous context manager in a synchronous function, but it has the same
overall effect.  Don't try this with a normal thread.

The process of launching an asynchronous thread can be a bit cumbersome.
Therefore, there is a special decorator ``@async_thread`` that can be
used to adapt a synchronous function.   There are two ways to use it.
One way to use it is to apply it to a function directly like this::

    from curio.thread import async_thread, await
    from curio import run, tcp_server

    @async_thread
    def sleeping_dog(client, addr):
        with client:
            for data in client.makefile('rb'):
                n = int(data)
                time.sleep(n)
                AWAIT(client.sendall(b'Bark!\n'))
        print('Connection closed')

    run(tcp_server, '', 25000, sleeping_dog)

If you do this, the function becomes a coroutine where any invocation
automatically launches it into a thread. This is useful if you need to
write coroutines that perform a lot of blocking operations, but you'd
like that coroutine to work transparently with the rest of Curio.

The other way to use the decorator is an adapter for existing
synchronous code. For example, here is an alternative technique
for launching an asynchronous thread::

    from curio.thread import await, async_thread
    import curio

    # A synchronous function
    def consumer(q):
        while True:
            item = AWAIT(q.get())   # <- !!!!
            if not item:
                break
            print('Got:', item)
        print('Consumer done')

    async def main():
        q = curio.Queue()
        t = await spawn(async_thread(consumer), q)
        ...
        await t.join()

All of this discussion is really not presenting asynchronous threads
in their full glory.  The key idea though is that instead of thinking
of threads as being this completely separate universe of code that
exists outside of Curio, you can actually create threads that work
*with* Curio.  They can use all of Curio's synchronization primitives
and they can interact with Curio tasks.  These threads can use all of
Curio's normal features and they can perform blocking operations. They
can call C extensions that release the GIL.  You can have these
threads interact with existing libraries.  If you're organized, you
can write synchronous functions that work with Curio and with normal
threaded code at the same time.  It's a brave new world.

Programming with Processes
--------------------------

A pitfall of asynchronous I/O is that it does not play nice with
CPU-intensive operations.  Just as a synchronous blocking operation
can stall the kernel, a long-running calculation can do the same.
Although calculations can be moved over to threads, that does not work
as well as you might expect.  Python's global interpreter lock (GIL)
prevents more than one thread from executing in parallel.  Moreover,
CPU intensive operations can starve I/O handling.  There's a lot that
can be said about this, but go view Dave's talk at
https://www.youtube.com/watch?v=5jbG7UKT1l4 and the associated slides
at
http://www.slideshare.net/dabeaz/in-search-of-the-perfect-global-interpreter-lock.
The bottom line: threads are not what's you're looking for if
CPU-intensive procecessing is your goal.

Curio provides several mechanisms for working with CPU-intensive work.
This section will describe some approaches you might take.

Launching Subprocesses
^^^^^^^^^^^^^^^^^^^^^^

If CPU intensive work can be neatly packaged up into an independent program
or script, you can have curio run it using the ``curio.subprocess`` module.
This is an asynchronous implementation of the Python standard library module
by the same name. You use it the same way::

    from curio.subprocess import check_output, CalledProcessError

    async def coro():
        try:
            out = await check_output(['prog', 'arg1', 'arg2'])
        except CalledProcessError as e:
            print('Failed!')

This runs an external command, collects its output, and returns it to you
as a string.  Curio also provides an asynchronous version of the ``Popen``
class and the ``subprocess.run()`` function.  Again, the behavior is meant
to mimic that of the standard library module.

Running CPU intensive functions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you have a simple function that performs CPU-intensive work, you can try
running it using the ``run_in_process()`` function.  For example::

    from curio import run_in_process

    def fib(n):
        if n <= 2:
            return 1
        else:
            return fib(n-1) + fib(n-2)

    async def coro():
        r = await run_in_process(fib, 40)

This runs the specified function in a completely separate Python
interpreter and returns the result.  It is critical to emphasize that
this only works if the supplied function is completely isolated.  It
should not depend on global state or have any side-effects.
Everything the function needs to execute should be passed in as
argument.

The ``run_in_process()`` function works with all of Curio's usual
features including cancellation and timeouts.  If cancelled, the
subprocess being used to execute the work is sent a ``SIGTERM`` signal
with the expectation that it will die immediately.

Message Passing and Channels
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

One issue with ``run_in_process()`` is that it doesn't really give
you much control over what's happening in a child process. For
example, you don't have too much control over subtle details such as
signal handling, files, network connections, cancellation, and other
things.  Also, if there is any kind of persistent state, it will be
difficult to manage.

For more complicated kinds of things, you might want to turn to
explicit message passing instead.  For this, Curio provides a
``Channel`` object.  A channel is kind of like a socket except that it
allows picklable Python objects to be sent and received.  It also
provides a bit of authentication.  Here is an example of a simple
producer program using channels::

    # producer.py
    from curio import Channel, run

    async def producer(ch):
        while True:
            c = await ch.accept(authkey=b'peekaboo')
            for i in range(10):
                await c.send(i)
            await c.send(None)   # Sentinel

    if __name__ == '__main__':
        ch = Channel(('localhost', 30000))
        run(producer, ch)

Here is a consumer program::

    # consumer.py
    from curio import Channel, run

    async def consumer(ch):
        c = await ch.connect(authkey=b'peekaboo')
        while True:
            msg = await c.recv()
            if msg is None:
                break
            print('Got:', msg)

    if __name__ == '__main__':
        ch = Channel(('localhost', 30000))
        run(consumer, ch)

Each of these programs create a corresponding ``Channel`` object.  One
of the programs must act as a server and accept incoming connections
using ``Channel.accept()``.  The other program uses
``Channel.connect()`` to make a connection.  As an option, an
authorization key may be provided.  Both methods return a
``Connection`` instance that allows Python objects to be sent and
received.  Any Python object compatible with ``pickle`` is allowed.

Beyond this, how you use a channel is largely up to you.  Each program
runs independently.  The programs could live on the same machine. They
could run on separate machines.  The main thing is that they send
messages back and forth.

One notable thing about channels is that they are compatible with
Python's ``multiprocessing`` module.  For example, you could rewrite
the ``consumer.py`` program like this::

    # consumer.py
    from multiprocessing.connection import Client

    def consumer(address):
        c = Client(address, authkey=b'peekaboo')
        while True:
            msg = c.recv()
            if msg is None:
                break
            print('Got:', msg)

    if __name__ == '__main__':
        consumer(('localhost', 30000))

This code doesn't involve Curio in any way.  However, it speaks the
same messaging protocol.  So, it should work just fine.

Spawning Tasks in a Subprocess
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

As final option, Curio provides a mechanism for spawning tasks in a 
subprocess.   To do this, use the aptly name ``aside()`` function. For
example::

    from curio import Channel, run, aside

    async def producer(ch):
        c = await ch.accept(authkey=b'peekaboo')
        for i in range(10):
            await c.send(i)

    async def consumer(ch):
        c = await ch.connect(authkey=b'peekaboo')
        while True:
            msg = await c.recv()
            print('Got:', msg)

    async def main():
        ch = Channel(('localhost', 30000))
        cons = await aside(consumer, ch)    # Launch consumer in separate process
        await producer(ch)
        await cons.cancel()                 # Cancel consumer process

    if __name__ == '__main__':
        run(main)

``aside()`` does nothing more than launch a new Python subprocess and
invoke ``curio.run()`` on the suppplied coroutine.  Any additional
arguments supplied to ``aside()`` are given as arguments to the
coroutine.

``aside()`` does not involve a pipe or a process fork.  The newly
created process shares no state with the caller.  There is no I/O
channel between processes.  There is no shared signal handling.  If
you want I/O, you should create a ``Channel`` object and pass it as an
argument as shown (or use some other communication mechanism such as
sockets).

A notable thing about ``aside()`` is that it still creates a proper
``Task`` in the caller.  You can join with that task or cancel it.  It
will be cancelled on kernel shutdown if you make it daemonic.  If you
cancel the task, a ``TaskCancelled`` exception is propagated to the
subprocess (e.g., the ``consumer()`` coroutine above gets a proper
cancellation exception when the ``main()`` coroutine invokes
``cons.cancel()``).

Tasks launched using ``aside()`` do not return a normal result.  As
noted, ``aside()`` does not create a pipe or any kind of I/O channel
for communicating a result.  If you need a result, it should be
communicated via a channel.  Should you call ``join()``, the return
value is the exit code of the subprocess.  Normally it is 0.  A
non-zero exit code indicates an error of some kind.

``aside()`` can be particularly useful if you want to programs that
perform sharding or other kinds of distributed computing tricks. For
example, here is an example of a sharded echo server::

    from curio import *
    import signal
    import os

    async def echo_client(sock, address):
        print(os.getpid(), 'Connection from', address)
        async with sock:
            try:
                while True:
                    data = await sock.recv(100000)
                    if not data:
                        break
                    await sock.sendall(data)
            except CancelledError:
                await sock.sendall(b'Server is going away\n')
                raise

    async def main(nservers):
        goodbye = SignalEvent(signal.SIGTERM, signal.SIGINT)
        for n in range(nservers):
            await aside(tcp_server, '', 25000, echo_client, reuse_port=True)
        await goodbye.wait()
        print("Goodbye cruel world!")
        raise SystemExit(0)

    if __name__ == '__main__':
        run(main(10))

In this code, ``aside()`` is used to spin up 10 separate processes,
each of which is running the Curio ``tcp_server()`` coroutine.  The
``reuse_port`` option is used to make them all bind to the same port.
The the main program then waits for a termination signal to arrive,
followed by a request to exit. That's it--you now have ten running Python
processes in parallel.  On exit, every task in every process will be
properly cancelled and each connected client will get the "Server is
going away" message.   It's magic.

Let's step aside for a moment and talk a bit more about some of this
magic.  When working with subprocesses, it is common to spend a lot of
time worrying about things like shutdown, signal handling, and other
horrors.  Yes, those things are an issue, but if you use ``aside()``
to launch tasks, you should just manage those tasks in the usual Curio
way.  For example, if you want to explicitly cancel one of them, use
its ``cancel()`` method.  Or if you want to quit altogether, raise
``SystemExit`` as shown.  Under the covers, Curio is tracking the
associated subprocesses and will manage their lifetime appropriately.
As long as you let Curio do its thing and you shut things down
cleanly, it should all work.

Working with Files
------------------

Let's talk about files for a moment. By files, I mean files on the
file system--as in the thousands of things sitting in the ``Desktop``
folder on your laptop.

Files present a special problem for asynchronous I/O.  Yes, you can
use Python's built-in ``open()`` function to open a file and yes you
can obtain a low-level integer file descriptor for it.  You might even
be able to wrap it with a Curio ``FileStream()`` instance.  However,
under the covers, it's hard to say if it is going to operate in an
async-friendly manner.  Support for asynchronous file I/O has always
been a bit dicey in most operating systems. Often it is nonexistent
unless you resort to very specialized APIs such as the POSIX ``aio_*``
functions. And even then, it might not exist.  

The bottom line is that interacting with traditional files might cause
Curio to block, leading to various performance problems under heavy
load.  As an example, consider everything that has to happen simply to
open a file--for example, traversing through a directory hierarchy,
loading file metadata, etc.  It could involve disk seeks on a physical
device. It might involve network access. It will undoubtedly introduce
a delay in your async code.

If you're going to write code that operates with traditional files,
prefer to use Curio's ``aopen()`` function instead. For example::

    async def coro():
        async with aopen('somefile.txt') as f:
            data = await f.read()    # Get data
            ...

``aopen()`` returns a file-like object where all of the traditional
file methods have been replaced by async-compatible equivalents.
The underlying implementation is guaranteed not to block the
Curio kernel loop.   How this is accomplished may vary by
operating system.  At the moment, Curio uses background
threads to avoid blocking.

Interacting with Synchronous Code
---------------------------------

Asynchronous functions can call functions written in a synchronous
manner.  For example, calling out to standard library modules.
However, this communication is one-way.  That is, an asynchronous
function can call a synchronous function, but the reverse is not true.
For example, this fails::

    async def spam():
        print('Asynchronous spam')

    def yow():
        print('Synchronous yow')
        spam()          # Fails  (doesn't run)
        await spam()    # Fails  (syntax error)
        run(spam)       # Fails  (RuntimeError, only one kernel per thread)

    async def main():
        yow()           # Works

    run(main)

The reason that it doesn't work is that asynchronous functions 
require the use of the Curio kernel and once you call a synchronous
function, it's no longer in control of what's happening. 

It's probably best to think of synchronous code as a whole different
universe.  If for some reason, you need to make synchronous code
communicate with asynchronous code, you need to devise some sort of
different strategy for dealing with it. Curio provides a few different
techniques that synchronous code can use to interact with asynchronous
code from beyond the abyss.

Synchronous/Asynchronous Queuing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

One approach for bridging asynchronous and synchronous code is to use
a ``Queue`` and to take an approach similar to how you might
communicate between threads.  For example, you can write code like
this::

    from curio import run, spawn, Queue

    q = Queue()

    async def worker():
        item = await q.get()
        print('Got:', item)

    def yLazyow():
        print('Synchronous yow')
        q.put('yow')      # Works (note: there is no await)
        print('Goodbye yow')

    async def main():
        await spawn(worker)
        yow()
        await sleep(1)          # <- worker awakened here
        print('Main goodbye')
	
    run(main)

Running this code produces the following output::

    Synchronous yow
    Goodbye yow
    Got: yow
    Main goodbye

Curio queues allow the ``q.put()`` method to be used from synchronous
code.  Thus, if you're in the synchronous realm, you can at least
queue up a bunch of data.  It won't be processed until you return to
the world of Curio tasks though.  So, in the above code, you won't
see the item actually delivered until some kind of blocking operation
is made.

Lazy Coroutine Evalulation
^^^^^^^^^^^^^^^^^^^^^^^^^^

Another approach is to exploit the "lazy" nature of coroutines.
Coroutines don't actually execute until they are awaited.  Thus,
synchronous functions could potentially defer asynchronous operations
until execution returns back to the world of async.  For example, you
could do this::

    async def spam():
        print('Asynchronous spam')

    def yow(deferred):
        print('Synchronous yow')
	deferred.append(spam())      # Creates a coroutine, but doesn't execute it
        print('Goodbye yow')

    async def main():
        deferred = []
        yow(deferred)
	for coro in deferred:
            await coro               # spam() runs here

    run(main)

If you run the above code, the output will look like this::

    Synchronous yow
    Goodbye yow
    Asynchronous spam

Notice how the asynchronous operation has been deferred until control
returns back to the ``main()`` coroutine and the coroutine is properly awaited.

Executing Coroutines on Behalf of Synchronous Code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you are in synchronous code and need to execute a coroutine, you
can certainly use the Curio ``run()`` function to do it.  However, if
you're going to execute a large number of coroutines, you'll be better
served by creating a ``Kernel`` object and repeatedly using its
``run()`` method instead::

    from curio import Kernel

    async def coro(n):
        print('Hello coro', n)

    def main():
        with Kernel() as kern:
           for n in range(10):
               kern.run(coro, n)

    main()

Kernels involve a fair-bit of internal state related to their operation. 
Taking this approach will be a lot more efficient.  Also, if you happen to
launch any background tasks, those tasks will persist and continue to
execute when you make subsequent ``run()`` calls.

Interfacing with Foreign Event Loops
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Sometimes, you may want to interface Curio-based applications with a 
foreign event loop.  This is a scenario that often arises when using
a graphical user interface. 

For this scenario, there are a few possible options.  One choice
is to try and run everything in a single thread.   For this, you
might need to inject callouts to run the foreign event loop on
a periodic timer.   This is a somewhat involved example, but
here is some code that integrates a Curio echo server with a tiny
Tk-based GUI:: 

    import tkinter as tk
    from curio import *

    class EchoApp(object):
        def __init__(self):
            # Pending coroutines
            self.pending = []

            # Main Tk window
            self.root = tk.Tk()

            # Number of clients connected label
            self.clients_label = tk.Label(text='')
            self.clients_label.pack()
            self.nclients = 0
            self.incr_clients(0)
            self.client_tasks = set()

            # Number of bytes received label
            self.bytes_received = 0
            self.bytes_label = tk.Label(text='')
            self.bytes_label.pack()
            self.update_bytes()

            # Disconnect all button
            self.disconnect_button = tk.Button(text='Disconnect all', 
                                               command=lambda: self.pending.append(self.disconnect_all()))
            self.disconnect_button.pack()

        def incr_clients(self, delta=1):
            self.nclients += delta
            self.clients_label.configure(text='Number Clients %d' % self.nclients)            

        def update_bytes(self):
            self.bytes_label.configure(text='Bytes received %d' % self.bytes_received)
            self.root.after(1000, self.update_bytes)

        async def echo_client(self, sock, address):
            self.incr_clients(1)
            self.client_tasks.add(await current_task())
            try:
                async with sock:
                    while True:
                        data = await sock.recv(100000)
                        if not data:
                            break
                        self.bytes_received += len(data)
                        await sock.sendall(data)
            finally:
                self.incr_clients(-1)
                self.client_tasks.remove(await current_task())

        async def disconnect_all(self):
            for task in list(self.client_tasks):
                await task.cancel()

        async def main(self):
            serv = await spawn(tcp_server, '', 25000, self.echo_client)
            while True:
                self.root.update()
                for coro in self.pending:
                    await coro
                self.pending = []
                await sleep(0.05)

    if __name__ == '__main__':
        app = EchoApp()
        run(app.main)

If you run this program, it will put up a small GUI window that looks like this:

.. image:: _static/guiserv.png

The GUI has two labels.  One of the labels shows the number of
connected clients.  It is updated by the ``incr_clients()`` method.  The
other label shows a byte total. It is updated on a periodic timer.
The button ``Disconnect All`` disconnects all of the connected clients
by cancelling them.

Now, a few tricky aspects of this code.  First, control is managed by
the ``main()`` coroutine which runs under Curio.  The various server
tasks are spawned separately and the program enters a periodic update
loop in which the GUI is updated on timer every 50 milliseconds.
Since everything runs in the same thread, it's okay for coroutines to
perform operations that might update the display (e.g., directly
calling ``incr_clients()``).

Executing coroutines is a bit tricky though.  Since the GUI runs
outside of Curio, it's not able to run coroutines directly.  Thus, if
it's going to invoke a coroutine in response to an event such as a
button press, it has to handle it a bit differently.  In this case,
the coroutine is placed onto a list (``self.pending``) and processed
in the ``main()`` loop after pending GUI events have been updated.  
It looks a bit weird, but it basically works.

One issue with this approach is that might result in a sluggish or
glitchy GUI. Yes, events are processed on a periodic interval, but if
there's a lot action going on in the GUI, it might just feel "off" in
some way. Dealing with that in a single thread is going to be tricky.
You could invert the control flow by having the GUI call out to Curio
on a periodic timer.  However, that's just going to change the problem
into one of glitchy network performance.

Another possibility is to run the GUI and Curio in separate threads
and to have them communicate via queues.   Here's some code that
does that::

    import tkinter as tk
    from curio import *
    import threading

    class EchoApp(object):
        def __init__(self):
            self.gui_ops = UniversalQueue(withfd=True)
            self.coro_ops = UniversalQueue()

            # Main Tk window
            self.root = tk.Tk()

            # Number of clients connected label
            self.clients_label = tk.Label(text='')
            self.clients_label.pack()
            self.nclients = 0
            self.incr_clients(0)
            self.client_tasks = set()

            # Number of bytes received label
            self.bytes_received = 0
            self.bytes_label = tk.Label(text='')
            self.bytes_label.pack()
            self.update_bytes()

            # Disconnect all button
            self.disconnect_button = tk.Button(text='Disconnect all', 
                                               command=lambda: self.coro_ops.put(self.disconnect_all()))
            self.disconnect_button.pack()

            # Set up event handler for queued GUI updates
            self.root.createfilehandler(self.gui_ops, tk.READABLE, self.process_gui_ops)

        def incr_clients(self, delta=1):
            self.nclients += delta
            self.clients_label.configure(text='Number Clients %d' % self.nclients)            

        def update_bytes(self):
            self.bytes_label.configure(text='Bytes received %d' % self.bytes_received)
            self.root.after(1000, self.update_bytes)

        def process_gui_ops(self, file, mask):
            while not self.gui_ops.empty():
                func, args = self.gui_ops.get()
                func(*args)

        async def echo_client(self, sock, address):
            await self.gui_ops.put((self.incr_clients, (1,)))
            self.client_tasks.add(await current_task())
            try:
                async with sock:
                    while True:
                        data = await sock.recv(100000)
                        if not data:
                            break
                        self.bytes_received += len(data)
                        await sock.sendall(data)
            finally:
                self.client_tasks.remove(await current_task())
                await self.gui_ops.put((self.incr_clients, (-1,)))

        async def disconnect_all(self):
            for task in list(self.client_tasks):
                await task.cancel()

        async def main(self):
            serv = await spawn(tcp_server, '', 25000, self.echo_client)
            while True:
                coro = await self.coro_ops.get()
                await coro

        def run_forever(self):
            threading.Thread(target=run, args=(self.main(),)).start()
            self.root.mainloop()

    if __name__ == '__main__':
        app = EchoApp()
        app.run_forever()

In this code, there are two queues in use.  The ``gui_ops`` queue is
used to carry out updates on the GUI from Curio.  The
``echo_client()`` coroutine puts various operations on this queue.
The GUI listens to the queue by watching for I/O events.  This is a
bit sneaky, but Curio's ``UniversalQueue`` has an option that delivers
a byte on an I/O channel whenever an item is added to the queue. This,
in turn, can be used to wake an external event loop.  In this code,
the ``createfilehandler()`` call at the end of the ``__init__()`` sets
this up.

The ``coro_ops`` queue goes in the other direction. Whenever the GUI
wants to execute a coroutine, it places it on this queue. The
``main()`` coroutine receives and awaits these coroutines.


Programming Considerations and APIs
-----------------------------------

The use of ``async`` and ``await`` present new challenges in designing
libraries and APIs.  For example, asynchronous functions can't be
called outside of coroutines and weird things happen if you forget to
use ``await``.  Curio can't solve all of these problems, but it does
provide some metaprogramming features that might prove to be
interesting.   Many of these features are probably best described as
"experimental" so use them with a certain skepticism and caution.

A Moment of Zen
^^^^^^^^^^^^^^^

One of the most commonly cited rules of Python coding is that
"explicit is better than implicit."  Use of ``async`` and ``await``
embodies this idea--if you're using a coroutine, it is always called
using ``await``.  There is no ambiguity when reading the code.  
Moreover, ``await`` is only allowed inside functions defined using
``async def``.  So, if you see ``async`` or ``await``, you're
working with coroutines--end of story.

That said, there are still certain design challenges.  For example,
where are you actually allowed to define coroutines?  Functions?
Methods?  Special methods? Properties?   Also, what happens when
you start to mix normal functions and coroutines together?  For
example, suppose you have a class with a mix of methods like this::

    class Spam(object):
        async def foo():
             ...
        def bar():
             ...

Is this mix of a coroutine and non-coroutine methods in the class a
potential source of confusion to users?  It might be hard to say.
However, what happens if more advanced features such as inheritance
enter the picture and people screw it up? For example::

    class Child(Spam):
        def foo():        # Was a coroutine in Spam
            ...

Needless to say, this is the kind of thing that might keep you
up at night.  If you are writing any kind of large application
involving ``async`` and ``await`` you'll probably want to spend
some time carefully thinking about the big picture and how all
of the parts hold together.

Asynchronous Abstract Base Classes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose you wanted to enforce async-correctness in methods defined in 
a subclass.  Use ``AsyncABC`` as a base class. For example::

    from curio.meta import AsyncABC

    class Base(AsyncABC):
        async def spam(self):
            pass

If you inherit from ``Base`` and don't define ``spam()`` as an asynchronous
method, you'll get an error::

    class Child(Base):
        def spam(self):
            pass

    Traceback (most recent call last):
    ...
    TypeError: Must use async def spam(self)

The ``AsyncABC`` class is also a proper abstract base class so you can
use the usual ``@abstractmethod`` decorator on methods as well. For
example::

    from curio.meta import AsyncABC, abstractmethod

    class Base(AsyncABC):
        @abstractmethod
        async def spam(self):
            pass

Asynchronous Instance Creation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Normally, use of ``async`` and ``await`` is forbidden in the
``__init__()`` method of a class.  Honestly, you should probably try to
avoid asynchronous operations during instance creation, but if you
can't, there are two approaches.  First, you can define an
asynchronous class method::

    class Spam(object):
        @classmethod
        async def new(cls)
            self = cls.__new__(cls)
            self.val = await coro()
            ...
            return self

     # Example of creating an instance
     async def main():
          s = await Spam.new()
     
You'd need to custom-tailor the arguments to ``new()`` to your liking.
However, as an ``async`` function, you're free to use coroutines inside.

A second approach is to inherit from the Curio ``AsyncObject`` base class
like this::

    from curio.meta import AsyncObject
    class Spam(AsyncObject):
        async def __init__(self):
            self.val = await coro()
            ...

 
     # Example of creating an instance    
     async def main():
         s = await Spam()

This latter approach probably looks the most "pythonic" at the risk of
shattering your co-workers heads as they wonder what kind of
voodoo-magic you applied to the ``Spam`` class to make it support an
asynchronous ``__init__()`` method.  If you must know, that magic
involves metaclasses.  On that subject, the ``AsyncObject`` base uses
the same metaclass as ``AsyncABC``, enforces async-correctness in
subclasses, and allows abstract methods to be defined.

Asynchronous Instance Cleanup/Deletion
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You might be asking yourself if it's possible to put asynchronous
operations in the ``__del__()`` method of a class.  In short: it's
not possible (at least not using any technique that I'm aware of).
If you need to perform actions involving asynchronous operations on
cleanup, you should make your class operate as an asynchronous context
manager::

    class Spam(object):
        async def __aenter__(self):
            await coro()
            ...
        async def __aexit__(self, ty, val, tb):
            await coro()
            ...

Then, use your object using an ``async with`` statement like this::

    async def main():
        s = Spam()
        ...
        async with s:
            ...

If a context-manager is not appropriate, then your only other option
is to have an explicit shutdown/cleanup method defined as an async
function::

    class Spam(object):
        async def cleanup(self):
            await coro()
            ...

    async def main():
        s = Spam()
        try:
           ...
        finally:
           await s.cleanup()

Asynchronous Properties
^^^^^^^^^^^^^^^^^^^^^^^

It might come as a surprise, but normal Python properties can be defined
using asynchronous functions.  For example::

    class Spam(object):
        @property
        async def value(self):
            result = await coro()
            return result

    # Example usage
    async def main():
        s = Spam()
        ...
        v = await s.value

The property works as a read-only value as long as you preface any
access by an ``await``.  Again, you might shatter heads pulling a
stunt like this.

It does not seem possible to define asynchronous property setter or
deleter functions.   So, if you're going to drop ``async`` on a
property, keep in mind that it best needs to be read-only.

Blocking Functions
^^^^^^^^^^^^^^^^^^

Suppose you have a normal Python function that performs blocking
operations, but you'd like the function to be safely available to 
coroutines.  You can use the curio ``blocking`` decorator to do
this::

    from curio.meta import blocking

    @blocking
    def spam():
        ...
        blocking_op()
        ...

The interesting thing about ``@blocking`` is that it doesn't change
the usage of the function for normal Python code.  You call it the
same way you always have::

    def foo():
        s = spam()
  

In asynchronous code, you call the same function but add ``await`` like this::

    async def bar():
        s = await spam()

Behind the scenes, the blocking function is implicitly executed in a
separate thread using Curio's ``run_in_thread()`` function.

CPU-Intensive Functions
^^^^^^^^^^^^^^^^^^^^^^^

CPU-intensive operations performed by a coroutine will temporarily
suspend execution of all other tasks.   If you have such a function,
you can mark it as such using the ``@cpubound`` decorator.  For example::


    from curio.meta import cpubound

    @cpubound
    def spam():
        # Computationally expensive op
        ...
        return result

In normal Python code, you call this function the same way as before::

    def foo():
        s = spam()

In asynchronous code, you call the same function but add ``await`` like this::

    async def bar():
        s = await spam()

This will run the computationally intensive task in a separate process using
Curio's ``run_in_process()`` function.

Be aware that ``@cpubound`` makes a function execute in a separate
Python interpreter process.  It's only going to work correctly if that
function is free of side-effects and dependencies on global state.

Dual Synchronous/Asynchronous Function Implementation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose you wanted to have a function with both a synchronous and asynchronous
implementation.  You can use the ``@awaitable`` decorator for this::

    from curio.meta import awaitable

    def spam():
        print('Synchronous spam')

    @awaitable(spam)
    async def spam():
        print('Asynchronous spam')

The selection of the appropriate method now depends on execution context.
Here's an example of what happens in your code::

    def foo():
        spam()         # --> Synchronous spam

    async def bar():
        await spam()   # --> Asynchronous spam

If you're wondering how in the world this actually works, let's
just say it involves frame hacks.   Your list of enemies and
the difficulty of your next code review continues to grow.

Considerations for Function Wrapping and Inheritance
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Suppose that you have a simple async function like this::

    async def spam():
        print('spam')

Now, suppose you have another function that wraps around it::

    async def bar():
        print('bar')
        return await spam()

If you call ``bar()`` as a coroutine, it will work perfectly fine. 
For example::
 
    async def main():
        await bar()

However, here's a subtle oddity.  It turns out that you could drop
the ``async`` and ``await`` from the ``bar()`` function entirely
and everything will still work. For example::

     def bar():
         print('bar')
         return spam()

However, should you actually do this?  All things considered, I think it's
probably better to leave the ``async`` and ``await`` keywords in place.
It makes it more clear to the reader that the code exists in the world
of asynchronous programming.  This is something to think about as you
write larger applications--if you're using async, always define async functions.

Here is another odd example involving inheritance. Suppose you redefined
a method and used ``super()`` like this::

    class Parent(object):
        async def spam(self):
            print('Parent.spam')

    class Child(Parent):
        def spam(self):
            print('Child.spam')
            return super().spam()

It turns out that the ``spam()`` method of ``Child`` will work
perfectly fine, but it's just a little weird that it doesn't use
``async`` in the same way as the parent.  It would probably read
better written like this::

    class Child(Parent):
        async def spam(self):
            print('Child.spam')
            return await super().spam()

