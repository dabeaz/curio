import pytest
from curio import Kernel
from curio.monitor import Monitor

@pytest.fixture(scope='session')
def kernel(request):
    k = Kernel()
    m = Monitor(k)
    request.addfinalizer(lambda: k.run(shutdown=True))
    request.addfinalizer(m.close)
    return k
