Curio - A Tutorial Introduction
===============================

Curio is a library for concurrent systems programming that
uses coroutines and the async/await syntax introduced in Python
3.5. Most of Curio is based on existing abstractions such
as threads, sockets, files, locks, and queues. However, it also
implements a task model that provides for cancellation, task groups,
and other features.  This tutorial takes you through the basics of
the concurrency model.  Consult the "howto" guide at
https://curio.readthedocs.io/en/latest/howto.html for cookbook-style information
on specific programming tasks.

Getting Started
---------------

Consider a simple program that prints a countdown::
 
    # hello.py
    import curio
    
    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    if __name__ == '__main__':
        curio.run(countdown, 10)

Curio requires the use of
``async`` functions (or coroutine functions). To run a program, you
provide a function along with its arguments to the ``run()``
function. When the function completes its result is returned.

Tasks and Concurrency
---------------------

Let's write a program that does two things at once::

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

This program illustrates how to create and join with tasks.
``curio.spawn()`` is used launch tasks. The ``join()`` method waits
for a task to finish and returns its result.
If you run this program, you'll see it produce the following
output::

    bash % python3 hello.py
    Getting around to doing my homework
    T-minus 10
    T-minus 9
    ...
    T-minus 2
    T-minus 1
    Are you done yet?
    .... hangs ....

At this point, the child is busy for the next 1000 seconds, the parent
is blocked on ``join()`` and nothing seems to be happening--this is
the mark of all good concurrent programs (hanging that is).  Change
the last part of the program to run the kernel with the monitor
enabled::

    ...
    if __name__ == '__main__':
        curio.run(parent, with_monitor=True)

Run the program again.  Now, open up another terminal window on the same
machine and connect to the monitor::

    bash % python3 -m curio.monitor
    Curio Monitor: 4 tasks running
    Type help for commands
    curio >

View the status of each task by typing ``ps``::

    curio > ps
    Task   State        Cycles     Timeout Sleep   Task                                               
    ------ ------------ ---------- ------- ------- --------------------------------------------------
    1      READ_WAIT    1          None    None    Kernel._make_kernel_runtime.<locals>._kernel_task 
    3      FUTURE_WAIT  1          None    None    Monitor.monitor_task                              
    4      TASK_JOIN    2          None    None    parent                                            
    5      TIME_SLEEP   1          None    970.186 kid                                               
    curio > 

You can see that the parent is waiting to join and that the kid is
sleeping.  You can get the stack trace of any active task using the
``where`` command::

    curio > w 4
    Stack for Task(id=4, name='parent', state='TASK_JOIN') (most recent call last):
      File "hello.py", line 24, in parent
        result = await kid_task.join()
    curio > w 5
    Stack for Task(id=5, name='kid', state='TIME_SLEEP') (most recent call last):
      File "hello.py", line 14, in kid
        await curio.sleep(1000)
    curio >

Tasks can be forcefully cancelled. Change the program as follows::

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
            print("Guess I'll fail!")
            raise

Now the program should produce output like this::

    bash % python3 hello.py
    Getting around to doing my homework
    T-minus 10
    T-minus 9
    ...
    T-minus 2
    T-minus 1
    Are you done yet?
    We've got to go!
    Guess I'll fail!
   bash %

This is the basic gist of tasks. You can create
tasks, join tasks, and cancel tasks.  

Task Groups
-----------

Suppose you want to put the ``countdown()`` and the ``kid()`` task in
a race. That is, have the two tasks run concurrently, but whichever
one finishes first wins--cancelling the other task.  This kind of coordination
can be handled using a ``TaskGroup``.  Change the ``parent()`` function to this::

    async def parent():
        async with curio.TaskGroup(wait=any) as g:
            await g.spawn(kid, 37, 42)
            await g.spawn(countdown, 10)

        if g.result is None:
            print("Why didn't you finish?")
        else:
            print("Result:", g.result)

Here, a task group waits for any spawned task to finish (the ``wait=any``
argument). When this occurs, the losing task is 
automatically cancelled.  The ``result`` attribute of the group
contains the result of the task that finished first.

Running this code, you will either get output similar to this::

    Getting around to doing my homework
    T-minus 10
    T-minus 9
    T-minus 8
    T-minus 7
    Result: 1554

or you will get this if the ``kid()`` takes too long::

    Getting around to doing my homework
    T-minus 10
    T-minus 9
    ...
    T-minus 2
    T-minus 1
    Guess I'll fail!
    Why didn't you finish?

A critical feature of a task group is that when used as a context
manager (as shown), no child task survives--all created tasks will
have either completed or have been cancelled when control-flow leaves
the managed block. 

Blocking Operations
-------------------

Suppose that the ``kid()`` task now requires the computation of
Fibonacci numbers using an algorithm with exponential complexity like
this::

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
            print("Guess I'll fail!")
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

