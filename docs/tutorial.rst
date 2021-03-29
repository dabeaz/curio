A Tutorial Introduction
=======================

Curio is a library for concurrent systems programming that uses
coroutines and common programming abstractions such as threads,
sockets, files, locks, and queues. In addition, it supports
cancellation, task groups, and other useful features.  This tutorial
describes the basics of the concurrency model.  Consult the
"howto" guide at https://curio.readthedocs.io/en/latest/howto.html for
cookbook-style coding recipes.

Getting Started
---------------

Consider this program that prints a countdown::
 
    # hello.py
    import curio
    
    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    if __name__ == '__main__':
        curio.run(countdown, 10)

Curio executes ``async`` functions (or coroutine functions). To run a
program, you provide an initial function and arguments to
``run()``.  When it completes, ``run()`` returns the result.

Tasks and Concurrency
---------------------

This program does two things at once::

    # hello.py
    import curio

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    async def kid(x, y):
        print('Getting around to doing my homework')
        await curio.sleep(1000)
        return x * y

    async def parent():
        kid_task = await curio.spawn(kid, 37, 42)
        count_task = await curio.spawn(countdown, 10)

	await count_task.join()

        print("Are you done yet?")
        result = await kid_task.join()

        print("Result:", result)

    if __name__ == '__main__':
        curio.run(parent)

``curio.spawn()`` launches a concurrent task. The ``join()`` method waits
for it to finish and returns its result. The following output is produced::

    bash % python3 hello.py
    Getting around to doing my homework
    T-minus 10
    T-minus 9
    ...
    T-minus 2
    T-minus 1
    Are you done yet?
    .... hangs ....

At this point, the child is busy for the next 990 seconds, the parent
is blocked on ``join()`` and nothing seems to be happening. Change
``run()`` to enable the monitor::

    if __name__ == '__main__':
        curio.run(parent, with_monitor=True)

Re-run the program and launch the monitor in a separate window::

    bash % python3 -m curio.monitor
    Curio Monitor: 4 tasks running
    Type help for commands
    curio >

Type ``ps`` to view the status of each task::

    curio > ps
    Task   State        Cycles     Timeout Sleep   Task                                               
    ------ ------------ ---------- ------- ------- --------------------------------------------------
    1      READ_WAIT    1          None    None    Kernel._make_kernel_runtime.<locals>._kernel_task 
    3      FUTURE_WAIT  1          None    None    Monitor.monitor_task                              
    4      TASK_JOIN    2          None    None    parent                                            
    5      TIME_SLEEP   1          None    970.186 kid                                               
    curio > 

Here, you see the parent waiting to join and the kid sleeping.
Use the ``where`` command to get a stack trace::

    curio > w 4
    Stack for Task(id=4, name='parent', state='TASK_JOIN') (most recent call last):
      File "hello.py", line 24, in parent
        result = await kid_task.join()
    curio > w 5
    Stack for Task(id=5, name='kid', state='TIME_SLEEP') (most recent call last):
      File "hello.py", line 14, in kid
        await curio.sleep(1000)
    curio >

A timeout can be applied to any operation and tasks can be cancelled. Change the program as follows::

    async def parent():
        kid_task = await curio.spawn(kid, 37, 42)
        count_task = await curio.spawn(countdown, 10)

        await count_task.join()

        print("Are you done yet?")
        try:
            result = await curio.timeout_after(10, kid_task.join)
            print("Result:", result)
        except curio.TaskTimeout as e:
            print("We've got to go!")
            await kid_task.cancel()

Likewise, cancellation can be caught. For example::

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            await curio.sleep(1000)
            return x * y
        except curio.CancelledError:
            print("No go diggy die!")
            raise

Now the program produces this output::

    bash % python3 hello.py
    Getting around to doing my homework
    T-minus 10
    T-minus 9
    ...
    T-minus 2
    T-minus 1
    Are you done yet?
    We've got to go!
    No go diggy die!
   bash %

This is the basic gist of tasks. You can create
tasks, join tasks, and cancel tasks.  

Task Groups
-----------

