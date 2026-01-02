# Common test fixtures shared across test files.
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_dal():
    """Create mock data access layer with common defaults."""
    dal = MagicMock()
    dal.list_accounts_for_book.return_value = []
    dal.create_account.return_value = MagicMock(id=1)
    return dal


@pytest.fixture
def mock_book():
    """Create mock book."""
    return MagicMock(id=1, name='Test Book')


@pytest.fixture
def mock_ctx(mock_dal, mock_book):
    """Create mock BookContext with common defaults."""
    ctx = MagicMock()
    ctx.book = mock_book
    ctx.dal = mock_dal
    ctx.accounts = MagicMock()
    ctx.transactions = MagicMock()
    return ctx
