import pytest
from roledock.runtime import RoleDock
from roledock.security import DEMO_IDENTITIES


@pytest.fixture
def service():
    return RoleDock()


@pytest.fixture
def principals():
    return {p.role: p for p in DEMO_IDENTITIES.values()}
