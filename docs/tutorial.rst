Curio - A Tutorial Introduction
===============================

Curio is a library for writing concurrent programs using Python
coroutines and the async/await syntax introduced in Python 3.5.  Its
programming model is based on existing programming abstractions
such as threads, sockets, files, locks, and queues.  Under the hood,
it's based on a task model that provides for advanced handling of
cancellation, interesting interactions between threads and processes,
and much more.  Plus, it's fun.

This tutorial will take you through the basics of using Curio
as well as some useful debugging features.

A Small Taste
-------------

For those who don't want to read, here is an example that implements a
simple echo server::

    from curio import run, spawn
    from curio.socket import *
    
    async def echo_server(address):
        sock = socket(AF_INET, SOCK_STREAM)
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
                 data = await client.recv(1000)
                 if not data:
                     break
                 await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(echo_server, ('',25000))

This server can handle thousands of concurrent clients.   It does
not use threads although it looks almost identical to a threaded
version.  This is a major feature of Curio--asynchronous
programs can be written in the same style as normal synchronous code.
Of course, there's are a number of other features.   If you keep
reading, this tutorial will introduce you to much more.

Getting Started
---------------

To start, we'll back up and talk about a simple hello world
program--in this case, a program that prints a countdown as you
wait for your kid to put their shoes on::
 
    # hello.py
    import curio
    
    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    if __name__ == '__main__':
        curio.run(countdown, 10)

Run it and you'll see a countdown.  Yes, some jolly fun to be
sure. Curio is based around the idea of tasks.  Tasks are 
defined as coroutines using ``async`` functions.  To make a task
execute, it must run inside the curio kernel.  The ``run()`` function
starts the kernel with an initial task.  The kernel runs until the 
supplied task returns.

Tasks
-----

Let's add a few more tasks into the mix::

    # hello.py
    import curio

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    async def kid():
        print('Building the Millenium Falcon in Minecraft')
        await curio.sleep(1000)

    async def parent():
        kid_task = await curio.spawn(kid)
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown, 10)
        await count_task.join()

        print("We're leaving!")
        await kid_task.join()
        print('Leaving')

    if __name__ == '__main__':
        curio.run(parent)

This program illustrates the process of creating and joining with
tasks.  Here, the ``parent()`` task uses the ``curio.spawn()``
coroutine to launch a new child task.  After sleeping briefly, it then
launches the ``countdown()`` task.  The ``join()`` method is used to
wait for a task to finish.  In this example, the parent first joins
with ``countdown()`` and then with ``kid()`` before trying to
leave. If you run this program, you'll see it produce the following
output::

    bash % python3 hello.py
    Building the Millenium Falcon in Minecraft
    Let's go
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    T-minus 6
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    We're leaving!
    .... hangs ....

At this point, the program appears hung.  The child is busy for
the next 1000 seconds, the parent is blocked on ``join()`` and nothing
much seems to be happening--this is the mark of all good concurrent
programs (hanging that is).  Change the last part of the program to
run the kernel with the monitor enabled::

    ...
    if __name__ == '__main__':
        curio.run(parent, with_monitor=True)

Run the program again. You'd really like to know what's happening?
Yes?  Open up another terminal window on the same machine and connect
to the monitor as follows::

    bash % python3 -m curio.monitor
    Curio Monitor: 4 tasks running
    Type help for commands
    curio >

See what's happening by typing ``ps``::

    curio > ps
    Task   State        Cycles     Timeout Sleep   Task                                               
    ------ ------------ ---------- ------- ------- --------------------------------------------------
    1      READ_WAIT    1          None    None    Kernel._make_kernel_runtime.<locals>._kernel_task 
    3      FUTURE_WAIT  1          None    None    Monitor.monitor_task                              
    4      TASK_JOIN    3          None    None    parent                                            
    5      TIME_SLEEP   1          None    984.554 kid  
    curio >

