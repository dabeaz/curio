import sys
import pytest
from curio import Kernel
from curio.monitor import Monitor
from curio.debug import *

@pytest.fixture(scope='session')
def kernel(request):
    k = Kernel(debug=[longblock, logcrash, schedtrace, traptrace])
    m = Monitor(k)
    request.addfinalizer(lambda: k.run(shutdown=True))
    request.addfinalizer(m.close)
    return k

collect_ignore = []
if sys.version_info < (3,6):
    collect_ignore.append("test_asyncgen.py")