If you run this version, you'll find that everything becomes
unresponsive.  For example, you won't see the ``countdown()`` task
running.  The problem is that the ``fib()`` function takes the CPU and
never yields.  Important lesson: Curio DOES NOT provide preemptive
scheduling. If a task decides to compute large Fibonacci numbers or
mine bitcoins, everything blocks until it's done. Don't do that.

For other tasks to make progress, you need to modify ``kid()``
to carry out computationally intensive work in a separate process.
Change the code to use ``curio.run_in_process()`` like this::

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            fx = await curio.run_in_process(fib, x)
            fy = await curio.run_in_process(fib, y)
            return fx * fy
        except curio.CancelledError:
            print("Guess I'll fail!")
            raise

With this change, you'll now see the countdown task running and
the kid task will be cancelled if it takes too long (to see it finish, you might need
to greatly increase the countdown duration).   Coincidentally, you
could modify the code to carry the computation in parallel on
two CPUs.  You can also do this using a task group::

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

The problem of blocking also applies to operations involving I/O.  For
example, suppose the kid starts hanging out with a bunch of savvy 5th
graders who are into microservices and the ``fib()`` function morphs
into something that's making HTTP requests and decoding JSON::

    import requests
    def fib(n):
        r = requests.get(f'http://www.dabeaz.com/cgi-bin/fib.py?n={n}')
        resp = r.json()
        return int(resp['value'])

The popular ``requests`` library knows nothing of Curio and it blocks
the internal event loop while waiting for a response.  This is
essentially the same problem as before except that ``requests.get()``
mainly spends its time waiting for I/O. For this, you can use
``curio.run_in_thread()`` to move work to a separate thread
instead. Modify the code like this::

    async def kid(x, y):
        try:
            print('Getting around to doing my homework')
            fx = await curio.run_in_thread(fib, x)
            fy = await curio.run_in_thread(fib, y)
            return fx*fy
        except curio.CancelledError:
            print("Guess I'll fail!")
            raise

The problem of blocking is a common issue with all async
frameworks. Unless you can rewrite the code to be fully async, running
code in a separate thread or process is really your only option to
avoid stalls.  The ``run_in_process()`` and ``run_in_thread()``
functions are used to do just this.  As a rule of thumb, use processes
for computationally intensive tasks and use threads for tasks that
are mostly performing I/O.  

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
see the program echoing back data to you.  Open up multiple
connections and see that it handles multiple client connections::

    bash % nc localhost 25000
    Hello                 (you type)
    Hello                 (response)
    Is anyone there?      (you type)
    Is anyone there?      (response)
    ^C
    bash %

In this program, the ``client`` argument to ``echo_client()`` is a
socket. However, all I/O operations are now asynchronous and must use
``await``.  In some cases, it is easier to work with the data
presented with a file-like interface--especially if you must work with
data formatted as lines.  To do this, you can convert the socket into
a stream like this::

    async def echo_client(client, addr):
        print("Connection from", addr)
        s = client.as_stream()
        async for line in s:
            await s.write(line)
        await s.close()
        print('Connection closed')

    if __name__ == '__main__':
        run(tcp_server, '', 25000, echo_client)
    
If you've written a similar program using sockets and threads, you'll
find that this program looks nearly identical except for the use of
``async`` and ``await``.  Any operation that involves I/O, blocking, or
the services of Curio is always prefaced by ``await``.  

Intertask Communication
-----------------------

If you want tasks to communicate, use a ``Queue``.  For example,
here's an example of implementing a publish-subscribe service::

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

A Chat Server
-------------

Combining sockets and queues, you can implement a simple chat server.  For example::

    from curio import run, spawn, TaskGroup, Queue, tcp_server

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

At this point, you should have enough of the core concepts to get started. 
Here are a few programming tips:

- Think thread programming and synchronous code.
  Tasks execute like threads and programming techniques applied to threads
  also apply to Curio.  Just remember that blocking operations are
  always prefaced by an explicit ``await``. 

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
consider the use of the monitor.  For example::

    import curio
    ...
    run(..., with_monitor=True)

The monitor can show you the state of each task and you can get stack 
traces. Remember that you enter the monitor by running ``python3 -m curio.monitor``
in a separate window.

The stack trace of any task can be produced using its ``traceback()`` method. For
example::

    print("Where are you?")
    print(task.traceback())

You can also turn on scheduler tracing with code like this::

    from curio.debug import schedtrace
    import logging
    logging.basicConfig(level=logging.DEBUG)
    run(..., debug=schedtrace)

This will write detailed log information showing the scheduling of tasks.  If you want even
more fine-grained information, use ``traptrace`` instead of ``schedtrace``.

More Information
----------------

A reference manual can be found at https://curio.readthedocs.io/en/latest/reference.html.

See the HowTo guide at https://curio.readthedocs.io/en/latest/howto.html for more tips and
techniques.















    







