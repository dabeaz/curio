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


Different flavours of selector.


OSError
=======



Select Patience
===============

SelectPatience = 0
==================

If I get to the selector and there is nothing there it is an OSError.
I don't know how to answer the question (yet)

CallBackLater
=============


Catching Exceptions
===================

Bit like catching a cold.  Don't do it, otherwise you have to decide
what to do with it.  Or just throw it away.