In the monitor, you can see a list of the active tasks.  You can see
that the parent is waiting to join and that the kid is sleeping.
Actually, you'd like to know more about what's happening. You can get
the stack trace of any task using the ``where`` command::

    curio > w 4
    Stack for Task(id=4, name='parent', state='TASK_JOIN') (most recent call last):
      File "hello.py", line 23, in parent
        await kid_task.join()
    curio > w 5
    Stack for Task(id=5, name='kid', state='TIME_SLEEP') (most recent call last):
      File "hello.py", line 12, in kid
        await curio.sleep(1000)
    curio >

Actually, that kid is just being super annoying.  Let's cancel their
world::

    curio > cancel 5
    Cancelling task 5
    *** Connection closed by remote host ***

This causes the whole program to die with a rather nasty traceback message similar to this::

    Traceback (most recent call last):
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 828, in _run_coro
        trap = current._throw(current.next_exc)
      File "/Users/beazley/Desktop/Projects/curio/curio/task.py", line 95, in _task_runner
        return await coro
      File "hello.py", line 12, in kid
        await curio.sleep(1000)
      File "/Users/beazley/Desktop/Projects/curio/curio/task.py", line 440, in sleep
        return await _sleep(seconds, False)
      File "/Users/beazley/Desktop/Projects/curio/curio/traps.py", line 80, in _sleep
        return (yield (_trap_sleep, clock, absolute))
    curio.errors.TaskCancelled: TaskCancelled

    The above exception was the direct cause of the following exception:

    Traceback (most recent call last):
      File "hello.py", line 27, in <module>
        curio.run(parent, with_monitor=True, debug=())
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 872, in run
        return kernel.run(corofunc, *args, timeout=timeout)
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 212, in run
        raise ret_exc
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 825, in _run_coro
        trap = current._send(current.next_value)
      File "/Users/beazley/Desktop/Projects/curio/curio/task.py", line 95, in _task_runner
        return await coro
      File "hello.py", line 23, in parent
        await kid_task.join()
      File "/Users/beazley/Desktop/Projects/curio/curio/task.py", line 108, in join
        raise TaskError('Task crash') from self.next_exc
    curio.errors.TaskError: Task crash

Not surprisingly, the parent sure didn't like having their child
process abruptly killed out of nowhere like that.  The ``join()``
method returned with a ``TaskError`` exception to indicate that some
kind of problem occurred in the child.

Debugging is an important feature of curio and by using the monitor,
you see what's happening as tasks run.  You can find out where tasks
are blocked and you can cancel any task that you want.  However, it's
not necessary to do this in the monitor.  Change the parent task to
include a timeout and some debugging print statements like this::

    async def parent():
        kid_task = await curio.spawn(kid)
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown, 10)
        await count_task.join()

        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join)
        except curio.TaskTimeout:
            print('Where are you???')
            print(kid_task.traceback())
	    raise SystemExit()
        print('Leaving!')

If you run this version, the parent will wait 10 seconds for the child
to join.  If not, a debugging traceback for the child task is printed
and the program quits.  Use the ``traceback()`` method of a task to create a
traceback string.  Raising ``SystemExit()`` causes Curio to quit in the same
manner as normal Python programs.

The parent could also elect to forcefully cancel the child.  Change
the program so that it looks like this::

    async def parent():
        kid_task = await curio.spawn(kid)
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown, 10)
        await count_task.join()

        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join)
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print('Leaving!')

Of course, all is not lost in the child.  If desired, they can catch
the cancellation request and cleanup. For example::

    async def kid():
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')
	    raise

Now your program should produce output like this::

    bash % python3 hello.py
    Building the Millenium Falcon in Minecraft
    Let's go
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    T-minus 6
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    We're leaving!
    I warned you!
    Fine. Saving my work.
    Leaving!

By now, you have the basic gist of the curio task model. You can
create tasks, join tasks, and cancel tasks.  Even if a task appears to
be blocked for a long time, it can be cancelled by another task or a
timeout. You have a lot of control over the environment.

Task Groups
-----------

