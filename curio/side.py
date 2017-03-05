# curio/side.py
#
# Main program that runs to handle the aside() functionality.

# -- Standard library 
import base64
import pickle
import sys
import types
import signal

# -- Curio

from . import task
from .errors import CancelledError

# Signal handling task in the child process
async def _aside_term(task):
    from . import signal as curio_signal
    await curio_signal.SignalSet(signal.SIGTERM).wait()
    raise SystemExit(1)

# Task that runs the requested coroutine
async def _aside_child(coro, args):
    self_task = await task.current_task()
    await task.spawn(_aside_term, self_task, daemon=True)
    await coro(*args)
    return 0

def main(argv):
    from .kernel import run
    filename = argv[1]
    if filename:
        mod = types.ModuleType('curio.aside')
        code = open(filename).read()
        exec(code, mod.__dict__, mod.__dict__)
        sys.modules['__main__'] = mod
    (corofunc, args) = pickle.loads(base64.b64decode(sys.argv[2]))
    try:
        run(_aside_child(corofunc, args))
    except CancelledError as e:
        raise SystemExit(1)

if __name__ == '__main__':
    main(sys.argv)
