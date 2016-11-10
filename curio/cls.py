# curio/cls.py
#
# Context local storage

__all__ = ["Local"]

# Our public API is intentionally almost identical to that of threading.local:
# the user allocates a curio.Local() object, and then can attach arbitrary
# attributes to it. Reading one of these attributes later will return the last
# value that was assigned to this attribute *by code running inside the same
# Task*.
#
# Internally, each Task has an attribute .context_local_storage, which holds a
# dict. This dict has one entry for each Local object that has been accessed
# from this task context (i.e. entries here are lazily allocated), keyed by
# the Local object instance itself:
#
#   {
#     local_object_1: {
#       "attr": value,
#       "attr": value,
#       ...
#     },
#     local_object_2: {
#       "attr": value,
#       "attr": value,
#       ...
#     },
#     ...
#   }
#
# From an async context one could access this dict with
#
#  (await curio.current_task()).context_local_storage
#
# But, we also want to be able to access this from synchronous context,
# because one of the major use cases for this is tagging log messages with
# context, and there are lots of legacy third-party libraries that use the
# Python stdlib logging module. And it's synchronous. So if you want to
# capture their logs and feed them into something better and more context-ful,
# then you need to be able to get that context from synchronous-land.
#
# Therefore, whenever we resume a task, we stash a pointer to its
# .context_local_storage dictionary in a global *thread*-local variable. Then
# when we want to find a specific variable (local_obj.attr), we ultimately
# look in
#
#  _current_context_local_storage.value[local_obj]["attr"]
#
# An unusual feature of this implementation (and our main deviation from
# threading.Local) is that we implement *CLS inheritance*, i.e., when you
# spawn a new task, then all CLS values set in the parent task are (shallowly)
# copied to the child task. This is a bit experimental, but very handy in
# cases like when a request handler spawns some small short-lived worker tasks
# as part of its processing and those want to do logging as well.

import threading
from contextlib import contextmanager

# The thread-local storage slot that points to the context-local storage dict
# for whatever task is currently running.
_current_context_local_storage = threading.local()
_current_context_local_storage.value = None

@contextmanager
def _enable_cls_for(task):
    # Using a full save/restore pattern here is a little paranoid, but
    # safe. Even if someone does something silly like calling curio.run() from
    # inside a curio coroutine.
    old = _current_context_local_storage.value
    try:
        _current_context_local_storage.value = task.context_local_storage
        yield
    finally:
        _current_context_local_storage.value = old

# Called from _trap_spawn to implement CLS inheritance.
def _copy_cls(parent, child):
    # Make a shallow copy of the values associated with each Local object.
    for local, values in parent.context_local_storage.items():
        child.context_local_storage[local] = dict(values)

# Given a Local object, find its associated dict in the current task (creating
# it if necessary.)  Normally would be a method on Local, but __getattribute__
# makes that annoying. This is the simplest workaround.
def _local_dict(local):
    return _current_context_local_storage.value.setdefault(local, {})

class Local:
    def __getattribute__(self, name):
        if name == "__dict__":
            return _local_dict(self)
        try:
            return _local_dict(self)[name]
        except KeyError:
            # "from None" preserves the context, but makes it hidden from
            # tracebacks by default; see PEP 409
            raise AttributeError(name) from None

    def __setattr__(self, name, value):
        _local_dict(self)[name] = value

    def __delattr__(self, name):
        try:
            del _local_dict(self)[name]
        except KeyError:
            # "from None" preserves the context, but makes it hidden from
            # tracebacks by default; see PEP 409
            raise AttributeError(name) from None
