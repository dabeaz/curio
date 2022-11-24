import curio
import inspect
import unittest


class CurioTestCase(unittest.TestCase):
	def __init__(self, methodName='runTest'):
		super().__init__(methodName)
		self._kernel = None

	async def asyncSetUp(self):
		pass

	async def asyncTearDown(self):
		pass

	def addAsyncCleanup(self, func, *args, **kwargs):
		self.addCleanup(*(func, *args), **kwargs)

	async def enterAsyncContext(self, cm):
		super().enterAsyncContext(cm)

	def _callSetUp(self):
		self.setUp()
		self._call_async(self.asyncSetUp)

	def _callTestMethod(self, method):
		self._call_maybe_async(method)

	def _callTearDown(self):
		self._call_async(self.asyncTearDown)
		self.tearDown()

	def _callCleanup(self, function, *args, **kwargs):
		self._call_maybe_async(function, *args, **kwargs)

	def _call_async(self, func, *args, **kwargs):
		assert self._kernel is not None, 'curio kernel is not initialized'
		err_msg = f'{func!r} is not an async function'
		assert inspect.iscoroutinefunction(func), err_msg
		return self._kernel.run(
			func(*args, **kwargs),
		)

	def _call_maybe_async(self, func, *args, **kwargs):
		if inspect.iscoroutinefunction(func):
			return self._kernel.run(
				func(*args, **kwargs),
			)
		else:
			return func(*args, **kwargs)

	def _setup_curio_kernel(self):
		assert self._kernel is None, 'curio kernel is already initialized'
		kernel = curio.Kernel()
		self._kernel = kernel

	def _tear_down_curio_kernel(self):
		kernel = self._kernel
		kernel.run(self._shutdown, shutdown=True)

	async def _shutdown(self):
		pass

	def run(self, result=None):
		self._setup_curio_kernel()
		try:
			return super().run(result)
		finally:
			self._tear_down_curio_kernel()

	def debug(self):
		super().debug()

	def __del__(self):
		if self._kernel._shutdown_funcs is not None:
			self._tear_down_curio_kernel()
