# curio/local.py
#
# Task local storage

# Our public API is intentionally almost identical to that of threading.local:
# the user allocates a curio.Local() object, and then can attach arbitrary
# attributes to it. Reading one of these attributes later will return the last
# value that was assigned to this attribute *by code running inside the same
# Task*.
#
# Internally, each Task has an attribute .task_local_storage, which holds a
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
#  (await curio.current_task()).task_local_storage
#
# But, we also want to be able to access this from synchronous context,
# because one of the major use cases for this is tagging log messages with
# context, and there are lots of legacy third-party libraries that use the
# Python stdlib logging module. And it's synchronous. So if you want to
# capture their logs and feed them into something better and more context-ful,
# then you need to be able to get that context from synchronous-land.
#
# Therefore, whenever we resume a task, we stash a pointer to its
# .task_local_storage dictionary in a global *thread*-local variable. Then
# when we want to find a specific variable (local_obj.attr), we ultimately
# look in
#
#  _current_task_local_storage.value[local_obj]["attr"]
#
# An unusual feature of this implementation (and our main deviation from
# threading.Local) is that we implement *task local inheritance*, i.e., when
# you spawn a new task, then all task local values set in the parent task
# are (shallowly) copied to the child task.
# This is a bit experimental, but very handy in cases like when a request
# handler spawns some small short-lived worker tasks as part of its processing
# and those want to do logging as well.

import threading
from contextlib import contextmanager


__all__ = ["Local"]

# The thread-local storage slot that points to the task-local storage dict for
# whatever task is currently running.
_current_task_local_storage = threading.local()
_current_task_local_storage.value = None


@contextmanager
def _enable_tasklocal_for(task):
    # Using a full save/restore pattern here is a little paranoid, but
    # safe. Even if someone does something silly like calling curio.run() from
    # inside a curio coroutine.
    old = _current_task_local_storage.value
    try:
        _current_task_local_storage.value = task.task_local_storage
        yield
    finally:
        _current_task_local_storage.value = old


# Called from _trap_spawn to implement task local inheritance.
def _copy_tasklocal(parent, child):
    # Make a shallow copy of the values associated with each Local object.
    for local, values in parent.task_local_storage.items():
        child.task_local_storage[local] = dict(values)


# Given a Local object, find its associated dict in the current task (creating
# it if necessary.)  Normally would be a method on Local, but __getattribute__
# makes that annoying. This is the simplest workaround.
def _local_dict(local):
    # forbid accessing attributes when no task is running, which is equivalent
    # to using task local outside of any asynchronous code
    if _current_task_local_storage.value is None:
        raise RuntimeError('Accessing task local outside of the task context')
    return _current_task_local_storage.value.setdefault(local, {})


# make self.__dict__ point to the current task local storage
def _patch_magic_dict(self):
    object.__setattr__(self, '__dict__', _local_dict(self))


class Local:

    __slots__ = '__dict__',

    def __getattribute__(self, name):
        _patch_magic_dict(self)
        return object.__getattribute__(self, name)

    def __setattr__(self, name, value):
        _patch_magic_dict(self)
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        _patch_magic_dict(self)
        return object.__delattr__(self, name)
