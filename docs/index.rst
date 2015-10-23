.. curio documentation master file, created by
   sphinx-quickstart on Thu Oct 22 09:54:26 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

curio - Concurrent I/O
======================

Curio is a modern library for performing reliable concurrent I/O using
Python coroutines and the explicit async/await syntax introduced in
Python 3.5. Its programming interface is based on common system
programming abstractions such as sockets, files, tasks, subprocesses,
locks, and queues.  Unlike libraries that use a callback-based event loop,
curio is implemented as a queuing system. As such, it is considerably
easier to debug, offers a variety of advanced features, and runs
faster.

Contents:

.. toctree::
   :maxdepth: 2

* :doc:`tutorial` 
* :doc:`reference`

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`

