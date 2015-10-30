Curio - A Tutorial Introduction
===============================

Curio is a modern library for performing reliable concurrent I/O using
Python coroutines and the explicit async/await syntax introduced in
Python 3.5.  Its programming model is based on common system
programming abstractions such as sockets, files, tasks, subprocesses,
locks, and queues.  It is an alternative to asyncio that is
implemented as a queuing system, not a callback-based event loop.

This tutorial will take you through the basics of creating and 
managing tasks in curio as well as some useful debugging features. 
Various I/O related features come a bit later.

Getting Started
---------------
Here is a simple curio hello world program--a task that prints a simple
countdown as you wait for your kid to put their shoes on::
 
    # hello.py
    import curio
    
    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(countdown(10))

Run it and you'll see a countdown.  Yes, some jolly fun to be
sure. Curio is based around the idea of tasks.  Tasks are functions
defined as coroutines using the ``async`` syntax.  To run a task, you
create a ``Kernel`` instance, then invoke the ``run()`` method with a
task.

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
        kid_task = await curio.new_task(kid())
        await curio.sleep(5)
        print("Let's go")
        count_task = await curio.new_task(countdown(10))
        await count_task.join()
        print("We're leaving!")
        await kid_task.join()
        print("Leaving")

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(parent())

This program illustrates the process of creating and joining with
tasks.  Here, the ``parent()`` task uses the ``curio.new_task()`` coroutine to 
launch a new child task.  After sleeping briefly, it then launches the
``countdown()`` task.  The ``join()`` method is used to wait for a task to
finish.  In this example, the parent first joins with ``countdown()`` and then
with ``kid()`` before leaving. If you run this program, you'll see it produce the
following output::

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

At this point, the program appears hung.  The child is sleeping for
the next 1000 seconds, the parent is blocked on ``join()`` and nothing
much seems to be happening--this is the mark of all good concurrent
programs.  Change the last part of the program to create the kernel
with the monitor enabled::

    ...
    if __name__ == '__main__':
        kernel = curio.Kernel(with_monitor=True)
        kernel.run(parent())

Run the program again. You'd really like to know what's happening?
Yes?  Press Ctrl-C to enter the curio monitor::

    ...
    We're leaving!
    ... hanging ...
    ^C
    Curio Monitor:  4 tasks running
    Type help for commands
    curio > 

Let's see what's happening by typing ``ps``::

    curio > ps
    Task   State        Cycles     Timeout Task                                               
    ------ ------------ ---------- ------- --------------------------------------------------
    1      READ_WAIT    2          None    Kernel._init_task                                 
    2      RUNNING      6          None    monitor                                           
    3      TASK_JOIN    5          None    parent                                            
    4      TIME_SLEEP   1          926.016 kid                                               

In the monitor, you can see a list of the active tasks.  You can see
that the parent is waiting to join and that the kid is sleeping for
another 926 seconds.  If you type ``ps`` again, you'll see the timeout
value change. Although you're in the monitor--the kernel is still
running underneath.  Actually, you'd like to know more about what's
happening. You can get the stack trace of any task using the ``where`` command::

    curio > where 3
     Stack for Task(id=3, <coroutine object parent at 0x1011bee60>, state='TASK_JOIN') (most recent call last):
      File "hello.py", line 22, in parent
        await kid_task.join()
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 74, in join
        await join_task(self, timeout)
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 538, in join_task
        yield '_trap_join_task', task, timeout
   
    curio > where 4
     Stack for Task(id=4, <coroutine object kid at 0x1013162b0>, state='TIME_SLEEP') (most recent call last):
      File "hello.py", line 13, in kid
        await curio.sleep(1000)
      File "/Users/beazley/Desktop/Projects/curio/curio/kernel.py", line 517, in sleep
        yield '_trap_sleep', seconds
    
    curio > 

Actually, that kid is just being super annoying.  Let's cancel their world and let the parent
get on with their business::

    curio > cancel 4
    Cancelling task 4
    Leaving!
    curio > 
    bash % 

Debugging is an important feature of curio and by using the monitor, you see what's happening as tasks run.
Can can find out where tasks are blocked and you can cancel any task that you want.
However, it's not necessary to do this in the monitor.  Change the parent task to include a timeout
and a cancellation request like this::

    async def parent():
        kid_task = await curio.new_task(kid())
        await curio.sleep(5)
        print("Let's go")
        count_task = await curio.new_task(countdown(10))
        await count_task.join()
        print("We're leaving!")
        try:
            await kid_task.join(timeout=10)
        except TimeoutError:
            print('I warned you!')
            await kid_task.cancel()
        print("Leaving!")

