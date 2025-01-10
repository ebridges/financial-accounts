import pytest
from unittest.mock import MagicMock
from financial_accounts.business.book_service import BookService


@pytest.fixture
def book_service():
    service = BookService().init_with_url(db_url="sqlite:///:memory:")
    service.data_access = MagicMock()
    return service


def test_create_new_book(book_service):
    book_service.data_access.get_book_by_name.return_value = None
    book_service.data_access.create_book.return_value = MagicMock(id=1)

    book = book_service.create_new_book("New Book")
    assert book.id == 1
