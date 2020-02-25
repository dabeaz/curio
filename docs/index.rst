.. curio documentation master file, created by
   sphinx-quickstart on Thu Oct 22 09:54:26 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Curio
=====

Curio is a coroutine-based library for concurrent Python systems
programming.  It provides standard programming abstractions such as as
tasks, sockets, files, locks, and queues. You'll find it to be
familiar, small, fast, and fun. 

Curio is the work of David Beazley (https://www.dabeaz.com), who has
been teaching and talking about concurrency related topics for more
than 20 years, both as a university professor and as an independent
researcher.

Requirements
------------

Curio requires Python 3.7 or newer.  It has no third-party
dependencies and works on both POSIX and Windows.

Documentation
-------------

.. toctree::
   :maxdepth: 2

   tutorial
   howto
   reference

Curio University
----------------

Curio is based on ideas resulting from more than 12 years of
exploration into various facets of Python's concurrency and coroutine
model.  Dave has given numerous talks/tutorials on this topic at PyCon
and elsewhere.  Here is a detailed list of presentations to help you
understand how Curio works and some of the system thinking that has gone 
into it.  All of these talks are more general than Curio--you'll learn
a lot about Python concurrency in general.

* `Build Your Own Async <https://www.youtube.com/watch?v=Y4Gt3Xjd7G8>`_ 
   Workshop talk at PyCon India, 2019. 
   This workshop talks about the fundamentals of building a simple
   async concurrency library from scratch using both callbacks and
   coroutines.

* `Die Threads <https://www.youtube.com/watch?v=U66KuyD3T0M>`_
   Keynote talk at EuroPython, 2018. 
   Asynchronous programming is most commonly described as an alternative to
   thread programming.  But what if you reinvented thread programming run on top
   of asynchronous programming?  This talk explores this concept. It
   might be the most "experimental" talk related to Curio.

* `The Other Async (Threads + Asyncio = Love) <https://www.youtube.com/watch?v=x1ndXuw7S0s>`_ 
   Keynote talk at PyGotham, 2017.
   This talk steps through the thinking and design of building a so-called
   "Universal Queue" that works with both async programs and threads
   using a common programming interface. 

* `Fear and Awaiting in Async <https://www.youtube.com/watch?v=E-1Y4kSsAFc>`_ 
   Keynote talk at PyOhio 2016.
   A no-holds-barred tour through the possibilities that await programmers
   who embrace the new async/await syntax in Python.  Covers the basics of
   coroutines, async iteration, async context managers, and a lot of advanced
   metaprogramming including decorators, descriptors, and metaclasses.
   Also discusses the importance of API design in async programming.

* `Topics of Interest (Async) <https://www.youtube.com/watch?v=ZzfHjytDceU>`_ 
   Keynote talk at Python Brasil 2015.
   Perhaps the first "Curio" talk.  A small concurrency library similar 
   to Curio is live-coded and discussed along with other topics
   related to async.

* `Python Concurrency from the Ground Up (LIVE) <https://www.youtube.com/watch?v=MCs5OvhV9S4>`_ 
   Conference talk at PyCon 2015.  This live-coded talk
   discusses threads, generators, coroutines, the Global
   Interpreter Lock (GIL), and more.

* `Understanding the Python GIL <https://www.youtube.com/watch?v=Obt-vMVdM8s>`_
   Conference talk from PyCon 2010.  Understand the inner workings of the infamous
   Global Interpreter Lock and how it impacts thread performance.  See also
   this related `talk <https://www.youtube.com/watch?v=5jbG7UKT1l4>`_ from the RuPy 2011 conference.

* `A Curious Course on Coroutines and Concurrency <https://www.youtube.com/watch?v=Z_OAlIhXziw>`_ [`Materials <https://www.dabeaz.com/coroutines>`_]
   Tutorial at PyCon 2009.  Coroutines were first introduced in Python 2.5.
   This tutorial explores the foundations of using coroutines for various
   problems in data processing and concurrency.  This tutorial gives
   much of the background that led to the current incarnation of Python
   coroutines.

* `An Introduction to Python Concurrency <https://speakerdeck.com/dabeaz/an-introduction-to-python-concurrency>`_ 
   Tutorial at USENIX Technical Conference, 2009. A comprehensive overview of concurrency
   programming in Python. Includes threads, processes, and event-driven I/O.  A good overview
   of basic programming concepts.
   





