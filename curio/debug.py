# curio/debug.py
#
# Task debugging tools

__all__ = [ 'longblock', 'schedtrace' ]

import time
import logging
log = logging.getLogger(__name__)

# -- Curio

from .activation import ActivationBase

class DebugBase(ActivationBase):
    pass

class longblock(DebugBase):
    '''
    Report warnings for tasks that block the event loop for a long duration.
    '''
    def __init__(self, *, max_time=0.05, level=logging.WARNING):
        self.max_time = max_time
        self.level = level

    def scheduled(self, task):
        self.start = time.monotonic()

    def suspended(self, task, exc):
        duration = time.monotonic() - self.start
        if duration > self.max_time:
            log.log(self.level, 'Task id=%d (%s) ran for %s seconds' % (task.id, task, duration))

class schedtrace(DebugBase):
    '''
    Report when tasks get scheduled.
    '''
    def __init__(self, *, level=logging.INFO, **kwargs):
        self.level = level

    def scheduled(self, task):
        log.log(self.level, 'SCHEDULE:%f:%d:%s', time.time(), task.id, task)


def create_debuggers(debug):
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


    
        
        
        
