import ast
import curio
import code
import inspect
import sys
import types
import warnings
import threading

class CurioIOInteractiveConsole(code.InteractiveConsole):

    def __init__(self, locals):
        super().__init__(locals)
        self.compile.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        self.requests = curio.UniversalQueue()
        self.response = curio.UniversalQueue()

    def runcode(self, code):
        async def run_it():
            func = types.FunctionType(code, self.locals)
            try:
                coro = func()
            except BaseException as ex:
                await self.response.put((None, ex))
                return
            if not inspect.iscoroutine(coro):
                await self.response.put((coro, None))
                return
            try:
                result = await coro
                await self.response.put((result, None))
            except SystemExit:
                raise
            except BaseException as ex:
                await self.response.put((None, ex))
            

        self.requests.put(run_it())
        # Get the result here...
        result, exc = self.response.get()
        if exc is not None:
            try:
                raise exc
            except BaseException:
                self.showtraceback()
        else:
            return result

    # Task that runs in the main thread, executing input fed to it from above
    async def runmain(self):
        while True:
            coro = await self.requests.get()
            if coro is None:
                break
            await coro

def run_repl(console):
    try:
        banner = (
            f'curio REPL {sys.version} on {sys.platform}\n'
            f'Use "await" directly instead of "curio.run()".\n'
            f'Type "help", "copyright", "credits" or "license" '
            f'for more information.\n'
            f'{getattr(sys, "ps1", ">>> ")}import curio'
            )
        console.interact(
            banner=banner,
            exitmsg='exiting curio REPL...')
    finally:
        warnings.filterwarnings(
            'ignore',
            message=r'^coroutine .* was never awaited$',
            category=RuntimeWarning)
        console.requests.put(None)
    
if __name__ == '__main__':
    repl_locals = { 'curio': curio }
    for key in {'__name__', '__package__',
                '__loader__', '__spec__',
                '__builtins__', '__file__'}:
        repl_locals[key] = locals()[key]

    console = CurioIOInteractiveConsole(repl_locals)
    threading.Thread(target=run_repl, args=[console], daemon=True).start()
    curio.run(console.runmain)