Suppose you want the ``countdown`` and ``kid`` tasks to have a race.
That is, have them run concurrently, but whichever
one finishes first wins--cancelling the other task.  This kind of coordination
is handled by a ``TaskGroup``.  Change the ``parent()`` function to this::

    async def parent():
        async with curio.TaskGroup(wait=any) as g:
            await g.spawn(kid, 37, 42)
            await g.spawn(countdown, 10)

        if g.result is None:
            print("Why didn't you finish?")
        else:
            print("Result:", g.result)

Here, a task group waits for any spawned task to finish (the
``wait=any`` argument). When this occurs, the losing task is
cancelled.  The ``result`` attribute of the group contains the result
of the task that won.

Running this code, you will either get output similar to this::

    Getting around to doing my homework
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    Result: 1554

or you will get this if the ``kid()`` took too long::

    Getting around to doing my homework
    T-minus 10
    T-minus 9
    ...
    T-minus 2
    T-minus 1
    No go diggy die!
    Why didn't you finish?

A critical feature of a task group is that all created tasks will have
completed or been cancelled when control-flow leaves the managed
block--no child left behind. 

Long-Running Operations
-----------------------

Suppose that ``kid()`` involves an inefficient computation
of Fibonacci numbers::

    def fib(n):
        if n < 2:
            return 1
        else:
            return fib(n-1) + fib(n-2)

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            return fib(x) * fib(y)
        except curio.CancelledError:
            print("No go diggy die!")
            raise

    async def parent():
        async with curio.TaskGroup(wait=any) as g:
            await g.spawn(kid, 37, 42)
            await g.spawn(countdown, 10)

        if g.result is None:
            print("Why didn't you finish?")
        else:
            print("Result:", g.result)

    if __name__ == '__main__':
        curio.run(parent, with_monitor=True)

If you run this version, everything becomes unresponsive and you
see no output. The problem is that ``fib()`` takes over the CPU and
never yields.  Important lesson: Curio DOES NOT provide preemptive
scheduling. If a task decides to compute large Fibonacci numbers or
mine bitcoins, everything blocks. Don't do that.

For other tasks to make progress, you must modify ``kid()`` to carry
out computationally intensive work elsewhere.  Change the code to use
``curio.run_in_process()``::

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            fx = await curio.run_in_process(fib, x)
            fy = await curio.run_in_process(fib, y)
            return fx * fy
        except curio.CancelledError:
            print("No go diggy die!")
            raise

With this change, you'll see the countdown task running and
the kid task is cancelled if it takes too long (you might need
to greatly increase the countdown duration).  Coincidentally, you
execute the two ``fib()`` calculations in parallel on two CPUs using
``spawn()`` like this::

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            async with curio.TaskGroup() as g:
                tx = await g.spawn(curio.run_in_process, fib, x)
                ty = await g.spawn(curio.run_in_process, fib, y)
            return tx.result * ty.result
        except curio.CancelledError:
            print("Guess I'll fail!")
            raise

The blocking problem also applies to I/O operations. For
example, suppose ``kid()`` was modified to use a Fibonacci microservice::

    import requests
    def fib(n):
        r = requests.get(f'http://www.dabeaz.com/cgi-bin/fib.py?n={n}')
        resp = r.json()
        return int(resp['value'])

The popular ``requests`` library knows nothing of Curio.  As such, it blocks
everything waiting for a response.  Since it's waiting for I/O (as opposed to 
performing heavy CPU work), you can use ``curio.run_in_thread()`` like this::

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            fx = await curio.run_in_thread(fib, x)
            fy = await curio.run_in_thread(fib, y)
            return fx*fy
        except curio.CancelledError:
            print("No go diggy die!")
            raise

As a rule of thumb, use processes for computationally intensive
operations and use threads for I/O bound operations.

An Echo Server
--------------

A common use of Curio is network programming.  Here is an
echo server::

    from curio import run, tcp_server

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

Run this program and connect to it using ``nc`` or ``telnet``.  You'll
see the program echoing back data to you::

    bash % nc localhost 25000
    Hello                 (you type)
    Hello                 (response)
    Is anyone there?      (you type)
    Is anyone there?      (response)
    ^C
    bash %

