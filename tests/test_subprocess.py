# test_subprocess.py

import sys
from curio import subprocess
from curio import *
import os
import pytest

# ---- Test subprocesses and worker task related functions

executable = sys.executable
dirname = os.path.dirname(__file__)


def test_simple(kernel):
    results = []
    async def subproc():
        # out = await subprocess.run([executable, '-m', 'curio.test.slow'],
        # stdout=subprocess.PIPE)
        out = await subprocess.run([executable, os.path.join(dirname, 'child.py')], stdout=subprocess.PIPE)
        results.append(out.stdout)
        results.append(out.returncode)

    kernel.run(subproc())
    assert results == [
        b't-minus 4\nt-minus 3\nt-minus 2\nt-minus 1\n',
        0,
    ]


def test_simple_check_output(kernel):
    results = []
    async def subproc():
        #        out = await subprocess.check_output([executable, '-m', 'curio.test.slow'])
        out = await subprocess.check_output([executable, os.path.join(dirname, 'child.py')])
        results.append(out)

    kernel.run(subproc())
    assert results == [
        b't-minus 4\nt-minus 3\nt-minus 2\nt-minus 1\n',
    ]


def test_bad_cmd(kernel):
    results = []
    async def subproc():
        try:
            out = await subprocess.run([executable, '-m', 'curio.test.bad'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            results.append('what?')
        except subprocess.CalledProcessError:
            results.append('bad command')

    kernel.run(subproc())
    assert results == ['bad command']


def test_bad_cmd_check_output(kernel):
    results = []
    async def subproc():
        try:
            out = await subprocess.check_output([executable, '-m', 'curio.test.bad'], stderr=subprocess.STDOUT)
            results.append('what?')
        except subprocess.CalledProcessError:
            results.append('bad command')

    kernel.run(subproc())
    assert results == ['bad command']


def test_timeout(kernel):
    results = []
    async def subproc():
        try:
            async with timeout_after(0.5):
                out = await subprocess.run([executable, os.path.join(dirname, 'child.py')], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                results.append('what?')
        except TaskTimeout as e:
            results.append('timeout')
            results.append(e.stdout)
            results.append(e.stderr)

    kernel.run(subproc())
    assert results == ['timeout', b't-minus 4\n', b'']

def test_universal():
    with pytest.raises(RuntimeError):
        p = subprocess.Popen([executable, '-m', 'bad'], universal_newlines=True)

def test_stdin_pipe(kernel):
    async def main():
         p1 = subprocess.Popen([executable, os.path.join(dirname, 'child.py')], stdout=subprocess.PIPE)
         p2 = subprocess.Popen([executable, os.path.join(dirname, 'ichild.py')], stdin=p1.stdout, stdout=subprocess.PIPE)
         out = await p2.stdout.read()
         assert out == b'4\n'

    kernel.run(main())

def test_check_output_stdin(kernel):
    async def main():
         out = await subprocess.check_output([executable, os.path.join(dirname, 'ichild.py')],
                                             input=b'Line1\nLine2\nLine3\n')
         assert out == b'3\n'

    kernel.run(main())

def test_no_input_cancel(kernel):
    async def child():
        p = subprocess.Popen([executable, os.path.join(dirname, 'child.py')], stdin=subprocess.PIPE)
        try:
            out = await p.communicate(input=b'x'*10000000)
            assert False
        except CancelledError as e:
            assert e.stdout == b''
            assert e.stderr == b''
            raise

    async def main():
        t = await spawn(child)
        await sleep(0.1)
        await t.cancel()
        
    kernel.run(main())

def test_popen_join(kernel):
    async def main():
         p = subprocess.Popen([executable, '-c', 'import time;time.sleep(1)'])
         code = await p.wait()
         assert code == 0

    kernel.run(main)

def test_io_error(kernel):
    async def main():
         with pytest.raises(BrokenPipeError):
             out = await subprocess.check_output([executable, '-c', 'import sys, time; sys.stdin.close(); time.sleep(1)'],
                                           input=b'x'*10000000)

    kernel.run(main)


         
