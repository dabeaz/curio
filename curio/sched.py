# curio/sched.py
#
# Implementation of kernel-level scheduling primitives.   These are used
# to implement low-level task scheduling operations and are the basis
# upon which higher-level synchronization primitives such as Events, Locks,
# and Semaphores are built.   End-users of Curio would not use these
# primitives directly--they would use higher level functionality such
# as that in the curio/sync.py file.

# -- Standard Library

from abc import ABC, abstractmethod
from collections import deque

class SchedBase(ABC):

    @abstractmethod
    def __len__(self):
        pass

    @abstractmethod
    def add(self, task):
        '''
        Adds a new task.  This method *must* return a zero-argument
        callable that can be used to remove the just added task
        '''
        pass

    @abstractmethod
    def pop(self, ntasks=1):
        '''
        Pop one or more task.  Returns a list of the removed tasks.
        '''
        pass


# Scheduler FIFO queue with soft-delete on task cancellation.
# On cancellation, a placeholder is left in the queue, but it will
# be removed on subsequent pop operations.

class SchedFIFO(SchedBase):

    def __init__(self):
        self._queue = deque()
        self._actual_len = 0

    def __len__(self):
        return self._actual_len

    def add(self, task):
        item = [task]
        self._queue.append(item)
        self._actual_len += 1

        def remove():
            item[0] = None
            self._actual_len -= 1
        return remove

    def pop(self, ntasks=1):
        tasks = []
        while ntasks > 0:
            task, = self._queue.popleft()
            if task:
                tasks.append(task)
                ntasks -= 1
        self._actual_len -= len(tasks)
        return tasks


# Scheduler Barrier.  Keeps an unordered set of waiting tasks. Cancellation
# removes a task from the set.  Rescheduling removes an arbitrary task
# and reschedules it.

class SchedBarrier(SchedBase):

    def __init__(self):
        self._tasks = set()

    def __len__(self):
        return len(self._tasks)

    def add(self, task):
        self._tasks.add(task)
        return lambda: self._tasks.remove(task)

    def pop(self, ntasks=1):
        if ntasks == len(self._tasks):
            result = list(self._tasks)
            self._tasks.clear()
        else:
            result = [self._tasks.pop() for _ in range(ntasks)]
        return result
