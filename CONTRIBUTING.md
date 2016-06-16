Contributing to Curio
=====================

Curio is a young project and currently rather experimental.
Contributions of any kind that make it better are welcome--this
includes both code and documentation.

There aren't too many formal guidelines.  If submitting a bug report,
any information that helps to reproduce the problem will be handy.  If
submitting a pull request, try to make sure that Curio's test suite
still passes. Even if that's not the case, that's okay--a failed test
might be something very minor that can fixed up after a merge and some
review (if not, expect some discussion).

It is not my goal to turn Curio into a gigantic framework with every
possible feature.  If you have built something useful that uses Curio,
it might be better served by its own repository.  Feel free to submit
a pull request to the Curio README file that includes a link to your
project.

Also, if submitting a pull request, please consider updating the
"Contributors" section of the README file so that you get credit.

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