What kind of kid plays Minecraft alone?  Of course, they're going to invite
all of their school friends over.  Change the ``kid()`` function like this::

    async def friend(name):
        print('Hi, my name is', name)
        print('Playing Minecraft')
        try:
            await curio.sleep(1000)
        except curio.CancelledError:
            print(name, 'going home')
            raise

    async def kid():
        print('Building the Millenium Falcon in Minecraft')

        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                await curio.sleep(1000)
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

In this code, the kid creates a task group and spawns a collection of
tasks into it.  Now you've got a four-fold problem of tasks sitting
around doing nothing useful.  You'd think the parent might have a problem
with a motley crew like this, but no. If you run the code again,
you'll get output like this::

    Building the Millenium Falcon in Minecraft
    Hi, my name is Max
    Playing Minecraft
    Hi, my name is Lillian
    Playing Minecraft
    Hi, my name is Thomas
    Playing Minecraft
    Let's go
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    T-minus 6
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    We're leaving!
    I warned you!
    Fine. Saving my work.
    Max going home
    Lillian going home
    Thomas going home
    Leaving!

Carefully observe how all of those friends just magically went
away. That's the defining feature of a ``TaskGroup``. You can spawn
tasks into a group and they will either all complete or they'll all
get cancelled if any kind of error occurs. Either way, none of those
tasks are executing when control-flow leaves the with-block.  In this
case, the cancellation of ``child()`` causes a cancellation to
propagate to all of those friend tasks who promptly leave.  Again,
problem solved.  

This kind of task control is an example of a programming style known
as "structured concurrency."  It's supported by Curio, but it's not
required if it doesn't apply to the problem being solved.

Task Synchronization
--------------------

Although threads are not used to implement curio, you still might have
to worry about task synchronization issues (e.g., if more than one
task is working with mutable state).  For this purpose, curio provides
``Event``, ``Lock``, ``Semaphore``, and ``Condition`` objects.  For
example, let's introduce an event that makes the child wait for the
parent's permission to start playing::

    start_evt = curio.Event()

    async def kid():
        print('Can I play?')
        await start_evt.wait()

        print('Building the Millenium Falcon in Minecraft')

        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                await curio.sleep(1000)
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

    async def parent():
        kid_task = await curio.spawn(kid)
        await curio.sleep(5)

        print('Yes, go play')
        await start_evt.set()
        await curio.sleep(5)

        print("Let's go")
        count_task = await curio.spawn(countdown, 10)
        await count_task.join()

        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join)
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print('Leaving!')

All of the synchronization primitives work the same way that they do
in the ``threading`` module.  The main difference is that all operations
must be prefaced by ``await``. Thus, to set an event you use ``await
start_evt.set()`` and to wait for an event you use ``await
start_evt.wait()``. 

All of the synchronization methods also support timeouts. So, if the
kid wanted to be rather annoying, they could use a timeout to
repeatedly nag like this::


    async def kid():
        while True:
            try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait)
                break
            except curio.TaskTimeout:
                print('Wha!?!')

        print('Building the Millenium Falcon in Minecraft')

        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                await curio.sleep(1000)
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

Signals
-------

What kind of screen-time obsessed helicopter parent lets their child
and friends play Minecraft for a measly 5 seconds?  Instead, let's
have the parent allow the child to play as much as they want until a
signal arrives, indicating that it's time to go.  Modify the code
to wait for Control-C (``SIGINT``) or a ``SIGTERM`` using a ``SignalEvent`` like
this::

    import signal

    async def parent():
        goodbye = curio.SignalEvent(signal.SIGINT, signal.SIGTERM)

        kid_task = await curio.spawn(kid)
        await curio.sleep(5)

        print('Yes, go play')
        await start_evt.set()
        
        await goodbye.wait()
     
        print("Let's go")
        count_task = await curio.spawn(countdown, 10)
        await count_task.join()
        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join)
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print('Leaving!')

