# curio/workers.py
#
# Various functions/classes for performing work outside of curio.  This includes
# subprocesses, running in executors, etc.

from .kernel import future_wait, new_task, sleep
from .file import File
import subprocess
import os

__all__ = [ 'run_in_executor', 'run_subprocess' ]

from subprocess import (
    CompletedProcess,
    CalledProcessError,
    TimeoutExpired
    )

async def run_in_executor(exc, callable, *args):
    '''
    Run a callable in an executor (e.g., concurrent.futures.ThreadPoolExecutor) and return the result.
    '''
    future = exc.submit(callable, *args)
    await future_wait(future)
    return future.result()

async def run_blocking(callable, *args, **kwargs):
    pass

async def run_cpu_bound(callable, *args, **kwargs):
    pass

class Popen(object):
    '''
    Curio wrapper around the Popen class from the subprocess module.
    '''
    def __init__(self, *args, bufsize=0, **kwargs):
        self._popen = subprocess.Popen(*args, bufsize=bufsize, **kwargs)
        if self._popen.stdin:
            os.set_blocking(self._popen.stdin.fileno(), False)
            self.stdin = File(self._popen.stdin)
        if self._popen.stdout:
            os.set_blocking(self._popen.stdout.fileno(), False)
            self.stdout = File(self._popen.stdout)
        if self._popen.stderr:
            os.set_blocking(self._popen.stderr.fileno(), False)
            self.stderr = File(self._popen.stderr)

    def __getattr__(self, name):
        return getattr(self._popen, name)

    async def wait(self):
        while True:
            retcode = self._popen.poll()
            if retcode is not None:
                return retcode
            await sleep(0.0005)

    async def communicate(self, input=b'', timeout=None):
        if input:
            assert self.stdin
            stdin_task = await new_task(self.stdin.write(input, close_on_complete=True))
        else:
            stdin_task = None

        stdout_task = await new_task(self.stdout.readall())
        stderr_task = await new_task(self.stderr.readall())

        # Collect the output from the workers
        try:
            stdout = await stdout_task.join(timeout=timeout)
            stderr = await stderr_task.join(timeout=timeout)
            return (stdout, stderr)
        except TimeoutError:
            await stdout_task.cancel()
            await stderr_task.cancel()
            if stdin_task:
                await stdin_task.cancel()
            raise

async def run_subprocess(args, *, input=None, timeout=None, shell=False, stderr=subprocess.PIPE):
    if input:
        stdin = subprocess.PIPE
    else:
        stdin = None

    process = Popen(args, stdin=stdin, stdout=subprocess.PIPE, stderr=stderr, shell=shell)
    try:
        stdout, stderr = await process.communicate(input, timeout)
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        raise TimeoutExpired(process.args, timeout, output=stdout, stderr=stderr)
    except:
        process.kill()
        await process.wait()
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
        if process.stdin:
            process.stdin.close()

    retcode = process.poll()
    if retcode:
        raise CalledProcessError(retcode, process.args,
                                 output=stdout, stderr=stderr)
    return CompletedProcess(process.args, retcode, stdout, stderr)

    
