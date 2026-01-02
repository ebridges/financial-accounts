# test_transaction_service.py
"""Tests for TransactionService."""
import pytest
from unittest.mock import MagicMock

from ledger.business.transaction_service import TransactionService
from ledger.db.models import Transaction


@pytest.fixture
def transaction_service(mock_dal, mock_book):
    """Create TransactionService with mocked dependencies."""
    return TransactionService(mock_dal, mock_book)


def test_enter_transaction(transaction_service, mock_dal):
    """Test entering a new transaction."""
    mock_dal.get_account_by_fullname_for_book.side_effect = [
        MagicMock(id=1),  # to_account
        MagicMock(id=2),  # from_account
    ]
    mock_dal.create_transaction.return_value = MagicMock(id=1)

    txn_id = transaction_service.enter_transaction(
        txn_date="2023-10-01",
        txn_desc="Test Transaction",
        to_acct="Debit Account",
        from_acct="Credit Account",
        amount="100.00",
    )
    
    assert txn_id == 1
    mock_dal.create_transaction.assert_called_once()
    # Should create two splits (debit and credit)
    assert mock_dal.create_split.call_count == 2


def test_enter_transaction_debit_account_not_found(transaction_service, mock_dal):
    """Test error when debit account not found."""
    mock_dal.get_account_by_fullname_for_book.return_value = None

    with pytest.raises(Exception, match="Debit account"):
        transaction_service.enter_transaction(
            txn_date="2023-10-01",
            txn_desc="Test Transaction",
            to_acct="Nonexistent Account",
            from_acct="Credit Account",
            amount="100.00",
        )


def test_delete_transaction(transaction_service, mock_dal):
    """Test deleting a transaction."""
    mock_dal.get_transaction.return_value = Transaction(id=1)
    mock_dal.delete_transaction.return_value = True

    result = transaction_service.delete(transaction_id=1)
    
    assert result is True
    mock_dal.delete_transaction.assert_called_once_with(txn_id=1)


def test_delete_transaction_not_found(transaction_service, mock_dal):
    """Test error when deleting non-existent transaction."""
    mock_dal.get_transaction.return_value = None

    with pytest.raises(ValueError, match="No transaction exists"):
        transaction_service.delete(transaction_id=999)


def test_get_all_transactions(transaction_service, mock_dal):
    """Test getting all transactions for the book."""
    mock_txns = [MagicMock(id=1), MagicMock(id=2)]
    mock_dal.list_transactions_for_book.return_value = mock_txns

    result = transaction_service.get_all()
    
    assert len(result) == 2
    mock_dal.list_transactions_for_book.assert_called_once_with(book_id=1)


def test_mark_matched(transaction_service, mock_dal):
    """Test marking a transaction as matched."""
    mock_txn = MagicMock()

    transaction_service.mark_matched(mock_txn)
    
    mock_dal.update_transaction_match_status.assert_called_once_with(mock_txn)


def test_query_unmatched(transaction_service, mock_dal):
    """Test querying unmatched transactions."""
    from datetime import date
    
    mock_dal.query_for_unmatched_transactions_in_range.return_value = []
    start = date(2024, 1, 1)
    end = date(2024, 1, 31)

    result = transaction_service.query_unmatched(start, end, ["Account1"])
    
    assert result == []
    mock_dal.query_for_unmatched_transactions_in_range.assert_called_once_with(
        1, start, end, ["Account1"]
    )


def test_insert_transaction(transaction_service, mock_dal):
    """Test inserting a transaction object."""
    mock_txn = MagicMock()
    mock_dal.insert_transaction.return_value = mock_txn

    result = transaction_service.insert(mock_txn)
    
    assert result == mock_txn
    mock_dal.insert_transaction.assert_called_once_with(mock_txn)