If you run this program, you'll get output like this::

    Building the Millenium Falcon in Minecraft
    Hi, my name is Max
    Playing Minecraft
    Hi, my name is Lillian
    Playing Minecraft
    Hi, my name is Thomas
    Playing Minecraft

At this point, nothing is going to happen for awhile. The kids
will play for the next 1000 seconds.  However,
if you press Control-C, you'll see the program initiate it's
usual shutdown sequence::

    ^C    (Control-C)
    Let's go
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    T-minus 6
    T-minus 5
    T-minus 4
    T-minus 3
    T-minus 2
    T-minus 1
    We're leaving!
    I warned you!
    Fine. Saving my work.
    Max going home
    Lillian going home
    Thomas going home
    Leaving!

In either case, you'll see the parent wake up, do the countdown and
proceed to cancel the child.  All the friends go home. Very good.

Signals are a weird affair though.   Suppose that the parent discovers
that the house is on fire and wants to get the kids out of there fast.  As
written, a ``SignalEvent`` captures the appropriate signal and sets 
a sticky flag.  If the same signal comes in again, nothing much happens.
In this code, the shutdown sequence would run to completion no matter
how many times you hit Control-C.  Everyone dies. Sadness.

This problem is easily solved--just delete the event after you're done with it.  
Like this::

    async def parent():
        goodbye = curio.SignalEvent(signal.SIGINT, signal.SIGTERM)

        kid_task = await curio.spawn(kid)
        await curio.sleep(5)

        print('Yes, go play')
        await start_evt.set()
        
        await goodbye.wait()
        del goodbye             # Removes the Control-C handler
     
        print("Let's go")
        count_task = await curio.spawn(countdown, 10)
        await count_task.join()
        print("We're leaving!")
        try:
            await curio.timeout_after(10, kid_task.join)
        except curio.TaskTimeout:
            print('I warned you!')
            await kid_task.cancel()
        print('Leaving!')

Run the program again.   Now, quickly hit Control-C twice in a row.
Boom! Minecraft dies instantly and everyone hurries their way out
of there.  You'll see the friends, the child, and the parent all
making a hasty exit.


Number Crunching and Blocking Operations
----------------------------------------

Now, suppose for a moment that the kid has discovered that the shape
of the Millenium Falcon is based on the Golden Ratio and that building
it now requires computing a sum of larger and larger Fibonacci numbers
using an exponential algorithm like this::

    def fib(n):
        if n < 2:
            return 1
        else:
            return fib(n-1) + fib(n-2)

    async def kid():
        while True:
            try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait)
                break
            except curio.TaskTimeout:
                print('Wha!?!')

        print('Building the Millenium Falcon in Minecraft')
        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                total = 0
                for n in range(50):
                    total += fib(n)
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

If you run this version, you'll find that the entire kernel becomes
unresponsive.  For example, signals aren't caught and there appears to
be no way to get control back.  The problem here is that the kid is
hogging the CPU and never yields.  Important lesson: async DOES NOT
provide preemptive scheduling. If a task decides to compute large
Fibonacci numbers or mine bitcoins, everything will block until it's
done. Don't do that.

If you're trying to debug a situation like this, the good news is that
you can still use the Curio monitor to find out what's happening.  The
monitor is written to operate concurrently with Curio and can still
tell you useful things even if everything else appears to be deadlocked.
For example, you could start a separate terminal window and type this::

    bash % python3 -m curio.monitor

    Curio Monitor: 7 tasks running
    Type help for commands
    curio > ps
    Task   State        Cycles     Timeout Sleep   Task                                               
    ------ ------------ ---------- ------- ------- --------------------------------------------------
    1      FUTURE_WAIT  1          None    None    Monitor.monitor_task                              
    2      READ_WAIT    1          None    None    Kernel._run_coro.<locals>._kernel_task            
    3      FUTURE_WAIT  2          None    None    parent                                            
    4      RUNNING      6          None    None    kid                                               
    5      READY        0          None    None    friend                                            
    6      READY        0          None    None    friend                                            
    7      READY        0          None    None    friend                                            
    curio > w 4
    Stack for Task(id=4, name='kid', state='RUNNING') (most recent call last):
      File "hello.py", line 44, in kid
        total += fib(n)

    curio >