If you run this version, the parent will wait 10 seconds for the child to join.  If not, the child is
forcefully cancelled.  Problem solved. Now, if only real life were this easy.

Of course, all is not lost in the child.  If desired, they can catch the cancellation request
and cleanup. For example::

    async def kid():
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

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

By now, you should have the basic gist of the curio task model. You can create tasks, join tasks, and cancel tasks. 
Blocking operations (e.g., ``join()``) almost always have a timeout option.  You have a lot of control over how
things work.

Task Synchronization
--------------------

Tasks often need to synchronize.  For this purpose, curio provides
``Event``, ``Lock``, ``Semaphore``, and ``Condition`` objects.  For
example, let's introduce an event that makes the child wait for the
parent's permission to start playing::

    start_evt = curio.Event()

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

    async def parent():
        kid_task = await curio.new_task(kid())
        await curio.sleep(5)
        print("Yes, go play")
        await start_evt.set()
        await curio.sleep(5)
        print("Let's go")
        count_task = await curio.new_task(countdown(10))
        await count_task.join()
        print("We're leaving!")
        try:
            await kid_task.join(timeout=10)
        except TimeoutError:
            print('I warned you!')
            await kid_task.cancel()
        print("Leaving!")

All of the synchronization primitives work the same way that they do
in the ``threading`` module.  The main difference is that all operations
must be prefaced by ``await``. Thus, to set an event you use ``await
start_evt.set()`` and to wait for an event you use ``await
start_evt.wait()``. 

All of the synchronization methods also support timeouts. So, if the
kid wanted to be rather annoying, they could do use a timeout to
repeatedly nag like this::

    async def kid():
        while True:
	    try:
                print('Can I play?')
                await start_evt.wait(timeout=1)
                break
             except TimeoutError:
                pass
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

Signals
-------
What kind of parent only lets their child play Minecraft for 5
seconds?  Instead, let's have the parent allow the child to play as
much as they want until a Unix signal arrives.  Modify the code to
wait on a ``SignalSet`` like this::

    import signal, os

    async def parent():
        print('Parent PID', os.getpid())
        kid_task = await curio.new_task(kid())
        await curio.sleep(5)
        print("Yes, go play")
        await start_evt.set()
        
        await curio.SignalSet(signal.SIGHUP).wait()
     
        print("Let's go")
        count_task = await curio.new_task(countdown(10))
        await count_task.join()
        print("We're leaving!")
        try:
            await kid_task.join(timeout=10)
        except TimeoutError:
            print('I warned you!')
            await kid_task.cancel()
        print("Leaving!")

If you run this program, the parent lets the kid play 
indefinitely--well, until a ``SIGHUP`` arrives.  When you run the
program, you'll see this::

    bash % python3 hello.py
    Parent PID 36069
    Can I play?
    Yes, go play
    Building the Millenium Falcon in Minecraft

Don't forget, if you're wondering what's happening, you can always drop into
the curio monitor by pressing Control-C::

    ^C
    Curio Monitor:  4 tasks running
    Type help for commands
    curio > ps
    Task   State        Cycles     Timeout Task                                               
    ------ ------------ ---------- ------- --------------------------------------------------
    1      READ_WAIT    2          None    Kernel._init_task                                 
    2      RUNNING      6          None    monitor                                           
    3      SIGNAL_WAIT  5          None    parent                                            
    4      TIME_SLEEP   2          796.593 kid                                               
    curio > 

Here you see the parent waiting on a signal and the kid sleeping await for another 796 seconds.
If you want to initiate the signal, go to a separate terminal and type this::

    bash % kill -HUP 36069

Alternatively, you can initiate the signal by typing this in the monitor::

    curio > signal SIGHUP

In either case, you'll see the parent wake up, do the countdown and
proceed to cancel the child.  Very good.

