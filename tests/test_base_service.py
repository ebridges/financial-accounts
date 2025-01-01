import pytest
from accounts.business.base_service import BaseService

@pytest.fixture
def db_url():
    # Use an in-memory SQLite database for testing
    return "sqlite:///:memory:"

def test_base_service_initialization(db_url):
    with BaseService(db_url) as service:
        assert service.engine is not None
        assert service.SessionLocal is not None
        assert service.data_access is not None

def test_session_management(db_url):
    with BaseService(db_url) as service:
        session = service.session
        assert session.is_active
        session.close()
        assert not session.is_active