The bad news is that if you want other tasks to run, you'll have to
figure out some other way to carry out computationally intensive work.
If you know that the work might take awhile, you can have it execute
in a separate process. Change the code to use
``curio.run_in_process()`` like this::

    async def kid():
        while True:
            try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait)
                break
            except curio.TaskTimeout:
                print('Wha!?!')

        print('Building the Millenium Falcon in Minecraft')
        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                total = 0
                for n in range(50):
                    total += await curio.run_in_process(fib, n)
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

In this version, the kernel remains fully responsive because the CPU
intensive work is being carried out in a subprocess. You should be
able to run the monitor, send the signal, and see the shutdown occur
as before. 

The problem of blocking might also apply to operations involving
I/O.  For example, suppose your kid starts hanging out with a bunch of
savvy 5th graders who are into microservices. Suddenly, the
``kid()`` task morphs into something that's making HTTP requests and
decoding JSON::

    import requests

    async def kid():
        while True:
            try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait)
                break
            except curio.TaskTimeout:
                print('Wha!?!')

        print('Building the Millenium Falcon in Minecraft')
        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                total = 0
                for n in range(50):
                    r = requests.get(f'http://www.dabeaz.com/cgi-bin/fib.py?n={n}')
		    resp = r.json()
                    total += int(resp['value'])
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

That's great except that the popular ``requests`` library knows
nothing of Curio and it blocks the internal event loop while waiting
for a response.  This is essentially the same problem as before except
that ``requests.get()`` mainly spends its time waiting. For this, 
you can use ``curio.run_in_thread()`` to offload work to a separate thread.  
Modify the code like this::

    import requests

    async def kid():
        while True:
            try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait)
                break
            except curio.TaskTimeout:
                print('Wha!?!')

        print('Building the Millenium Falcon in Minecraft')
        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                total = 0
                for n in range(50):
                    r = await curio.run_in_thread(requests.get,
                                                  f'http://www.dabeaz.com/cgi-bin/fib.py?n={n}')
		    resp = r.json()
                    total += int(resp['value'])
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

You'll find that this version works.  All of the tasks run, you can
send signals, and it's responsive.

Curiouser and Curiouser
-----------------------

Like actual kids, as much as you tell tasks to be responsible, you can
never be quite sure that they’re going to do the right thing in all
circumstances. The previous section on blocking operations illustrates
a problem that lurks in the shadows of any async program–-namely the
lack of task preemption and the risk of blocking the internal event
loop without even knowing it. Potentially any operation not involving
an explict ``await`` is suspect.  However, it's really up to you to
know more about the nature of what's being done and to explicitly use
calls such as ``run_in_thread()`` or ``run_in_process()`` as
appropriate.

There is another approach however.   Rewrite the ``fib()`` function and
``kid()`` task as follows::

    @curio.async_thread
    def fib(n):
        r = requests.get(f'http://www.dabeaz.com/cgi-bin/fib.py?n={n}')
        resp = r.json()
        return int(resp['value'])

    async def kid():
        while True:
            try:
                print('Can I play?')
                await curio.timeout_after(1, start_evt.wait)
                break
            except curio.TaskTimeout:
                print('Wha!?!')

        print('Building the Millenium Falcon in Minecraft')
        async with curio.TaskGroup() as f:
            await f.spawn(friend, 'Max')
            await f.spawn(friend, 'Lillian')
            await f.spawn(friend, 'Thomas')
            try:
                total = 0
                for n in range(50):
                    total += await fib(n)
            except curio.CancelledError:
                print('Fine. Saving my work.')
                raise

In this code, the ``kid()`` task uses ``await fib()`` to call the
``fib()`` function. It looks like you're calling a coroutine, but in
reality, it's launching a background thread and running the function
in that.  Since it's a separate thread, blocking operations aren't
going to block the rest of Curio.   In fact, you'll find that the example
works the same as it did before.

