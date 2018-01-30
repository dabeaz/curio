# curio/sched.py
#
# Implementation of kernel-level scheduling primitives.  These are
# used to implement low-level task scheduling operations and are the
# basis upon which higher-level synchronization primitives such as
# Events, Locks, and Semaphores are built.  End-users of Curio should
# not use these primitives directly--they would use higher level
# functionality such as that in the curio/sync.py file.  

# -- Standard Library

from abc import ABC, abstractmethod
from collections import deque

class SchedBase(ABC):     # pragma: no cover

    @abstractmethod
    def __len__(self):
        pass

    @abstractmethod
    def add(self, task):
        # Adds a new task.  This method *must* return a zero-argument
        # callable that removes the just added task.
        pass

    @abstractmethod
    def pop(self, ntasks=1):
        # Remove one or more task.  Returns a list of the removed tasks
        pass


# Scheduler FIFO queue.  This is used to implement locks and queues.
# Task cancellation results in a soft-delete where a placeholder is
# left on the queue, but is removed when encountered on subsequent pop
# operations.

class SchedFIFO(SchedBase):

    def __init__(self):
        self._queue = deque()
        self._actual_len = 0


    def __len__(self):
        return self._actual_len

    def add(self, task):
        # The task is placed inside a 1-item list.  If cancelled, the
        # task is replaced by None, but the list remains on the queue
        # until later pop operations discard it
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


# Scheduler Barrier.  This is used to implement Events.  Keeps an
# unordered set of waiting tasks. Cancellation removes a task from the
# set.  Popping removes an arbitrary task and reschedules it.

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
