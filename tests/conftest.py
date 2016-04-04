import pytest
from curio import Kernel

@pytest.fixture(scope='session')
def kernel(request):
    k = Kernel()
    request.addfinalizer(k.shutdown)
    return k
