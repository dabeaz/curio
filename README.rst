curio - concurrent I/O
======================

Curio is a modern library for performing reliable concurrent I/O using
Python coroutines and the explicit async/await syntax introduced in
Python 3.5. Its programming interface is based on common system
programming abstractions such as sockets, files, tasks, subprocesses,
locks, and queues.  Unlike libraries that use a callback-based event loop,
curio is implemented as a queuing system. As such, it is considerably
easier to debug, offers a variety of advanced features, and runs
faster.

An Example
----------
Here is a simple TCP echo server implemented using sockets and curio::

    # echoserv.py
    
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
                print('Connection from', addr)
                await new_task(echo_client(client))
    
    async def echo_client(client):
        async with client:
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

Or, if you prefer something a little higher level, here is the same program written
using the curio socketserver module::

    # echoserv.py

    from curio import Kernel, new_task
    from curio.socketserver import TCPServer, BaseRequestHandler

    class EchoHandler(BaseRequestHandler):
        async def handle(self):
            print('Connection from', self.client_address)
            while True:
                data = await self.request.recv(1000)
                if not data:
                    break
                await self.request.send(data)
            print('Connection closed')

    if __name__ == '__main__':
        serv = TCPServer(('',25000), EchoHandler)
        kernel = Kernel()
        kernel.add_task(serv.serve_forever())
        kernel.run()

This is only a small sample of what's possible.  Read the tutorial for more
in-depth coverage.

Performance
-----------

If you run the above server and conduct a simple performance benchmark
sending 1K messages back and forth as quickly as possible between
processes on the same machine, you'll find that curio runs about 60%
faster than a comparable echo server written using asyncio and 40%
faster than an echo server written in Twisted.

Additional Features
-------------------

Curio provides additional support for synchronization primitives
(events, locks, semaphores, and condition variables), queues, Unix
signals, subprocesses, as well as thread and process pools.  In addition,
it uses a task model that fully supports cancellation, timeouts, and
other features critical to writing reliable code.

The Big Question: Why?
----------------------

Python already has a plethora of libraries for async and event driven
I/O. So, why create yet another library?  There is no simple answer to
that question, but here are a few of the motivations for creating curio.

* Python 3 has evolved considerably as a programming language and
  has adopted many new language features that are well-suited to cleanly
  writing a new I/O library. For example, support for delegation to
  subgenerators (`yield from`) and the introduction of explicit `async`
  and `await` syntax in Python 3.5. Curio takes full advantage of these
  features and is not encumbered by issues of backwards compatibility
  with legacy Python code written 15 years ago.


* Previous libraries have often made heavy use of clever hacks and
  tricks to implement concurrent I/O.  For example, relying upon C
  extensions to support green threads, monkeypatching standard library
  modules, performing dazzling acrobatic tricks with generators, and
  carrying out amazing feats of metaprogramming magic.  Many of these
  tricks were the motivation for features added to the Python language
  later.  Curio tries to avoid wild hacks. It is a pure Python library
  that uses standard features available in Python 3.5. It performs no
  clever patching, no manipulation of Python internals, and no advanced
  metaprogramming tricks.  The code does what it says it does.


* Existing I/O libraries are largely built on event-loops and callback
  functions--this includes Python's own asyncio module. Unfortunately,
  this particular programming model invariably leads to a
  spaghetti-coded nightmare of gotos disguised as callback functions
  wrapped in futures running inside tasks wrapping coroutines yielding
  futures (or something sort of like that).  Nobody can reason about
  what's actually going on in a system like that.  You might as well
  abandon all hope if you ever have to debug it when things don't work
  as expected or if you ever have to explain how it works to a
  grey-haired C programmer.  It's too complicated.


* Curio is a powerful library in a small package.  However, it places
  a great emphasis on implementation simplicity above all else. Simplicity
  is an important part of writing reliable systems software.  If you're
  going to have thousands of concurrently executing tasks, it helps to
  have a coherent mental model of how tasks execute and interact with
  each other.  It's important to build upon well-known abstractions that
  programmers already understand (i.e., sockets, files, etc.).  When
  your code fails, you need to be able to debug it--possibly down to the
  level of individual calls to the operating system. Simplicity matters
  a lot.


* It's fun. 

Under the Covers
----------------

Internally, curio is implemented entirely as a task queuing system--
much in the same model as how an actual operating system kernel works. Tasks
are represented by coroutine functions declared with the `async`
keyword.  Each yield of a coroutine results in a low-level kernel
"trap" or system call.  The kernel handles these traps by moving the
task to various waiting queues. Events (i.e., due to I/O) and other
operations make the tasks move from waiting queues back into service.

It's important to emphasize that the kernel is solely focused on task
management, scheduling, and nothing else. No part of the kernel is
based on triggering event callback functions. In fact, the kernel
doesn't even perform any I/O operations.   This means that it is very
small, very fast, and relatively easy to understand.

Everything useful in curio is actually carried out in coroutines that
run on top of the kernel.  This includes all I/O operations and the
implementation of all other objects (synchronization primitives, sockets,
queues, etc.).   The makes the code simpler to write and easier to debug.
If there are problems, you get complete stack tracebacks and you can use
standard debugging tools. 

About
-----
Curio was created by David Beazley (@dabeaz).  http://www.dabeaz.com

It is a young project.  Contributions welcome.








 
