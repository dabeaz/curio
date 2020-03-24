# python3.7

"""Plugin module for pytest.

This enables easier unit tests for applications that use both Curio and Pytest. If you have Curio
installed, you have the plugin and can write unit tests per the example below.

Provides a fixture named `kernel`, and a marker (pytest.mark.curio) that will run a bare coroutine
in a new Kernel instance.

Example:

    from curio import sleep
    import pytest

    # Use marker

    @pytest.mark.curio
    async def test_coro():
        await sleep(1)


    # Use kernel fixture

    def test_app(kernel):

        async def my_aapp():
            await sleep(1)

        kernel.run(my_aapp)
"""

import inspect
import functools

import pytest

from curio import Kernel
from curio import meta
from curio import monitor
from curio.debug import longblock, logcrash


def _is_coroutine(obj):
    """Check to see if an object is really a coroutine."""
    return meta.iscoroutinefunction(obj) or inspect.isgeneratorfunction(obj)


def pytest_configure(config):
    """Inject documentation."""
    config.addinivalue_line("markers",
                            "curio: "
                            "mark the test as a coroutine, it will be run using a Curio kernel.")


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    """A pytest hook to collect coroutines in a test module."""
    if collector.funcnamefilter(name) and _is_coroutine(obj):
        item = pytest.Function(name, parent=collector)
        if 'curio' in item.keywords:
            return list(collector._genfunctions(name, obj))


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_pyfunc_call(pyfuncitem):
    """Run curio marked test functions in a Curio kernel instead of a normal function call.
    """
    if 'curio' in pyfuncitem.keywords:
        pyfuncitem.obj = wrap_in_sync(pyfuncitem.obj)
    yield


def wrap_in_sync(func):
    """Return a sync wrapper around an async function executing it in a Kernel."""
    @functools.wraps(func)
    def inner(**kwargs):
        coro = func(**kwargs)
        Kernel().run(coro, shutdown=True)
    return inner


# Fixture for explicitly running in Kernel instance.
@pytest.fixture(scope='session')
def kernel(request):
    """Provide a Curio Kernel object for running co-routines."""
    k = Kernel(debug=[longblock, logcrash])
    m = monitor.Monitor(k)
    request.addfinalizer(lambda: k.run(shutdown=True))
    request.addfinalizer(m.close)
    return k
