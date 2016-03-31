# test_subprocess.py

import sys
from curio import subprocess
from curio import *
import os

# ---- Test subprocesses and worker task related functions

executable = sys.executable
dirname = os.path.dirname(__file__)

def test_simple(kernel):
    results = []
    async def subproc():
#        out = await subprocess.run([executable, '-m', 'curio.test.slow'], stdout=subprocess.PIPE)
        out = await subprocess.run([executable, os.path.join(dirname, 'child.py')], stdout=subprocess.PIPE)
        results.append(out.stdout)
        results.append(out.returncode)

    kernel.add_task(subproc())
    kernel.run()
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

    kernel.add_task(subproc())
    kernel.run()
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

    kernel.add_task(subproc())
    kernel.run()
    assert results == ['bad command']

def test_bad_cmd_check_output(kernel):
    results = []
    async def subproc():
        try:
            out = await subprocess.check_output([executable, '-m', 'curio.test.bad'], stderr=subprocess.STDOUT)
            results.append('what?')
        except subprocess.CalledProcessError:
            results.append('bad command')

    kernel.add_task(subproc())
    kernel.run()
    assert results == [ 'bad command' ]

def test_timeout(kernel):
    results = []
    async def subproc():
        try:
#            out = await subprocess.run([executable, '-m', 'curio.test.slow'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1)
            out = await subprocess.run([executable, os.path.join(dirname, 'child.py')], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1)
            results.append('what?')
        except subprocess.TimeoutExpired:
            results.append('timeout')

    kernel.add_task(subproc())
    kernel.run()
    assert results == [ 'timeout' ]