In this program, the ``client`` argument to ``echo_client()`` is a
socket. It supports all of the usual I/O operations, but they are asynchronous
and should be prefaced by ``await``.  If you prefer, you can perform
I/O using a file-like interface by converting the socket to
a stream like this::

    async def echo_client(client, addr):
        print("Connection from", addr)
        async with client.as_stream() as s:
            async for line in s:
                await s.write(line)
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server, '', 25000, echo_client)
    
Intertask Communication
-----------------------

If tasks need to communicate, use a ``Queue``. Here's an example
of a publish-subscribe service::

    from curio import run, TaskGroup, Queue, sleep

    messages = Queue()
    subscribers = set()

    # Dispatch task that forwards incoming messages to subscribers
    async def dispatcher():
        while True:
            msg = await messages.get()
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
            while True:
                msg = await queue.get()
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

A Chat Server
-------------

Combining sockets and queues, you can implement a small chat server.  For example::

    from curio import run, spawn, TaskGroup, Queue, tcp_server

    messages = Queue()
    subscribers = set()

    async def dispatcher():
        while True:
            msg = await messages.get()
            for q in subscribers:
                await q.put(msg)

    async def publish(msg):
        await messages.put(msg)

    # Task that writes chat messages to clients
    async def outgoing(client_stream):
        queue = Queue()
        try:
            subscribers.add(queue)
            while True:
                name, msg = await queue.get()
                await client_stream.write(name + b':' + msg)
        finally:
            subscribers.discard(queue)

    # Task that reads chat messages and publishes them
    async def incoming(client_stream, name):
        async for line in client_stream:
            await publish((name, line))

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


    if __name__ == '__main__':
        run(chat_server('', 25000))

In this code, each connection results in two tasks (``incoming`` and 
``outgoing``).  The ``incoming`` task reads incoming lines and publishes
them.  The ``outgoing`` task subscribes to the feed and sends outgoing
messages.   The ``workers`` task group supervises these two tasks. If any
one of them terminates, the other task is cancelled right away.

The ``chat_server`` task launches both the ``dispatcher`` and a ``tcp_server``
task and watches them.  If cancelled, both of those tasks will be shut down.

Programming Advice
------------------

At this point, you have the core concepts. Here are a few tips:

- Think thread programming and synchronous code.
  Tasks execute like threads and programming techniques applied to threads
  apply to Curio. 

- Curio uses the same I/O abstractions as in synchronous code (e.g., sockets, files, etc.).  
  Methods have the same names and perform the same functions.  Just don't forget to
  add the extra ``await`` keyword.

- Be extra wary of calls that do not use an explicit
  ``await``.  Although they will work, they could 
  block progress of all other tasks. If you know
  that this is possible, use the
  ``run_in_process()`` or ``run_in_thread()`` functions.

Debugging Tips
--------------

A common mistake is forgetting ``await``.  For example::

    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            curio.sleep(5)        # Missing await
            n -= 1

This usually produces a warning message::
   
    example.py:8: RuntimeWarning: coroutine 'sleep' was never awaited

To debug running programs, use the monitor::

    import curio
    ...
    run(..., with_monitor=True)

The monitor shows the state of each task and can show stack traces.
To enter the monitor, run ``python3 -m curio.monitor`` in a separate window.

The ``traceback()`` method creates a stack trace that can be printed
or logged. For example::

    print("Where are you?")
    print(task.traceback())

Scheduler tracing can be enabled with code like this::

    from curio.debug import schedtrace
    import logging
    logging.basicConfig(level=logging.DEBUG)
    run(..., debug=schedtrace)

If you want even more detail, use ``traptrace`` instead of ``schedtrace``.

More Information
----------------

The reference manual is found at https://curio.readthedocs.io/en/latest/reference.html.

Programming recipes are found at https://curio.readthedocs.io/en/latest/howto.html.

Watch https://www.youtube.com/watch?v=Y4Gt3Xjd7G8 to learn about the theory of operation.