Functions marked with ``@async_thread`` are also unusual in that they
can be called from normal synchronous code as well.  For example, you could
launch an interactive interpreter and do this::

    >>> fib(5)
    8
    >>>

In this case, there is no need to launch a background thread--the function
simply runs as it normally would.    Yes, you just used the same function
from async (with ``await``) and from normal synchronous code at the REPL. 

There's more than meets the eye when it comes to Curio and threads. However,
Curio provides a number of features for making coroutines and threads
play nicely together.  This is only a small taste.

A Simple Echo Server
--------------------

Now that you've got the basics down, let's look at some I/O. Perhaps
the main use of Curio is in network programming.  Here is a simple
echo server written directly with sockets using curio::

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
                 data = await client.recv(1000)
                 if not data:
                     break
                 await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(echo_server, ('',25000))

Run this program and try connecting to it using a command such as ``nc``
or ``telnet``.  You'll see the program echoing back data to you.  Open
up multiple connections and see that it handles multiple client
connections perfectly well::

    bash % nc localhost 25000
    Hello                 (you type)
    Hello                 (response)
    Is anyone there?      (you type)
    Is anyone there?      (response)
    ^C
    bash %
    
If you've written a similar program using sockets and threads, you'll
find that this program looks nearly identical except for the use of
``async`` and ``await``.  Any operation that involves I/O, blocking, or
the services of Curio is prefaced by ``await``.  

Carefully notice that we are using the module ``curio.socket`` instead
of the built-in ``socket`` module here.  ``curio.socket``
is a wrapper around the existing ``socket`` module.  All
of the existing functionality of ``socket`` is available, but all of the
operations that might block have been replaced by coroutines and must be
preceded by an explicit ``await``. 

The use of an asynchronous context manager might be something new.  For
example, you'll notice the code uses this::

    async with sock:
        ...

Normally, a context manager takes care of closing a socket when you're
done using it.  The same thing happens here.  However, because you're
operating in an environment of cooperative multitasking, you should
use the asynchronous variant instead.   As a general rule, all I/O
related operations in curio will use the ``async`` form.

A lot of the above code involving sockets is fairly repetitive.  Instead
of writing the part that sets up the server, you can simplify the above example
using ``tcp_server()`` like this::

    from curio import run, spawn, tcp_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        while True:
            data = await client.recv(1000)
            if not data:
                break
            await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server, '', 25000, echo_client)

The ``tcp_server()`` coroutine takes care of a few low-level details
such as creating the server socket and binding it to an address.  It
also takes care of properly closing the client socket so you no longer
need the extra ``async with client`` statement from before.  Clients
are also launched into a proper task group so cancellation of the
server shuts everything down just like the kid's friends in the
earlier example.

A Stream-Based Echo Server
--------------------------

In certain cases, it might be easier to work with a socket connection
using a file-like stream interface.  Here is an example::

    from curio import run, spawn, tcp_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        s = client.as_stream()
        while True:
            data = await s.read(1000)
            if not data:
                break
            await s.write(data)
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server, '', 25000, echo_client)

The ``socket.as_stream()`` method can be used to wrap the socket in a
file-like object for reading and writing.  On this object, you would
now use standard file methods such as ``read()``, ``readline()``, and
``write()``.  One feature of a stream is that you can easily read data
line-by-line using an ``async for`` statement like this::

    from curio import run, spawn, tcp_server

    async def echo_client(client, addr):
        print('Connection from', addr)
        s = client.as_stream()
        async for line in s:
            await s.write(line)
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server, '', 25000, echo_client)

This is potentially useful if you're writing code to read HTTP headers or
some similar task.

A Managed Echo Server
---------------------