Number Crunching and Blocking Operations
----------------------------------------
Now, suppose for a moment that the kid has decided that building the
Millenium Falcon requires computing a sum of larger and larger
Fibonacci numbers using an exponential algorithm like this::

    def fib(n):
        if n <= 2:
            return 1
        else:
            return fib(n-1) + fib(n-2)

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            total = 0
            for n in range(50):
                 total += fib(n)
        except curio.CancelledError:
            print('Fine. Saving my work.')

If you run this version, you'll find that the entire kernel becomes
unresponsive.  The monitor doesn't work, signals aren't caught, and
there appears to be no way to get control back.  The problem here is
that the kid is hogging the CPU and never yields.  Important lesson:
curio does not have a preemptive scheduler.  If a task decides to
go off and mine bitcoins, the entire kernel blocks until its done.

If you know that work might take awhile, you can have it execute in a
separate process. Change the code use ``curio.run_cpu_bound()`` like
this::

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            total = 0
            for n in range(50):
                total += await curio.run_cpu_bound(fib, n)
        except curio.CancelledError:
            print('Fine. Saving my work.')

In this version, the kernel remains fully responsive because the CPU
intensive work is being carried out elsewhere.  You should be able to
run the monitor, send the signal, and see the shutdown occur as before.

The problem of blocking might also apply to other operations involving
I/O.  For example, accessing a database or calling out to other
libraries.  In fact, any operation not preceded by an explicit
``await`` might block.  If you know that blocking is possible, use the
``curio.run_blocking()`` coroutine.
This arranges to have the computation
carried out in a separate thread. For example::

    import time

    async def kid():
        print('Can I play?')
        await start_evt.wait()
        try:
            print('Building the Millenium Falcon in Minecraft')
            total = 0
            for n in range(50):
                total += await curio.run_cpu_bound(fib, n)
		# Rest for a bit
		await curio.run_blocking(time.sleep, n)
        except curio.CancelledError:
            print('Fine. Saving my work.')
    
Note: ``time.sleep()`` has only been used to illustrate blocking in an outside
library. ``curio`` already has its own sleep function so if you really need to
sleep, use that instead.

A Simple Echo Server
--------------------

Now that you've got the basics down, let's look at some I/O. Here
is a simple echo server written directly with sockets using curio::

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
the services of the kernel is prefaced by ``await``.  

Carefully notice that we are using the module ``curio.socket`` instead
of the built-in ``socket`` module here.  Under the covers, ``curio.socket``
is actually just a wrapper around the existing ``socket`` module.  All
of the existing functionality of ``socket`` is available, but all of the
operations that might block have been replaced by coroutines and must be
preceded by an explicit ``await``. 

A lot of the code involving sockets is fairly repetitive.  Instead
of writing the server component, you can simplify the above example
by using ``run_server()`` like this::

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

Subprocesses
------------
Curio provides a wrapper around the ``subprocess`` module for launching subprocesses.
For example, suppose you wanted to write a task to watch the output of the ``ping``
command::

    from curio import subprocess
    import curio

    async def main():
        p = subprocess.Popen(['ping', 'www.python.org'], stdout=subprocess.PIPE)
        async for line in p.stdout:
            print('Got:', line.decode('ascii'), end='')

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(main())

In addition to ``Popen()``, you can also use higher level functions
such as ``subprocess.run()`` and ``subprocess.check_output()``.  For example::

    from curio import subprocess
    async def main():
        try:
            out = await subprocess.check_output(['netstat', '-a'])
        except subprocess.CalledProcessError as e:
            print('It failed!', e)

These functions operate exactly as they do in the normal
``subprocess`` module except that they're written on top of the
``curio`` kernel.  There is no blocking and no use of hidden threads.

Intertask Communication
-----------------------
If you have multiple tasks and want them to communicate, use a ``Queue``.
For example::

    # prodcons.py

    import curio

    async def producer(queue):
        for n in range(10):
            await queue.put(n)
        await queue.join()
        print('Producer done')

    async def consumer(queue):
        while True:
            item = await queue.get()
            print('Consumer got', item)
            await queue.task_done()

    async def main():
        q = curio.Queue()
        prod_task = await curio.new_task(producer(q))
        cons_task = await curio.new_task(consumer(q))
        await prod_task.join()
        await cons_task.cancel()

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.run(main())

Curio provides the same synchronization primitives as found in the built-in
``threading`` module.  The same techniques used by threads can be used with
curio.

Final Words
-----------
At this point, you should have enough of the concepts to get going. 
More information can be found in the reference manual.








    







