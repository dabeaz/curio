# curio/util.py

import sys

__all__ = ["aiter_compat_hack"]

# Python 3.5.0 and 3.5.1 want __aiter__ to be an async method, while
# 3.5.2+ want it to be a regular method. See:
#    https://www.python.org/dev/peps/pep-0492/#api-design-and-implementation-revisions
# So: we write it as a regular method, and decorate with this thing to make it
# work on older Pythons.
def aiter_compat_hack(sync__aiter__):
    if sys.version_info < (3, 5, 2):
        async def __aiter__(self):
            return sync__aiter__(self)
        __aiter__.__qualname__ = sync__aiter__.__qualname__
        return __aiter__
    else:
        return sync__aiter__
