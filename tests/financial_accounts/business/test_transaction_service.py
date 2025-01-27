import pytest
from unittest.mock import MagicMock
from financial_accounts.business.transaction_service import TransactionService
from financial_accounts.db.models import Transaction


@pytest.fixture
def transaction_service():
    service = TransactionService().init_with_url(db_url="sqlite:///:memory:")
    service.data_access = MagicMock()
    return service


def test_enter_transaction(transaction_service):
    transaction_service.data_access.get_book_by_name.return_value = MagicMock(id=1)
    transaction_service.data_access.get_account_by_name_for_book.side_effect = [
        MagicMock(id=1),
        MagicMock(id=2),
    ]
    transaction_service.data_access.create_transaction.return_value = MagicMock(id=1)

    txn_id = transaction_service.enter_transaction(
        book_name="Test Book",
        txn_date="2023-10-01",
        txn_desc="Test Transaction",
        to_acct="Debit Account",
        from_acct="Credit Account",
        amount="100.00",
    )
    assert txn_id == 1


def test_delete_transaction(transaction_service):
    transaction_service.data_access.get_transaction.return_value = Transaction(id=1)
    transaction_service.data_access.delete_transaction.return_value = True

    result = transaction_service.delete_transaction(transaction_id=1)
    assert result is True


def test_delete_transaction_fail(transaction_service):
    transaction_service.data_access.get_transaction.return_value = None
    transaction_service.data_access.delete_transaction.return_value = False

    result = None
    with pytest.raises(ValueError):
        result = transaction_service.delete_transaction(transaction_id=1)
    assert result is None
