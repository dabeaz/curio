# test_tls.py

import pytest
from curio import *
from threading import Thread

# Like run, but unwraps exceptions so pytest can see them properly.
# Lets us use assert from inside async functions.


def run_with_real_exceptions(*args, **kwargs):
    try:
        return run(*args, **kwargs)
    except TaskError as e:
        real = e.__cause__
        # we can't avoid ending up with real.__context__ == e
        # and if e.__cause__ = real then we end up with a reference loop that
        # makes py.test blow up. So we have to None-out e.__cause__. (del is
        # illegal.)
        e.__cause__ = None
        raise real from None


def test_smoketest():
    local = Local()

    async def smoketest():
        assert local.__dict__ == {}
        assert vars(local) == {}
        local.a = 1
        assert local.a == 1
        assert local.__dict__ == {"a": 1}
        assert vars(local) == {"a": 1}
        del local.a
        with pytest.raises(AttributeError):
            local.a
        with pytest.raises(AttributeError):
            del local.a
        assert local.__dict__ == {}
        assert vars(local) == {}

        local.__dict__["b"] = 2
        assert local.b == 2

    run_with_real_exceptions(smoketest())


def test_isolation():
    local = Local()

    event1 = Event()
    event2 = Event()
    async def check_isolated_1():
        local.a = 1
        await event1.set()
        await event2.wait()
        assert local.a == 1

    async def check_isolated_2():
        await event1.wait()
        # another task has done local.a = 1, but we shouldn't be able to see
        # it
        assert not hasattr(local, "a")
        # Just like our assignment shouldn't be visible to them
        local.a = 2
        await event2.set()

    async def check_isolated():
        for task in [await spawn(check_isolated_1()),
                     await spawn(check_isolated_2())]:
            await task.join()

    run_with_real_exceptions(check_isolated())


def test_inheritance():
    local = Local()

    event1 = Event()
    event2 = Event()
    async def parent():
        local.a = "both"
        assert local.a == "both"
        child_task = await spawn(child())
        # now let the child check that it got the value, and try to change it
        await event1.wait()
        # child modification shouldn't be visible here
        assert local.a == "both"
        # and now check that the child can't see our change
        local.a = "parent"
        await event2.set()
        await child_task.join()

    async def child():
        assert local.a == "both"
        local.a = "child"
        assert local.a == "child"
        await event1.set()
        await event2.wait()
        assert local.a == "child"

    run_with_real_exceptions(parent())


def test_nested_curio():
    # You should never do this. But that doesn't mean it should crash.
    # Well, actually it probably should crash.
    local = Local()

    async def inner():
        assert not hasattr(local, "a")
        local.a = "inner"
        assert local.a == "inner"

    async def outer():
        local.a = "outer"
        with pytest.raises(RuntimeError):
            run_with_real_exceptions(inner())

    run_with_real_exceptions(outer())

def test_within_thread():
    local = Local()

    async def parent(parent_data):
        async def child(data):
            local.data = data
            await sleep(0)
            assert local.parent == parent_data # inherited
            assert local.data == data

        local.parent = parent_data

        tasks = []
        for data in range(8):
            tasks.append(await spawn(child(data)))
        for t in tasks:
            await t.join()

    exceptions = []
    def run_capturing_exceptions(*args, **kwargs):
        try:
            run_with_real_exceptions(*args, **kwargs)
        except Exception as e:
            nonlocal exceptions
            exceptions.append(e)

    threads = [Thread(target=run_capturing_exceptions, args=(parent(data),))
               for data in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        if exceptions:
            raise exceptions.pop()
