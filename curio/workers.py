# curio/workers.py
#
# Various functions/classes for performing work outside of curio.  This includes
# subprocesses, running in executors, etc.

from .kernel import future_wait, new_task, sleep
from .file import File
import subprocess
import os

__all__ = [ 'run_in_executor', 'Popen' ]

async def run_in_executor(exc, callable, *args):
    '''
    Run a callable in an executor (e.g., concurrent.futures.ThreadPoolExecutor) and return the result.
    '''
    future = exc.submit(callable, *args)
    await future_wait(future)
    return future.result()

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

        async def feeder(input, fileobj):
            await fileobj.write(input)
            fileobj.close()

        async def reader(fileobj):
            if not fileobj:
                return b''

            chunks = []
            while True:
                 chunk = await fileobj.read(1000000)
                 if not chunk:
                     break
                 chunks.append(chunk)
            return b''.join(chunks)

        if input:
            await new_task(feeder(input, self.stdin))

        stdout_task = await new_task(reader(self.stdout))
        stderr_task = await new_task(reader(self.stderr))

        # Collect the output
        stdout = await stdout_task.join()
        stderr = await stderr_task.join()
        return (stdout, stderr)

async def run_subprocess(args, *, stdin=None, input=None, stdout=None, stderr=None, 
                         shell=False, timeout=None, check=False):

    assert (stdin is not None and input is not None), "Can't specify both stdin and input"
    




    
