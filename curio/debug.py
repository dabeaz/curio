# curio/debug.py
#
# Task debugging tools

__all__ = [ 'longblock', 'schedtrace', 'traptrace', 'logcrash' ]

import time
import logging
log = logging.getLogger(__name__)

# -- Curio

from .activation import ActivationBase, trap_patch
from .traps import Traps

class DebugBase(ActivationBase):
    def __init__(self, level=logging.INFO, filter=None, **kwargs):
        self.level = level
        self.filter = filter

    def check_filter(self, task):
        if self.filter and task.name not in self.filter:
            return False
        return True

class longblock(DebugBase):
    '''
    Report warnings for tasks that block the event loop for a long duration.
    '''
    def __init__(self, *, max_time=0.05, level=logging.WARNING, **kwargs):
        super().__init__(level=level, **kwargs)
        self.max_time = max_time

    def running(self, task):
        if self.check_filter(task):
            self.start = time.monotonic()

    def suspended(self, task, exc):
        if self.check_filter(task):
            duration = time.monotonic() - self.start
            if duration > self.max_time:
                log.log(self.level, 'Task id=%d (%s) ran for %s seconds', task.id, task, duration)

class logcrash(DebugBase):
    '''
    Report tasks that crash with an uncaught exception
    '''
    def __init__(self, level=logging.ERROR, **kwargs):
        super().__init__(level=level, **kwargs)

    def suspended(self, task, exc):
        if exc and self.check_filter(task):
            if not isinstance(exc, StopIteration):
                log.log(self.level, 'Task %r crashed', task.id, exc_info=exc)

class schedtrace(DebugBase):
    '''
    Report when tasks run
    '''
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def running(self, task):
        if self.check_filter(task):
            log.log(self.level, 'SCHEDULE:%f:%d:%s', time.time(), task.id, task)

class traptrace(schedtrace):
    '''
    Report traps executed
    '''
    def __init__(self, *, traps=None, **kwargs):
        super().__init__(**kwargs)
        self.traps = traps
        self.report = False

    def activate(self, kernel):
        for trapno in Traps:
            if self.traps and trapno not in self.traps:
                continue

            @trap_patch(kernel, trapno)
            def trapfunc(*args, trap, trapno=trapno):
                if self.report:
                    log.log(self.level, 'TRAP:%f:%s:%r', 
                            time.time(),
                            trapno,
                            args)
                return trap(*args)

    def running(self, task):
        super().running(task)
        if self.check_filter(task):
            self.report = True

    def suspended(self, task, exc):
        self.report = False


def _create_debuggers(debug):
    '''
    Create debugger objects.  Called by the kernel to instantiate the objects.
    '''
    if debug is None:
        return []

    if debug is True:
        # Set a default set of debuggers
        debug = [ schedtrace ]

    elif not isinstance(debug, (list, tuple)):
        debug = [ debug ]

    # Create instances
    debug = [ (d() if (isinstance(d, type) and issubclass(d, DebugBase)) else d)
              for d in debug ]
    return debug


    
        
        
        
