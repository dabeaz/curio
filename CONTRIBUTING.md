Contributing to Curio
=====================

Curio is a young project and currently rather experimental.
Contributions of most kinds that make it better are welcome--this
includes code, documentation, examples, and feature requests.

There aren't too many formal guidelines.  If submitting a bug report,
any information that helps to reproduce the problem will be handy.  If
submitting a pull request, try to make sure that Curio's test suite
still passes. Even if that's not the case though, that's okay--a
failed test might be something very minor that can fixed up after a
merge.

Project Scope
-------------

It is not my goal to turn Curio into a gigantic framework with every
possible feature.  What you see here is pretty much what it
is. Instead, it's best to view Curio more as a small library for
building other more interesting things. If you have built something
useful that uses Curio, it is probably better served by its own
repository.  Feel free to submit a pull request to the Curio README
file that includes a link to your project.

Also, if submitting a pull request, please consider updating the
"Contributors" section of the README file so that you get credit.

The Curio "Community" (or lack thereof)
---------------------------------------

A number of people have asked me "is Curio a serious project?"  In
short, "yes" (although whimsical tongue-in-cheek aspects of the
documentation might suggest otherwise).  However, it's also important
to emphasize that Curio is also very much a side-project. No funding
is received for this work.  I also run a business and have a family
with kids.  These things have higher priority. As such, there may be
periods in which little activity is made on pull requests, issues, and
other development matters.  Do not mistake my "inaction" for
"disinterest."  I am definitely interested in improving Curio and
making it awesome--I just can't work on it all of the time or serve as
some kind of community BDFL.  Not every project needs a conference, a
sticker, or a community.  However, if you've made something
interesting with Curio, please feel free to add a link to your project
in the README. Citations to Curio are also always appreciated. 

Testing
-------
[![Build Status](https://travis-ci.org/dabeaz/curio.svg?branch=master)](https://travis-ci.org/dabeaz/curio)

Curio uses the [py.test](http://pytest.org) tool to write and drive
its tests. Probably the best way to get set up to run the test suite
is to create a virtual environment. For instance, if you were going
to run the tests under CPython 3.5, then you would want to run the
command::

  python3.5 -m venv venv-cpython35

This will create a `venv-cpython35` directory that you can install
py.test into. From there you can follow what the
[`.travis.yml` file](https://github.com/dabeaz/curio/blob/master/.travis.yml)
does to run Curio's test suite (both for code and documentation).

Important Note
--------------
Pull requests related to type-hinting, type annotations, or static
type checking will not be accepted.  Given the dynamic nature of
Python, there is a pretty good chance that such annotations will be
wrong.  If you want this, use a different programming language or a
different library.




