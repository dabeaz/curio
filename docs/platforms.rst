================================
 Quirks and quarks of platforms
================================

*curio* runs on a lot of platforms.

On many most of it works,

Here are some of the known areas of weirdness,

Windows
=======

If *sys.platform == 'win32'* then it mostly works at this point.

There are a few rough edges.

run_in_process
--------------

This does not work at present.

*curio* uses parts of pipes that are not there on win32.

However, *run_in_executor* does essentially the same thing, at the cost
of an extra thread.  *curio* may also have slightly less control when
running in an executor.

So, on windows, and have something cpu bound that might take a while: run_in_executor,

FIXME: add an example.

Selector
--------

See the *tail of the OS that barked in the night*.

There is a fix in curio that catches the OSError that *selector_selet*
throws if it is called with nothing in the selector.


Tested on
---------

Windows 10 and Window 7

Ubuntu bash on Windows 10
=========================

This says *sys.platform == 'linux'*.

And it is pretty much just that.

In reality it is the *windows system for linux* FIXME: check.

Limited experience of *curio* here.

socket.SO_REUSEPORT
-------------------

This is not implemented in the current WSL.

It is noted that it was not available on older linux.  FIXME: how old?

See: https://github.com/dabeaz/curio/issues/168



