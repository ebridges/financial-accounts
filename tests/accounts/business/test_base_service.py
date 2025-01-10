import pytest
from financial_accounts.business.base_service import BaseService


@pytest.fixture
def db_url():
    # Use an in-memory SQLite database for testing
    return "sqlite:///:memory:"


def test_base_service_initialization(db_url):
    with BaseService.init_with_url(db_url) as service:
        assert service.engine is not None
        assert service.SessionLocal is not None
        assert service.data_access is not None
