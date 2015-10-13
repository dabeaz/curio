# curio/queue.py

__all__ = [ 'Queue', 'QueueEmpty', 'QueueFull' ]

class QueueEmpty(Exception):
    pass

class QueueFull(Exception):
    pass

class Queue(object):
    pass
