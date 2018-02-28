# test_activation.py

from curio.activation import Activation
from curio import Kernel, sleep, run

class _TestActivation(Activation):
    def __init__(self):
        self.events = []

    def activate(self, kernel):
        self.events.append('activate')

    def created(self, task):
        if task.name.endswith('main'):
            self.events.append('created')

    def running(self, task):
        if task.name.endswith('main'):
            self.events.append('running')

    def suspended(self, task):
        if task.name.endswith('main'):
            self.events.append('suspended')

    def terminated(self, task):
        if task.name.endswith('main'):
            self.events.append('terminated')

def test_activation_base():
    async def main():
        await sleep(0.01)
        await sleep(0.01)
        await sleep(0.01)

    a = _TestActivation()
    run(main, activations=[a])
    assert a.events == ['activate', 'created', 'running', 'suspended', 'running', 'suspended',
                       'running', 'suspended', 'running', 'suspended', 'terminated']

def test_activation_crash():
    async def main():
        await sleep(0.01)
        raise ValueError("Dead")

    a = _TestActivation()
    kern = Kernel(activations=[a])
    try:
        kern.run(main)
        assert False
    except ValueError as e:
        assert a.events == ['activate', 'created', 'running', 'suspended', 'running', 'suspended', 'terminated']

    kern.run(shutdown=True)
