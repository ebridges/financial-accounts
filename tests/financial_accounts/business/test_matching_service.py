import pytest
import tempfile
import json
import os
from datetime import date
from unittest.mock import MagicMock

from financial_accounts.business.matching_service import MatchingService
from financial_accounts.db.models import Transaction, Split


@pytest.fixture
def matching_config():
    config = {
        "global_defaults": {"date_offset": 2, "description_patterns": []},
        "accounts": [
            {
                "account": "my-checking-account",
                "corresponding_accounts": {
                    "my-creditcard-account": {
                        "date_offset": 1,
                        "description_patterns": [
                            "^CREDIT CRD AUTOPAY\\s+PPD ID: \\d{10}$",
                            "^Payment to Credit card ending in \\d{4} \\d{2}/\\d{2}$",
                        ],
                    }
                },
            }
        ],
        "fallback": {"date_offset": 2, "description_patterns": []},
    }
    with tempfile.NamedTemporaryFile('w', delete=False) as temp_file:
        json.dump(config, temp_file)
        temp_file_path = temp_file.name
    yield temp_file_path
    # Cleanup
    try:
        os.remove(temp_file_path)
    except OSError:
        pass


@pytest.fixture
def matching_service(matching_config):
    mock_transaction_service = MagicMock()
    return MatchingService(
        config_path=matching_config, transaction_service=mock_transaction_service
    )


def test_is_match(matching_service):
    # Create mock transactions
    imported_txn = Transaction(
        transaction_date=date(2025, 1, 10),
        splits=[Split(account_id="acct1", amount=100), Split(account_id="acct2", amount=-100)],
    )
    candidate_txn = Transaction(
        transaction_date=date(2025, 1, 9),
        transaction_description="Payment Thank You - Web",
        splits=[Split(account_id="acct1", amount=-100), Split(account_id="acct2", amount=100)],
    )

    # Define rules
    rules = {"description_patterns": ["^Payment Thank You - (Web|Mobile)$"], "date_offset": 2}

    # Test matching
    result = matching_service._is_match(imported_txn, candidate_txn, rules)
    assert result


def test_group_candidates_by_account(matching_service):
    # Create mock transactions
    txn1 = Transaction(
        splits=[Split(account_id="acct1", amount=100), Split(account_id="acct2", amount=-100)]
    )
    txn2 = Transaction(
        splits=[Split(account_id="acct1", amount=200), Split(account_id="acct3", amount=-200)]
    )
    txn3 = Transaction(
        splits=[Split(account_id="acct2", amount=300), Split(account_id="acct3", amount=-300)]
    )

    # Group transactions by account
    candidates = [txn1, txn2, txn3]
    grouped = matching_service._group_candidates_by_account(candidates)

    # Verify the grouping
    assert len(grouped) == 3
    assert len(grouped["acct1"]) == 2
    assert len(grouped["acct2"]) == 2
    assert len(grouped["acct3"]) == 2
    assert txn1 in grouped["acct1"]
    assert txn2 in grouped["acct1"]
    assert txn1 in grouped["acct2"]
    assert txn3 in grouped["acct2"]
    assert txn2 in grouped["acct3"]
    assert txn3 in grouped["acct3"]


def test_get_account_rules(matching_service):
    # Test with an account that has specific rules
    account_with_rules = "my-checking-account"
    rules = matching_service._get_account_rules(account_with_rules)
    assert len(rules) == 1
    assert rules[0]["account"] == account_with_rules

    # Test with an account that does not have specific rules
    account_without_rules = "nonexistent-account"
    rules = matching_service._get_account_rules(account_without_rules)
    assert len(rules) == 1
    assert "date_offset" in rules[0]
    assert "description_patterns" in rules[0]


def test_batch_query_candidates(matching_service):
    # Mock transactions to import
    imported_transactions = [
        Transaction(transaction_date=date(2025, 1, 10)),
        Transaction(transaction_date=date(2025, 1, 15)),
    ]

    # Mock the transaction service's get_transactions_in_range method
    matching_service.transaction_service.get_transactions_in_range = MagicMock(
        return_value=[
            Transaction(transaction_date=date(2025, 1, 8)),
            Transaction(transaction_date=date(2025, 1, 12)),
            Transaction(transaction_date=date(2025, 1, 16)),
        ]
    )

    # Call the method
    candidates = matching_service._batch_query_candidates("book_id", imported_transactions)

    # Verify the method was called with the correct date range
    matching_service.transaction_service.get_transactions_in_range.assert_called_once_with(
        book_id="book_id",
        start_date=date(2025, 1, 8),  # 2 days before the earliest transaction
        end_date=date(2025, 1, 17),  # 2 days after the latest transaction
        recon_status=None,
        match_status=None,
    )

    # Verify the returned candidates
    assert len(candidates) == 3


def test_import_transactions(matching_service):
    # Mock transactions to import
    imported_transactions = [
        Transaction(
            transaction_date=date(2025, 1, 10),
            transaction_description="Payment Thank You - Web",
            splits=[
                Split(account_id="my-checking-account", amount=100),
                Split(account_id="my-creditcard-account", amount=-100),
            ],
        )
    ]

    # Mock the transaction service's get_transactions_in_range method
    matching_service.transaction_service.get_transactions_in_range = MagicMock(
        return_value=[
            Transaction(
                transaction_date=date(2025, 1, 9),
                transaction_description="Payment Thank You - Web",
                splits=[
                    Split(account_id="my-checking-account", amount=-100),
                    Split(account_id="my-creditcard-account", amount=100),
                ],
            )
        ]
    )

    # Mock the transaction service's update_transaction method
    matching_service.transaction_service.update_transaction = MagicMock()

    # Mock the transaction service's enter_transaction method
    matching_service.transaction_service.enter_transaction = MagicMock()

    # Call the method
    matching_service.import_transactions("book_id", "my-checking-account", imported_transactions)

    # Verify that the update_transaction method was called to mark the transaction as matched
    matching_service.transaction_service.update_transaction.assert_called_once()

    # Verify that the enter_transaction method was not called since the transaction was matched
    matching_service.transaction_service.enter_transaction.assert_not_called()
