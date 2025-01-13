import pytest
import tempfile
import json
import os
from datetime import date
from unittest.mock import MagicMock

from financial_accounts.business.matching_service import MatchingService
from financial_accounts.db.models import Transactions, Split


@pytest.fixture
def matching_config():
    config = {
        "global_defaults": {"date_offset": 2, "description_patterns": []},
        "accounts": [
            {
                "account": "checking-chase-personal-1381",
                "corresponding_accounts": {
                    "creditcard-chase-personal-6063": {
                        "date_offset": 1,
                        "description_patterns": [
                            "^CHASE CREDIT CRD AUTOPAY\\s+PPD ID: \\d{10}$",
                            "^Payment to Chase card ending in \\d{4} \\d{2}/\\d{2}$",
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
    imported_txn = Transactions(
        transaction_date=date(2025, 1, 10),
        splits=[Split(account_id="acct1", amount=100), Split(account_id="acct2", amount=-100)],
    )
    candidate_txn = Transactions(
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
    txn1 = Transactions(
        splits=[Split(account_id="acct1", amount=100), Split(account_id="acct2", amount=-100)]
    )
    txn2 = Transactions(
        splits=[Split(account_id="acct1", amount=200), Split(account_id="acct3", amount=-200)]
    )
    txn3 = Transactions(
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
    account_with_rules = "checking-chase-personal-1381"
    rules = matching_service._get_account_rules(account_with_rules)
    assert len(rules) == 1
    assert rules[0]["account"] == account_with_rules

    # Test with an account that does not have specific rules
    account_without_rules = "nonexistent-account"
    rules = matching_service._get_account_rules(account_without_rules)
    assert len(rules) == 1
    assert "date_offset" in rules[0]
    assert "description_patterns" in rules[0]
