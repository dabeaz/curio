# curio - concurrent I/O

Curio is a modern library for performing reliable concurrent I/O using
Python coroutines and the explicit async/await syntax introduced in
Python 3.5.  Its programming model is based on common system
programming abstractions such as sockets, files, tasks, subprocesses,
locks, and queues.  It is an alternative to asyncio that is
implemented as a queuing system, not a callback-based event loop.

## Getting Started

Here is a simple curio hello world program--a task that prints a simple
countdown as you wait for your kid to put their shoes on:
 
    # hello.py
    import curio
    
    async def countdown(n):
        while n > 0:
            print('T-minus', n)
            await curio.sleep(1)
            n -= 1

    if __name__ == '__main__':
        kernel = curio.Kernel()
        kernel.add_task(countdown(10))
        kernel.run()

Run it and you'll see a countdown.  Yes, some jolly fun to be
sure. Curio is based around the idea of tasks.  Tasks are functions
defined as coroutines using the `async` syntax.  To run a task, you
create a `Kernel` instance, add the task to it and then invoke the
`run()` method.

## Tasks

Let's add a few more tasks into the mix:

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
        kernel.add_task(parent())
        kernel.run()

This program illustrates the process of creating and joining with
tasks.  Use the `curio.new_task()` coroutine to have a task launch a
new task.  Use the `join()` method of the returned task object to wait
for it to finish.  If you run this program, you'll see it produce the
following output:

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
the next 1000 seconds, the parent is blocked on `join()` and nothing
much seems to be happening.  Change the last part of the program to
create the kernel with the monitor enabled:

    ...
    if __name__ == '__main__':
        kernel = curio.Kernel(with_monitor=True)
        kernel.add_task(parent())
        kernel.run()

Run the program again. You'd really like to know what's happening?
Yes?  Press Ctrl-C to enter the curio monitor:

    ...
    We're leaving!
    ... hanging ...
    ^C
    Curio Monitor:  4 tasks running
    Type help for commands
    curio > 

Let's see what's happening:

    curio > ps
    Task   State        Cycles     Timeout Task                                               
    ------ ------------ ---------- ------- --------------------------------------------------
    1      READ_WAIT    2          None    Kernel._init_task                                 
    2      RUNNING      6          None    monitor                                           
    3      TASK_JOIN    5          None    parent                                            
    4      TIME_SLEEP   1          926.016 kid                                               

In the monitor, you can see a list of the active tasks.  You can see
that the parent is waiting to join and that the kid is sleeping for
another 926 seconds.  If you type `ps` again, you'll see the timeout
value change. Although you're in the monitor--the kernel is still
running underneath.  Actually, you'd like to know more about what's
happening. Get the stack frames of the tasks:

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
get on with their business:

    curio > cancel 4
    Cancelling task 4
    Leaving!
    curio > 
    bash % 

Debugging is an important feature of curio--using the monitor, you see what's happening as tasks run.
Can can find out where tasks are blocked and you can cancel any task that you want.
However, it's not necessary to do this in the monitor.  Change the parent task to include a timeout
and a cancellation request like this:

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
forcefully cancelled.  Problem solved.

Of course, all is not lost in the child.  If desired, they can catch the cancellation request
and cleanup. For example:

    async def kid():
        try:
            print('Building the Millenium Falcon in Minecraft')
            await curio.sleep(1000)
        except curio.CancelledError:
            print('Fine. Saving my work.')

Now your program should produce output like this:

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
Blocking operations (e.g., `join()`) almost always have a timeout option. 

## Task Synchronization

Tasks often need to synchronize.  For this purpose, curio provides `Event`, `Lock`, `Semaphore`, and `Condition` objects.
For example, let's introduce an event that makes the child wait for the parent's permission to start playing:

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
in the `threading` module.  The main difference is that all operations
must be prefaced by `await`. Thus, to set an event you use `await
start_evt.set()` and to wait for an event you use `await
start_evt.wait()`. Almost all of the synchronization methods also
support timeouts.

## Signals

What kind of parent only lets their child play Minecraft for 5
seconds?  Instead, let's have the parent allow the child to play as
much as they want until a Unix signal arrives.  Modify the code like
this:

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
indefinitely--well, until a `SIGHUP` arrives.  When you run the
program, you'll see this:

    bash % python3 hello.py
    Parent PID 36069
    Can I play?
    Yes, go play
    Building the Millenium Falcon in Minecraft

Don't forget, if you're wondering what's happening, you can always drop into
the curio monitor by pressing Control-C:

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

If you want to initiate the signal, go to a separate terminal and type this:

    bash % kill -HUP 36069

You'll see the parent wake up, do the countdown and cancel the child.  Very good.

## Number Crunching

Now, suppose for a moment that the kid has decided that building the
Millenium Falcon requires computing a sum of larger and larger
Fibonacci numbers using an exponential algorithm like this:

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
curio does not provide any kind of preemption.  If a task decides to
go off and mine bitcoins, the entire kernel will block until its done.

If you know that work might take awhile, you can have it execute in a
separate process however.  Change the code use `curio.run_cpu_bound()`
like this:

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

In this version, the kernel will remain fully responsive.  You can use the
monitor and send the signal--shutdown will occur.
    
## And Finally, Some I/O

Now that you've got the basics down, let's look at some I/O. Here
is a simple echo server written directly with sockets using curio:

    from curio import Kernel, new_task
    from curio.socket import *
    
    async def echo_server(address):
        sock = socket(AF_INET, SOCK_STREAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        sock.bind(address)
        sock.listen(5)
        print('Server listening at', address)
        with sock:
            while True:
                client, addr = await sock.accept()
                print('Connection from', addr)
                await new_task(echo_client(client))
    
    async def echo_client(client):
        with client:
             while True:
                 data = await client.recv(1000)
                 if not data:
                     break
                 await client.sendall(data)
        print('Connection closed')

    if __name__ == '__main__':
        kernel = Kernel()
        kernel.add_task(echo_server(('',25000)))
        kernel.run()

Run this program and try connecting to it using a command such as `nc`
or `telnet`.  You'll see the program echoing back data to you.  Open
up multiple connections and see that it handles multiple client
connections perfectly well.  Very good.

    bash % nc localhost 25000
    Hello                 (you type)
    Hello                 (response)
    Is anyone there?      (you type)
    Is anyone there?      (response)
    ^C
    bash %
    
If you've written a similar program using sockets and threads, you'll
find that this program looks nearly identical except for the use of
`async` and `await`.  Any operation that involves I/O, blocking, or
the services of the kernel is prefaced by `await`.  Carefully notice
that we are using the module `curio.socket` instead of the built-in
`socket` module here.

If writing code with low-level sockets is a bit much, you can always
switch to the higher level `socketserver` interface:

    from curio import Kernel, new_task
    from curio.socketserver import StreamRequestHandler, TCPServer
    
    class EchoHandler(StreamRequestHandler):
        async def handle(self):
            print('Connection from', self.client_address)
            async for line in self.rfile:
                await self.wfile.write(line)
            print('Connection closed')

    if __name__ == '__main__':
        serv = TCPServer(('',25000), EchoHandler)
        kernel = Kernel()
        kernel.add_task(serv.serve_forever())
        kernel.run()

This code mirrors the code you might write using the `socketserver`
standard library--again, just remember to add `async` and `await` to
I/O operations.

## More to Come...

Curio is a work in progress.  More documentation is forthcoming.





    







