import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from financial_accounts.business.matching_service import (
    DEFAULT_DATE_OFFSET,
    MatchingService,
    MatchingRules,
)
from financial_accounts.db.models import Account, Transaction, Split


@pytest.fixture
def mock_matching_rules_data():
    """Mock configuration data similar to the example in the class docstring."""
    return {
        "matching_rules": {
            "checking-chase-personal-1381": {
                "creditcard-chase-personal-6063": {
                    "date_offset": 1,
                    "description_patterns": [
                        "^AUTOMATIC PAYMENT - THANK(?: YOU)?$",
                        "^Payment Thank You\\s?-\\s?(Web|Mobile)$",
                    ],
                }
            },
            "creditcard-chase-personal-6063": {
                "checking-chase-personal-1381": {
                    "date_offset": 3,
                    "description_patterns": [
                        "^CHASE CREDIT CRD AUTOPAY\\s*(?:\\d+)?\\s*PPD ID:\\s*\\d+$"
                    ],
                }
            },
        }
    }


@pytest.fixture
def mock_matching_rules_from_config(mock_matching_rules_data):
    """Creates a MatchingRules instance with mocked rules data instead of reading a file."""
    with patch("builtins.open"), patch("json.load", return_value=mock_matching_rules_data):
        return MatchingRules("blah blah blah")  # Path is irrelevant due to patching


@pytest.fixture
def mock_account():
    """Creates a mock Account object."""

    # book_id, code, name, full_name, description ...
    def _mock_account(account_id):
        account = MagicMock(spec=Account)
        account.id = account_id
        return account

    return _mock_account


@pytest.fixture
def mock_transaction():
    """Creates a mock Transaction object with two splits."""

    default_date = '1900-01-01'
    default_description = 'mock description'
    default_splits = []

    def _mock_transaction(
        date: str = default_date,
        description: str = default_description,
        splits: list = default_splits,
    ):
        transaction = MagicMock(spec=Transaction)
        transaction.transaction_date = datetime.fromisoformat(date)
        transaction.transaction_description = description
        transaction.splits = splits
        return transaction

    return _mock_transaction


@pytest.fixture
def mock_split():
    """Creates a mock Split object."""

    def _mock_split(account_id, amount):
        split = MagicMock(spec=Split)
        split.account_id = account_id
        split.amount = amount
        return split

    return _mock_split


@pytest.fixture
def mock_matching_rules():
    """Creates a mock MatchingRules object with predefined behaviors."""

    default_patterns = [r"Payment \d+", r"Invoice \d+"]
    default_offset = 5

    mock_rules = MagicMock(spec=MatchingRules)
    mock_rules.matching_patterns.return_value = default_patterns
    mock_rules.matching_date_offset.return_value = default_offset

    return mock_rules


@pytest.fixture
def mock_transaction_service():
    """Creates a mock TransactionService instance."""
    transaction_service = MagicMock()
    transaction_service.query_matchable_transactions.return_value = {"mock_result": []}
    return transaction_service


@pytest.fixture
def matching_service(mock_matching_rules, mock_transaction_service):
    """Creates an instance of MatchingService with mocked rules."""
    service = MatchingService(
        matching_rules=mock_matching_rules, transaction_service=mock_transaction_service
    )
    return service


@patch(
    "financial_accounts.business.matching_service.MatchingService.compare_splits", return_value=True
)
def test_is_match_success(
    mock_compare_splits, matching_service, mock_account, mock_transaction, mock_split
):
    """Test when transactions match successfully."""
    import_for = mock_account(1)
    txn_import = mock_transaction(
        "2024-03-10", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )
    txn_candidate = mock_transaction(
        "2024-03-08", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )

    txn_import.corresponding_account.return_value = mock_account(2)

    result = matching_service.is_match(import_for, txn_import, txn_candidate)
    assert result is True, "Expected True when all conditions match"


