import pytest

from accounts.db.models import Base
from accounts.business.book_service import BookService
from accounts.business.management_service import ManagementService


@pytest.fixture
def db_url():
    # Use an in-memory SQLite database for testing
    return "sqlite:///:memory:"


def test_database_reset(db_url):
    test_book_name = 'test_book_name'
    with BookService(db_url) as service:
        Base.metadata.create_all(service.engine)
        service.create_new_book(test_book_name)
        mgmt_service = ManagementService().init_with_engine(service.engine)
        mgmt_service.reset_database()
        assert not service.get_book_by_name(test_book_name)
