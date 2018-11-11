import socket
import sys
import pytest
from curio import Kernel
from curio.monitor import Monitor
from curio.debug import *

@pytest.fixture(scope='session')
def kernel(request):
    k = Kernel(debug=[longblock, logcrash])
    m = Monitor(k)
    request.addfinalizer(lambda: k.run(shutdown=True))
    request.addfinalizer(m.close)
    return k


# This is based on https://unix.stackexchange.com/a/132524
@pytest.fixture(scope='function')
def portno():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    _, port = s.getsockname()
    s.close()
    return port

collect_ignore = []
if sys.version_info < (3,6):
    collect_ignore.append("test_asyncgen.py")

