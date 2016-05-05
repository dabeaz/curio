# curio/subprocess.py
#
# A curio-compatible standin for the subprocess module.  Provides
# asynchronous compatible versions of Popen(), check_output(),
# and run() functions.

__all__ = [ 'run', 'Popen', 'CompletedProcess', 'CalledProcessError',
            'TimeoutExpired', 'SubprocessError', 'check_output',
            'PIPE', 'STDOUT', 'DEVNULL' ]

import subprocess

from subprocess import (
    CompletedProcess,
    SubprocessError, 
    CalledProcessError,
    TimeoutExpired,
    PIPE,
    STDOUT,
    DEVNULL,
    )

from .task import spawn, sleep, timeout_after
from .errors import TaskTimeout
from .io import FileStream

class Popen(object):
    '''
    Curio wrapper around the Popen class from the subprocess module. All of the
    methods from subprocess.Popen should be available, but the associated file
    objects for stdin, stdout, stderr have been replaced by async versions.
    Certain blocking operations (e.g., wait() and communicate()) have been
    replaced by async compatible implementations.
    '''
    def __init__(self, args, **kwargs):
        if 'universal_newlines' in kwargs:
            raise RuntimeError('universal_newlines argument not supported')

        self._popen = subprocess.Popen(args, **kwargs)
        if self._popen.stdin:
            self.stdin = FileStream(self._popen.stdin)
        if self._popen.stdout:
            self.stdout = FileStream(self._popen.stdout)
        if self._popen.stderr:
            self.stderr = FileStream(self._popen.stderr)

    def __getattr__(self, name):
        return getattr(self._popen, name)

    async def wait(self, timeout=None):
        async def waiter():
            while True:
                retcode = self._popen.poll()
                if retcode is not None:
                    return retcode
                await sleep(0.0005)
        task = await spawn(waiter())
        try:
            return await timeout_after(timeout, task.join())
        except TaskTimeout:
            await task.cancel()
            raise TimeoutExpired(self.args, timeout) from None

    async def communicate(self, input=b'', timeout=None):
        stdout_task = await spawn(self.stdout.readall()) if self.stdout else None
        stderr_task = await spawn(self.stderr.readall()) if self.stderr else None
        try:
            if input:
                await timeout_after(timeout, self.stdin.write(input))
                await self.stdin.close()
                self.stdin = None

            # Collect the output from the workers
            stdout = await timeout_after(timeout, stdout_task.join()) if stdout_task else b''
            stderr = await timeout_after(timeout, stderr_task.join()) if stderr_task else b''
            return (stdout, stderr)
        except TaskTimeout:
            await stdout_task.cancel()
            await stderr_task.cancel()
            raise

    def __enter__(self):
        raise RuntimeError('Use async with')

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self.stdout:
            await self.stdout.close()

        if self.stderr:
            await self.stderr.close()

        if self.stdin:
            await self.stdin.close()

        # Wait for the process to terminate
        await self.wait()

async def run(args, *, stdin=None, input=None, stdout=None, stderr=None, shell=False, timeout=None, check=False):
    '''
    Curio-compatible version of subprocess.run()
    '''
    if input:
        stdin = subprocess.PIPE
    else:
        stdin = None

    async with Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, shell=shell) as process:
        try:
            stdout, stderr = await process.communicate(input, timeout)
        except TaskTimeout:
            process.kill()
            stdout, stderr = await process.communicate()
            raise TimeoutExpired(process.args, timeout, output=stdout, stderr=stderr)
        except:
            process.kill()
            raise

    retcode = process.poll()
    if check and retcode:
        raise CalledProcessError(retcode, process.args,
                                 output=stdout, stderr=stderr)
    return CompletedProcess(process.args, retcode, stdout, stderr)

async def check_output(args, *, stdin=None, stderr=None, shell=False, input=None, timeout=None):
     '''
     Curio compatible version of subprocess.check_output()
     '''
     out = await run(args, stdout=PIPE, stdin=stdin, stderr=stderr, shell=shell, 
                     timeout=timeout, check=True, input=input)
     return out.stdout
