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

The problem with this is too often and it wastes resources, not often enough


Communication between tasks and event loops
===========================================


Polling
=======
