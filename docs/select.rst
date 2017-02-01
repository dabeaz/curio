======================================================================
 Selector select and the tail of the OS that didn't bark in the night
======================================================================

Curio gets very close to the operating system.  When you do that you
tend to feel the heat of the cpu and the bats can fly.

So curio is about managing tasks.  And the flow of information between
them.

On most operating systems this stuff flows through sockets or to or
from files.

The operating system handles all the events such as data coming and
going.

It provides a *select* service that does some magic and tells you
which of the things it is looking for need attention.

Readers and writers
===================

If you probe around in the *selector* it has *_readers* and *_writers* objects.

These are the sockets and files that the process is managing and the
seletor returns a list of events that are ready to be handled.

(At least that's what I think is going on).

OSError
=======

Now sometimes the selector is called before it knows about readers and
writers.

On some operating systems the selector just calls *sleep(timeout)* and
returns an empty list.

On others, in particular ones where "sys.platform == 'win32' an
*OSError* is raised.

This message on a python bug thread explains more of what is going on:

https://bugs.python.org/issue29256#msg285497

In short, Windows dispatches the call to a *provider*.  The code
supports the concept that different file objects can belong to
different providers.

It inspects the first file it finds to determine the provider.

So, if there are no file objects around it cannot determine what
provider to call, so it just throws up its hands and throws an *OSError*.

Aside: this means that all files in the selector need to support the
same provider.  Are there actual cases of different providers?
Guessing it is generally best to just leave it to the operating system
at this point.


CallBackLater
=============

Now in the case of *curio*, the main kernel loop is written in such a
way that the *selector* gets called before it knows about any file
descriptors.

*Curio* then processes its own list of things that are *ready* to be
registered with the selector.  Next time round the main *run* loop all
is good.

So, perhaps what windows should be doing here is raising a
*CallBackLater* exception, since the real problem is that it is not
yet ready to ask the question that has been asked.

This is actually quite a common situation in asynchronous code: a task
gets asked to do what it does *before* it is ready to answer the
question.  That's probably why thread programming is so much fun.

*Curio*, *async*, *await* make it much easier to manage these
situations since the code specifies where it can be interrupted.  So
*curio* tasks only communicate with each other when they are ready to
do so.

It is just curio itself that has to deal with the nutty problem of
scheduling everything.  And it does this with a little help from the
operating system and *select*.


Select Patience
===============

So the fix to make all this work on windows is just to catch the
*OSError* and make the selector sleep for a while, in short call back
later.

Catching Exceptions
-------------------

Now this is all well and good, but catching exceptions always leaves
you with a problem to solve: what to do with the exception?

It is a bit like catching a cold.  Don't do it, otherwise you have to
decide what to do with it.  Or just throw it away.

In this case, the OSError's just get dropped, with a log message.

Quietly dropping OSError messages makes me nervous.  Particularly at
the core of something like *curio*.   Now the code is assuming that is
caused by there being nothing to select from, but what if it is
something else causing her OSError, it might be good to see that?

In this case, we only expect to see the OSError on the first time
round the loop and only if we are windows [aside I am really curious
to see how this works on Windows 10 under Ubuntu bash].

So, a small re-work of the current code seems in order.


SelectPatience = 0
==================

One idea is to set a variable, *SelectorPatience* to the number of
times you are prepared to see OSError before you just give up and
raise the error.

On non-windows, seting this to zero would seem the right thing, any
OSError thrown by *select* is something you should know about.

SelectPatience = 1
==================

On windows, *SelectorPatience = 1* would seem the way to go.  Let it
complain the first time, interpret the error as "CallBackLater* and do
just that.

SelectPatience > 1
==================

This is probably not a good idea unless you know what is going on.  Oh
and what OS are you using?

With this, if the *tail* of your OS barks in the night you might not
hear it.

So set SelectPatience to 0 or 1 according to your OS and you will miss
at most one bark in the night.  And on windows the selector always
barks once.

Timeout in the kernel run loop
==============================

The call to the selector includes a timeout as follows:
*selector_select(timeout)*

The idea is that the kernel has nothing to do for *timeout* seconds so
it might as well wait on I/O unti then.

Upstream
========

Should this be fixed upstream?

The code in *curio* to handle the OSError could be used in the
upstream in the same way.

This may make a lot of things start working.

Or, Murphy's Law says it will break all sorts of wonderful code that
is catching the OSError and doing something exotic critical to the
running of the process.

It might be good to have an easy way to at least test the change.

Windows Ubuntu Bash
-------------------

Still working on finding a machine with a Ubuntu bash and python 3.5+.

Hope to have one to test soon.

Downstream
==========

Having a curio that works reliably across platforms opens up a lot
more options.


User interface
==============

This thread is generating some interesting ideas on using *tkinter* or
*qt* with curio.  Or anything else with its own eventloop:

https://github.com/dabeaz/curio/issues/111

