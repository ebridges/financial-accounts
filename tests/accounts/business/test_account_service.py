import pytest
from unittest.mock import MagicMock
from financial_accounts.business.account_service import AccountService


@pytest.fixture
def account_service():
    service = AccountService(db_url="sqlite:///:memory:")
    service.data_access = MagicMock()
    return service


def test_list_accounts_in_book(account_service):
    account_service.data_access.get_book_by_name.return_value = MagicMock(id=1)
    account_service.data_access.list_accounts_for_book.return_value = []

    accounts = account_service.list_accounts_in_book("Test Book")
    assert accounts == []


def test_add_account(account_service):
    account_service.data_access.get_book_by_name.return_value = MagicMock(id=1)
    account_service.data_access.create_account.return_value = MagicMock(id=1)

    new_account = account_service.add_account(
        book_name="Test Book",
        parent_name=None,
        parent_code="000",
        full_name="Test Account",
        acct_name="Test Account",
        acct_code="001",
        acct_type="Asset",
        description="Test Description",
        hidden=False,
        placeholder=False,
    )
    assert new_account.id == 1
