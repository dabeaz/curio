import pytest

import curio


@pytest.mark.filterwarnings('error::pytest.PytestUnhandledCoroutineWarning')
@pytest.mark.curio
async def test_coroutine_test():
    await curio.sleep(0)
