# curio/side.py
#
# Main program that runs to handle the aside() functionality.

import base64
import inspect
import pickle
import sys
import types

from . import task
from .errors import CancelledError, TaskError

# Signal handling task in the child process
async def _aside_term(task):
    from . import signal as curio_signal
    import signal as std_signal

    await curio_signal.SignalSet(std_signal.SIGTERM).wait()
    await task.cancel()

# Task that runs the requested coroutine
async def _aside_child(coro, args, kwargs):
    self_task = await task.current_task()
    await task.spawn(_aside_term(self_task), daemon=True)
    await coro(*args, **kwargs)
    return 0
    
if __name__ == '__main__':
    from .kernel import run
    filename = sys.argv[1]
    if filename:
        mod = types.ModuleType('curio.aside')
        code = open(filename).read()
        exec(code, mod.__dict__, mod.__dict__)
        sys.modules['__main__'] = mod
    (corofunc, args, kwargs) = pickle.loads(base64.b64decode(sys.argv[2]))
    try:
        run(_aside_child(corofunc, args, kwargs))
    except CancelledError as e:
        raise SystemExit(1)



