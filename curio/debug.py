# curio/debug.py
#
# Task debugging tools

import time
import logging

log = logging.getLogger(__name__)

class DebugBase:
    def schedule(self, task):
        pass

    def suspend(self, task, exc):
        pass

    def trap(self, trapno, args):
        pass

class longblock(DebugBase):
    '''
    Report warnings for tasks that block the event loop for a long duration.
    '''
    def __init__(self, max_time=0.05, level=logging.WARNING):
        self.max_time = max_time
        self.level = level

    def schedule(self, task):
        self.start = time.monotonic()

    def suspend(self, task, exc):
        duration = time.monotonic() - self.start
        if duration > self.max_time:
            log.log(self.level, 'Task %r ran for %s seconds' % (task, duration))

class schedtrace(DebugBase):
    '''
    Report when tasks get scheduled.
    '''
    def schedule(self, task):
        log.info('SCHEDULE:%f:%d:%s', time.time(), task.id, task)

class traptrace(DebugBase):
    '''
    Report traps
    '''
    def trap(self, trapno, args):
        log.info('TRAP:%r:%s', trapno, args)


def create_debuggers(debug):
    if debug is None:
        return None

    if debug is True:
        # Set a default set of debuggers
        debug = [ schedtrace ]

    elif not isinstance(debug, (list, tuple)):
        debug = [ debug ]

    # Create instances
    debug = [ (d() if (isinstance(d, type) and issubclass(d, DebugBase)) else d)
              for d in debug ]
    return debug


    
        
        
        
