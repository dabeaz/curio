# curio/test/workers.py

import unittest
from .. import subprocess
from ..kernel import *

# ---- Test subprocesses and worker task related functions

class TestSubprocess(unittest.TestCase):
    def test_simple(self):
        kernel = get_kernel()
        results = []
        async def subproc():
            out = await subprocess.run(['python3', '-m', 'curio.test.slow'], stdout=subprocess.PIPE)
            results.append(out.stdout)
            results.append(out.returncode)

        kernel.add_task(subproc())
        kernel.run()
        self.assertEqual(results, [
                b't-minus 4\nt-minus 3\nt-minus 2\nt-minus 1\n',
                0,
                ])

    def test_simple_check_output(self):
        kernel = get_kernel()
        results = []
        async def subproc():
            out = await subprocess.check_output(['python3', '-m', 'curio.test.slow'])
            results.append(out)

        kernel.add_task(subproc())
        kernel.run()
        self.assertEqual(results, [
                b't-minus 4\nt-minus 3\nt-minus 2\nt-minus 1\n',
                ])

    def test_bad_cmd(self):
        kernel = get_kernel()
        results = []
        async def subproc():
            try:
                out = await subprocess.run(['python3', '-m', 'curio.test.bad'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                results.append('what?')
            except subprocess.CalledProcessError:
                results.append('bad command')

        kernel.add_task(subproc())
        kernel.run()
        self.assertEqual(results, [ 'bad command' ])

    def test_bad_cmd_check_output(self):
        kernel = get_kernel()
        results = []
        async def subproc():
            try:
                out = await subprocess.check_output(['python3', '-m', 'curio.test.bad'], stderr=subprocess.STDOUT)
                results.append('what?')
            except subprocess.CalledProcessError:
                results.append('bad command')

        kernel.add_task(subproc())
        kernel.run()
        self.assertEqual(results, [ 'bad command' ])

    def test_timeout(self):
        kernel = get_kernel()
        results = []
        async def subproc():
            try:
                out = await subprocess.run(['python3', '-m', 'curio.test.slow'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1)
                results.append('what?')
            except subprocess.TimeoutExpired:
                results.append('timeout')

        kernel.add_task(subproc())
        kernel.run()
        self.assertEqual(results, [ 'timeout' ])

if __name__ == '__main__':
    unittest.main()
