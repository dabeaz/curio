=============
 Event Loops
=============

Here are some thoughts arising from this gitub issue:

https://github.com/dabeaz/curio/issues/111

If you are using *curio* with a user interface then there will be some
sort of event loop driving the user interface.

For example, tkinter.mainloop() runs a *tkinter* user interface.

This note uses *tkinter* as an example but it could as well be *gt*,
*gtk* or some magical web server.

*Twisted* might well have solved these issues a while back.  Or be
working on them too.

Widgets as co-routines
======================

Imagine widgets that just build and return something with an *async
run* method.

Build the widgets you need, then let *curio* fire the *run* coroutines
up and away you go.

GUI events
==========

Whatever is driving the event loop, the loop itself will be processing
events.

In short everything to make the user interface run.

So, there will be keyboard events, mouse events and events to paint
the screen etc.

Events from keyboards and mice and other user input devices are of
interest to the tasks that are running the widgets.

Callbacks
=========

One way to handle events is to use the GUI toolkit as it was designed
and call a callback function whenever the appropriate event arrives.

Or, you could interpret these events and turn them into
*curio.Events*.

Push these into a queue and then other tasks can pop them off the
queue and call appropriate methods or co-routines as appropriate.

User input
==========

This can be anything you like that is connected to the computer.

Keyboards and mice, touchscreens, web cam images.  Whatever you have.

If a task can convert these inputs into a common language, your own
language, then things could get interesting.


Polling
=======

Current solutions for *tkinter* involve periodically checking if it
has any events waiting.

The problem with this is too often and it wastes resources, not often
enough and the user interface becomes sluggish.  

Now somewhere in the *tkinter.mainloop*, if we are lucky, it is
runnint *select* waiting on activity on file descriptors that are used to pass
events along.

If we can find these descriptors, then we can wrap them up and let
curio do the waiting for input.

Then there will be no polls.

Why not have the mainloop just use queues?
==========================================

So events can be passed between the *tkinter* thread and curio tasks
by putting them into a *curio.queue*.

With this solution, you can just check the queue sizes, say once each
time round the mainloop and process them if they are not empty.

The good news with this solution is code called in the tkinter
mainloop just has to check a queue size periodically.  This should be
a fairly cheap operation, but might involve communication with another
thread depending on how *curio* is handling the queue.

The down side is that we do not have access to all the curio magic in
any of the callbacks made to the widgets.


Current solutions
=================

Polling the *tkinter* thread periodically to see if there is anything
it needs to do is working reasonably well.

There is room for improvement by making the nap times between polls
adaptive, in other words poll more regularly if we are always finding
events to process, less regularly if not.

A better solution would be to find the relevant file descriptors and
let *curio* handle these.

Pausing a kernel
----------------

Other *curio* users working with multiple event loops are wanting to
pause the *curio* event loop periodically.

It would be good to have a simple example explaining where and how
this is useful.

One other thought, is that one interesting case of their being
multiple eventloops is when we have multiple *curio* applications
which are communicating with each other.

In this case, if they use a *curio.Channel* there is no polling.

This case is different to the case where we are dealing with a
non-curio event loop.


async def tkmainloop
--------------------

If *tkinter* provided an async version of its mainloop then that would
just be another co-routine for curio to manage.

