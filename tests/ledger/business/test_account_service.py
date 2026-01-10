# test_account_service.py
"""Tests for AccountService."""
import pytest
from unittest.mock import MagicMock

from ledger.business.account_service import AccountService


@pytest.fixture
def account_service(mock_dal, mock_book):
    """Create AccountService with mocked dependencies."""
    return AccountService(mock_dal, mock_book)


def test_list_accounts(account_service, mock_dal):
    """Test listing accounts in a book."""
    accounts = account_service.list_accounts()

    assert accounts == []
    mock_dal.list_accounts_for_book.assert_called_once_with(1)


def test_add_account(account_service, mock_dal):
    """Test adding an account."""
    new_account = account_service.add_account(
        parent_code="000",
        parent_name=None,
        acct_name="Test Account",
        full_name="Test Account",
        acct_code="001",
        acct_type="Asset",
        description="Test Description",
        hidden=False,
        placeholder=False,
    )

    assert new_account.id == 1
    mock_dal.create_account.assert_called_once()


def test_add_account_with_parent(account_service, mock_dal):
    """Test adding an account with a parent."""
    mock_parent = MagicMock(id=5)
    mock_dal.get_account_by_name_for_book.return_value = mock_parent

    new_account = account_service.add_account(
        parent_code="ROOT",
        parent_name="Root Account",
        acct_name="Child Account",
        full_name="Root:Child Account",
        acct_code="002",
        acct_type="Asset",
        description="",
        hidden=False,
        placeholder=False,
    )

    assert new_account.id == 1
    # Verify parent was looked up
    mock_dal.get_account_by_name_for_book.assert_called_once_with(1, "ROOT", "Root Account")


def test_lookup_by_name(account_service, mock_dal):
    """Test looking up account by name."""
    mock_account = MagicMock(id=10, full_name="Assets:Checking")
    mock_dal.get_account_by_fullname_for_book.return_value = mock_account

    result = account_service.lookup_by_name("Assets:Checking")

    assert result.id == 10
    mock_dal.get_account_by_fullname_for_book.assert_called_once_with(
        book_id=1, acct_fullname="Assets:Checking"
    )


def test_lookup_by_name_not_found(account_service, mock_dal):
    """Test looking up account that doesn't exist."""
    mock_dal.get_account_by_fullname_for_book.return_value = None

    with pytest.raises(Exception, match="No account found"):
        account_service.lookup_by_name("Nonexistent:Account")


def test_lookup_by_id(account_service, mock_dal):
    """Test looking up account by ID."""
    mock_account = MagicMock(id=10)
    mock_dal.get_account.return_value = mock_account

    result = account_service.lookup_by_id(10)

    assert result.id == 10
    mock_dal.get_account.assert_called_once_with(account_id=10)
