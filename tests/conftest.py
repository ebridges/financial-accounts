import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock


@pytest.fixture
def mock_dal():
    """Mock data access layer."""
    dal = MagicMock()
    dal.list_accounts_for_book.return_value = []
    dal.create_account.return_value = MagicMock(id=1)
    return dal


@pytest.fixture
def mock_book():
    """Mock book."""
    return MagicMock(id=1, name='Test Book')


@pytest.fixture
def mock_ctx(mock_dal, mock_book):
    """Mock BookContext with DAL, book, accounts, and transactions."""
    ctx = MagicMock()
    ctx.book = mock_book
    ctx.dal = mock_dal
    ctx.accounts = MagicMock()
    ctx.transactions = MagicMock()
    return ctx


@pytest.fixture
def mock_fitz_doc():
    """Factory fixture for mocking fitz PDF documents."""

    def _make_doc(page_text: str):
        mock_page = MagicMock()
        mock_page.get_text.return_value = page_text
        mock_doc = MagicMock()
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        return mock_doc

    return _make_doc


@pytest.fixture
def sample_statement():
    """Sample AccountStatement mock for reconciliation tests."""
    from ledger.db.models import AccountStatement

    stmt = MagicMock(spec=AccountStatement)
    stmt.id = 1
    stmt.book_id = 1
    stmt.account_id = 10
    stmt.start_date = date(2024, 1, 1)
    stmt.end_date = date(2024, 1, 31)
    stmt.start_balance = Decimal('1000.00')
    stmt.end_balance = Decimal('1500.00')
    stmt.account = MagicMock(name='Test Checking')
    return stmt


@pytest.fixture
def sample_transactions():
    """Sample transactions that sum to +500 (matching sample_statement)."""
    from ledger.db.models import Transaction, Split

    txns = []
    for amount in [Decimal('300.00'), Decimal('200.00')]:
        split = MagicMock(spec=Split)
        split.account_id = 10
        split.amount = amount
        txn = MagicMock(spec=Transaction)
        txn.splits = [split]
        txns.append(txn)
    return txns
