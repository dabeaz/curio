#!/usr/bin/env python3.5

"""
Debugger helper module.
"""

import os
import sys

class _DebuggerLoader:
    """Loader for custom debugger. Replaces itself on first access.

    The PYTHON_DEBUGGER environment variable should name a module with a
    post_mortem(tb) method.
    """
    def __getattr__(self, name):
        global debugger
        modname = os.environ.get("PYTHON_DEBUGGER", "pdb")
        __import__(modname)
        debugger = sys.modules[modname]
        return getattr(debugger, name)


debugger = _DebuggerLoader()


def post_mortem(tb=None):
    if tb is None:
        tb = sys.exc_inf()[2]
    if tb is None:
        raise ValueError("A valid traceback is required if no "
                         "exception is being handled.")
    debugger.post_mortem(tb)

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
