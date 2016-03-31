import pytest
from curio import Kernel

@pytest.fixture(scope='session')
def kernel(request):
    print("Initializing kernel")
    k = Kernel()
    request.addfinalizer(k.shutdown)
    return k