@patch(
    "financial_accounts.business.matching_service.MatchingService.compare_splits",
    return_value=False,
)
def test_is_match_fails_on_splits(
    mock_compare_splits, matching_service, mock_account, mock_transaction, mock_split
):
    """Test when transactions fail due to split mismatch."""
    import_for = mock_account(1)
    txn_import = mock_transaction(
        "2024-03-10", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )
    txn_candidate = mock_transaction(
        "2024-03-08", "Payment 12345", [mock_split(1, 200), mock_split(2, -200)]
    )

    result = matching_service.is_match(import_for, txn_import, txn_candidate)
    assert result is False, "Expected False when splits do not match"


def test_is_match_fails_on_description(
    matching_service, mock_account, mock_transaction, mock_split
):
    """Test when description does not match any pattern."""
    import_for = mock_account(1)
    txn_import = mock_transaction(
        "2024-03-10", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )
    txn_candidate = mock_transaction(
        "2024-03-08", "Random Text", [mock_split(1, 100), mock_split(2, -100)]
    )

    result = matching_service.is_match(import_for, txn_import, txn_candidate)
    assert result is False, "Expected False when description does not match any pattern"


def test_is_match_fails_on_date_range(matching_service, mock_account, mock_transaction, mock_split):
    """Test when transaction date difference exceeds allowed offset."""
    import_for = mock_account(1)
    txn_import = mock_transaction(
        "2024-03-10", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )
    txn_candidate = mock_transaction(
        "2024-03-01", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )  # 9 days apart

    result = matching_service.is_match(import_for, txn_import, txn_candidate)
    assert result is False, "Expected False when date difference exceeds offset"


def test_is_match_success_with_regex(matching_service, mock_account, mock_transaction, mock_split):
    """Test when description matches via regex pattern."""
    import_for = mock_account(1)
    txn_import = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    txn_candidate = mock_transaction(
        "2024-03-09", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )

    result = matching_service.is_match(import_for, txn_import, txn_candidate)
    assert result is True, "Expected True when description matches a regex pattern"


def test_compare_splits_matching(mock_transaction, mock_split):
    """Test when the candidate matches the imported transaction exactly."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )

    result = MatchingService.compare_splits(imported, candidate)
    assert result == candidate, "Expected candidate to be returned when splits match"


def test_compare_splits_mismatching_amount(mock_transaction, mock_split):
    """Test when a split amount does not match."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -50)]
    )  # Amount mismatch

    result = MatchingService.compare_splits(imported, candidate)
    assert result is None, "Expected None when a split amount does not match"


def test_compare_splits_mismatching_account(mock_transaction, mock_split):
    """Test when an account ID does not match."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(3, 100), mock_split(2, -100)]
    )  # Account mismatch

    result = MatchingService.compare_splits(imported, candidate)
    assert result is None, "Expected None when an account ID does not match"


def test_compare_splits_extra_split(mock_transaction, mock_split):
    """Test when candidate has an extra split that is not in imported."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100), mock_split(3, 50)]
    )  # Extra split

    result = MatchingService.compare_splits(imported, candidate)
    assert result is None, "Expected None when candidate has an extra split"


def test_compare_splits_missing_split(mock_transaction, mock_split):
    """Test when candidate has a missing split compared to imported."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100)]
    )  # Missing second split

    result = MatchingService.compare_splits(imported, candidate)
    assert result is None, "Expected None when candidate has a missing split"


def test_compare_splits_unordered_matching(mock_transaction, mock_split):
    """Test when candidate splits match but are in a different order."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(2, -100), mock_split(1, 100)]
    )  # Reversed order

    result = MatchingService.compare_splits(imported, candidate)
    assert result == candidate, "Expected candidate to be returned even if order differs"


def test_compare_splits_empty_splits(mock_transaction):
    """Test when both transactions have no splits (edge case)."""
    imported = mock_transaction("2024-03-10", "Invoice 7890", [])
    candidate = mock_transaction("2024-03-10", "Invoice 7890", [])

    result = MatchingService.compare_splits(imported, candidate)
    assert result == candidate, "Expected candidate to be returned when both are empty"