Let's make a slightly more sophisticated echo server that responds
to a Unix signal and gracefully restarts::

    import signal
    from curio import run, spawn, SignalQueue, CancelledError, tcp_server
    from curio.socket import *

    async def echo_client(client, addr):
        print('Connection from', addr)
        s = client.as_stream()
        try:
            async for line in s:
                await s.write(line)
        except CancelledError:
            await s.write(b'SERVER IS GOING AWAY!\n')
            raise
	print('Connection closed')

    async def main(host, port):
        async with SignalQueue(signal.SIGINT) as restart:
            while True:
                print('Starting the server')
                serv_task = await spawn(tcp_server, host, port, echo_client)
                await restart.get()
                print('Server shutting down')
                await serv_task.cancel()

    if __name__ == '__main__':
        run(main('', 25000))

In this code, the ``main()`` coroutine launches the server, but then
waits for the arrival of a ``SIGINT`` (Control-C) signal (note: on Unix it would be
more common to use ``SIGHUP`` for this, but ``SIGINT`` works on all platforms so
it's being used here to illustrate).  When received, it
cancels the server.  Behinds the scenes, the server has spawned all children into
a task group, all active children also get cancelled and print a
"server is going away" message back to their clients. Just to be clear,
if there were a 1000 connected clients at the time the restart occurs,
the server would drop all 1000 clients at once and start fresh with no
active connections.

The use of a ``SignalQueue`` here is useful if you want to respond to
a signal more than once. Instead of merely setting a flag like an event,
each occurrence of a signal is queued.  Use the ``get()`` method to get the
signals as they arrive.

Intertask Communication
-----------------------

If you have multiple tasks and want them to communicate, use a ``Queue``.
For example, here's a program that builds a little publish-subscribe service
out of a queue, a dispatcher task, and publish function::


    from curio import run, TaskGroup, Queue, sleep

    messages = Queue()
    subscribers = set()

    # Dispatch task that forwards incoming messages to subscribers
    async def dispatcher():
        async for msg in messages:
            for q in list(subscribers):
                await q.put(msg)

    # Publish a message
    async def publish(msg):
        await messages.put(msg)

    # A sample subscriber task
    async def subscriber(name):
        queue = Queue()
        subscribers.add(queue)
        try:
            async for msg in queue:
                print(name, 'got', msg)
        finally:
            subscribers.discard(queue)

    # A sample producer task
    async def producer():
        for i in range(10):
            await publish(i)
            await sleep(0.1)

    async def main():
        async with TaskGroup() as g:
            await g.spawn(dispatcher)
            await g.spawn(subscriber, 'child1')
            await g.spawn(subscriber, 'child2')
            await g.spawn(subscriber, 'child3')
            ptask = await g.spawn(producer)
            await ptask.join()
            await g.cancel_remaining()

    if __name__ == '__main__':
        run(main)

Curio provides the same synchronization primitives as found in the built-in
``threading`` module.  The same techniques used by threads can be used with
Curio.  All things equal though, prefer to use queues if you can.

A Chat Server
-------------

Let's put more of our tools into practice and implement a chat server.  This
server combines a bit of network programming with the publish-subscribe
system you just built.  Here it is::

    # chat.py

    import signal
    from curio import run, spawn, SignalQueue, TaskGroup, Queue, tcp_server, CancelledError
    from curio.socket import *

    messages = Queue()
    subscribers = set()

    async def dispatcher():
        async for msg in messages:
            for q in subscribers:
                await q.put(msg)

    async def publish(msg):
        await messages.put(msg)

    # Task that writes chat messages to clients
    async def outgoing(client_stream):
        queue = Queue()
        try:
            subscribers.add(queue)
            async for name, msg in queue:
                await client_stream.write(name + b':' + msg)
        finally:
            subscribers.discard(queue)

    # Task that reads chat messages and publishes them
    async def incoming(client_stream, name):
        try:
            async for line in client_stream:
                await publish((name, line))
        except CancelledError:
            await client_stream.write(b'SERVER IS GOING AWAY!\n')
            raise

    # Supervisor task for each connection
    async def chat_handler(client, addr):
        print('Connection from', addr) 
        async with client:
            client_stream = client.as_stream()
            await client_stream.write(b'Your name: ')
            name = (await client_stream.readline()).strip()
            await publish((name, b'joined\n'))

            async with TaskGroup(wait=any) as workers:
                await workers.spawn(outgoing, client_stream)
                await workers.spawn(incoming, client_stream, name)

            await publish((name, b'has gone away\n'))

        print('Connection closed')

    async def chat_server(host, port):
        async with TaskGroup() as g:
            await g.spawn(dispatcher)
            await g.spawn(tcp_server, host, port, chat_handler)

    async def main(host, port):
        async with SignalQueue(signal.SIGINT) as restart:
            while True:
                print('Starting the server')
                serv_task = await spawn(chat_server, host, port)
                await restart.get()
                print('Server shutting down')
                await serv_task.cancel()

    if __name__ == '__main__':
        run(main('', 25000))

This code might take a bit to digest, but here are some important bits.
Each connection results into two tasks being spawned (``incoming`` and 
``outgoing``).  The ``incoming`` task reads incoming lines and publishes
them.  The ``outgoing`` task subscribes to the feed and sends outgoing
messages.   The ``workers`` task group supervises these two tasks. If any
one of them terminates, the other task is cancelled right away.

The ``chat_server`` task launches both the ``dispatcher`` and a ``tcp_server``
task and watches them.  If cancelled, both of those tasks will be shut down.
This includes all active client connections (each of which will get a 
"server is going away" message).  

Spend some time to play with this code.   Allow clients to come and go.
Send the server a ``SIGHUP`` and watch it drop all of its clients.
It's neat.

Programming Advice
------------------

At this point, you should have enough of the core concepts to get going. 
Here are a few programming tips to keep in mind:

- When writing code, think thread programming and synchronous code.
  Tasks execute like threads and would need to be synchronized in much
  the same way.  However, unlike threads, tasks can only be preempted
  on statements that explicitly use ``await`` or ``async``.

- Curio uses the same I/O abstractions that you would use in normal
  synchronous code (e.g., sockets, files, etc.).  Methods have the
  same names and perform the same functions.  However, all operations
  that potentially involve I/O or blocking will always be prefaced by an
  explicit ``await`` keyword.  

- Be extra wary of any library calls that do not use an explicit
  ``await``.  Although these calls will work, they could potentially
  block the kernel on I/O or long-running calculations.  If you know
  that either of these are possible, consider the use of the
  ``run_in_process()`` or ``run_in_thread()`` functions to execute the work.

Debugging Tips
--------------

A common programming mistake is to forget to use ``await``.  For example::

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            curio.sleep(5)        # Missing await
            n -= 1

This will usually result in a warning message::
   
    example.py:8: RuntimeWarning: coroutine 'sleep' was never awaited

For debugging a program that is otherwise running, but you're not
exactly sure what it might be doing (perhaps it's hung or deadlocked),
consider the use of the curio monitor.  For example::

    import curio
    ...
    run(..., with_monitor=True)

The monitor can show you the state of each task and you can get stack 
traces. Remember that you enter the monitor by running ``python3 -m curio.monitor``
in a separate window.

You can also turn on scheduler tracing with code like this::

    from curio.debug import schedtrace
    import logging
    logging.basicConfig(level=logging.DEBUG)
    run(..., debug=schedtrace)

This will write log information about the scheduling of tasks.  If you want even
more fine-grained information, you can enable trap tracing using this::

    from curio.debug import traptrace
    import logging
    logging.basicConfig(level=logging.DEBUG)
    run(..., debug=traptrace)

This will write a log of every low-level operation being performed by the kernel.

More Information
----------------

The official Github page at https://github.com/dabeaz/curio should be used for bug reports,
pull requests, and other activities. 

A reference manual can be found at https://curio.readthedocs.io/en/latest/reference.html.

A more detailed developer's guide can be found at https://curio.readthedocs.io/en/latest/devel.html.

See the HowTo guide at https://curio.readthedocs.io/en/latest/howto.html for more tips and
techniques.















    







