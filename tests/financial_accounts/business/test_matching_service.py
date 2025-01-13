import pytest
import tempfile
import json
import os
from datetime import date
from unittest.mock import MagicMock

from financial_accounts.business.matching_service import MatchingService
from financial_accounts.db.models import Transactions, Split

@pytest.fixture
def temp_matching_config():
    config = {
        "global_defaults": {
            "date_offset": 2,
            "description_patterns": []
        },
        "accounts": [
            {
                "account": "checking-chase-personal-1381",
                "corresponding_accounts": {
                    "creditcard-chase-personal-6063": {
                        "date_offset": 1,
                        "description_patterns": [
                            "^CHASE CREDIT CRD AUTOPAY\\s+PPD ID: \\d{10}$",
                            "^Payment to Chase card ending in \\d{4} \\d{2}/\\d{2}$"
                        ]
                    }
                }
            }
        ],
        "fallback": {
            "date_offset": 2,
            "description_patterns": []
        }
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
def matching_service(temp_matching_config):
    mock_transaction_service = MagicMock()
    return MatchingService(
        config_path="matching-config.json",
        transaction_service=mock_transaction_service
    )

def test_is_match(matching_service):
    # Create mock transactions
    imported_txn = Transactions(
        transaction_date=date(2025, 1, 10),
        splits=[
            Split(account_id="acct1", amount=100),
            Split(account_id="acct2", amount=-100)
        ]
    )
    candidate_txn = Transactions(
        transaction_date=date(2025, 1, 9),
        transaction_description="Payment Thank You - Web",
        splits=[
            Split(account_id="acct1", amount=-100),
            Split(account_id="acct2", amount=100)
        ]
    )

    # Define rules
    rules = {
        "description_patterns": ["^Payment Thank You - (Web|Mobile)$"],
        "date_offset": 2
    }

    # Test matching
    result = matching_service._is_match(imported_txn, candidate_txn, rules)
    assert result