def test_compare_splits_one_empty(mock_transaction, mock_split):
    """Test when one transaction is empty and the other is not."""
    imported = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )
    candidate = mock_transaction("2024-03-10", "Invoice 7890", [])  # Candidate is empty

    result = MatchingService.compare_splits(imported, candidate)
    assert result is None, "Expected None when candidate has no splits"

    imported_empty = mock_transaction("2024-03-10", "Invoice 7890", [])
    candidate_nonempty = mock_transaction(
        "2024-03-10", "Invoice 7890", [mock_split(1, 100), mock_split(2, -100)]
    )

    result = MatchingService.compare_splits(imported_empty, candidate_nonempty)
    assert result is None, "Expected None when imported has no splits"


def test_batch_query_candidates_success(
    matching_service, mock_transaction_service, mock_transaction
):
    """Test batch query candidates with a valid range of transactions."""
    book_id = "12345"
    imported_transactions = [
        mock_transaction('2024-03-10'),
        mock_transaction('2024-03-15'),
        mock_transaction('2024-03-20'),
    ]
    matching_accounts = ["acct1", "acct2"]

    # Expected date range
    expected_start_date = datetime.fromisoformat('2024-03-10') - timedelta(days=DEFAULT_DATE_OFFSET)
    expected_end_date = datetime.fromisoformat('2024-03-20') + timedelta(days=DEFAULT_DATE_OFFSET)

    # Call the function
    result = matching_service.batch_query_candidates(
        book_id, imported_transactions, matching_accounts
    )

    # Assertions
    mock_transaction_service.query_matchable_transactions.assert_called_once_with(
        book_id=book_id,
        start_date=expected_start_date,
        end_date=expected_end_date,
        accounts_to_match_for=matching_accounts,
    )
    assert result == {"mock_result": []}, "Expected mock result to be returned"


def test_batch_query_candidates_single_transaction(
    matching_service, mock_transaction_service, mock_transaction
):
    """Test batch query candidates with only one transaction."""
    book_id = "12345"
    imported_transactions = [mock_transaction('2024-03-15')]
    matching_accounts = ["acct1"]

    expected_start_date = datetime.fromisoformat('2024-03-15') - timedelta(days=DEFAULT_DATE_OFFSET)
    expected_end_date = datetime.fromisoformat('2024-03-15') + timedelta(days=DEFAULT_DATE_OFFSET)

    # Call the function
    result = matching_service.batch_query_candidates(
        book_id, imported_transactions, matching_accounts
    )

    # Assertions
    mock_transaction_service.query_matchable_transactions.assert_called_once_with(
        book_id=book_id,
        start_date=expected_start_date,
        end_date=expected_end_date,
        accounts_to_match_for=matching_accounts,
    )
    assert result == {"mock_result": []}, "Expected mock result to be returned"


def test_batch_query_candidates_empty_transactions(matching_service, mock_transaction_service):
    """Test batch query candidates with an empty imported transactions list."""
    book_id = "12345"
    imported_transactions = []  # No transactions
    matching_accounts = ["acct1"]

    with pytest.raises(ValueError, match=r"min\(\) iterable argument is empty"):
        matching_service.batch_query_candidates(book_id, imported_transactions, matching_accounts)


def test_batch_query_candidates_no_matching_accounts(
    matching_service, mock_transaction_service, mock_transaction
):
    """Test batch query candidates with no matching accounts (should still execute)."""
    book_id = "12345"
    imported_transactions = [
        mock_transaction('2024-03-15'),
        mock_transaction('2024-03-20'),
    ]
    matching_accounts = []  # No accounts specified

    expected_start_date = datetime.fromisoformat('2024-03-15') - timedelta(days=DEFAULT_DATE_OFFSET)
    expected_end_date = datetime.fromisoformat('2024-03-20') + timedelta(days=DEFAULT_DATE_OFFSET)

    # Call the function
    result = matching_service.batch_query_candidates(
        book_id, imported_transactions, matching_accounts
    )

    # Assertions
    mock_transaction_service.query_matchable_transactions.assert_called_once_with(
        book_id=book_id,
        start_date=expected_start_date,
        end_date=expected_end_date,
        accounts_to_match_for=matching_accounts,
    )
    assert result == {"mock_result": []}, "Expected mock result to be returned"


def test_matchable_accounts_success(mock_account, mock_matching_rules_from_config):
    """Test retrieving matchable accounts successfully."""
    test_account = mock_account(123)
    test_account.full_name = "checking-chase-personal-1381"

    result = mock_matching_rules_from_config.matchable_accounts(test_account)
    assert result == {"creditcard-chase-personal-6063"}, "Expected matchable account IDs"


def test_matchable_accounts_key_error(mock_account, mock_matching_rules_from_config):
    """Test KeyError when querying an unknown account."""
    test_account = mock_account(123)
    test_account.full_name = "unknown-account"
    with pytest.raises(KeyError):
        mock_matching_rules_from_config.matchable_accounts(test_account)


def test_matching_patterns_success(mock_account, mock_matching_rules_from_config):
    """Test retrieving matching patterns for valid accounts."""
    test_account_1 = mock_account(123)
    test_account_1.full_name = "checking-chase-personal-1381"
    test_account_2 = mock_account(456)
    test_account_2.full_name = "creditcard-chase-personal-6063"
    result = mock_matching_rules_from_config.matching_patterns(test_account_1, test_account_2)
    assert result == [
        "^AUTOMATIC PAYMENT - THANK(?: YOU)?$",
        "^Payment Thank You\\s?-\\s?(Web|Mobile)$",
    ], "Expected correct regex patterns"


def test_matching_patterns_key_error(mock_account, mock_matching_rules_from_config):
    """Test KeyError when querying invalid import or corresponding accounts."""
    test_account_1 = mock_account(123)
    test_account_1.full_name = "checking-chase-personal-1381"
    test_account_2 = mock_account(456)
    test_account_2.full_name = "nonexistent-account"
    with pytest.raises(KeyError):
        mock_matching_rules_from_config.matching_patterns(test_account_1, test_account_2)


def test_matching_date_offset_success(mock_account, mock_matching_rules_from_config):
    """Test retrieving date offset for valid accounts."""
    test_account_1 = mock_account(123)
    test_account_1.full_name = "checking-chase-personal-1381"
    test_account_2 = mock_account(456)
    test_account_2.full_name = "creditcard-chase-personal-6063"
    result = mock_matching_rules_from_config.matching_date_offset(test_account_1, test_account_2)
    assert result == 1, "Expected correct date offset"


def test_matching_date_offset_key_error(mock_account, mock_matching_rules_from_config):
    """Test KeyError when querying an invalid account pair for date offset."""
    test_account_1 = mock_account(123)
    test_account_1.full_name = "checking-chase-personal-1381"
    test_account_2 = mock_account(456)
    test_account_2.full_name = "nonexistent-account"
    with pytest.raises(KeyError):
        mock_matching_rules_from_config.matching_date_offset(test_account_1, test_account_2)


def test_matching_rules_malformed_data(mock_account):
    """Test behavior when matching rules configuration is malformed."""
    malformed_data = {
        "matching_rules": {
            "checking-chase-personal-1381": {
                "creditcard-chase-personal-6063": {
                    # Missing "description_patterns"
                    "date_offset": 1
                }
            }
        }
    }

    test_account_1 = mock_account(123)
    test_account_1.full_name = "checking-chase-personal-1381"
    test_account_2 = mock_account(456)
    test_account_2.full_name = "creditcard-chase-personal-6063"

    with patch("builtins.open"), patch("json.load", return_value=malformed_data):
        matching_rules = MatchingRules("blah blah blah")

        with pytest.raises(KeyError):
            matching_rules.matching_patterns(test_account_1, test_account_2)
