import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from ledger.business.matching_service import (
    MatchingService,
    MatchingRules,
)


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

    def _mock_account(account_id):
        # Don't use spec=Account to avoid SQLAlchemy introspection
        account = MagicMock()
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
        # Don't use spec=Transaction to avoid SQLAlchemy introspection
        transaction = MagicMock()
        transaction.transaction_date = datetime.fromisoformat(date)
        transaction.transaction_description = description
        transaction.splits = splits
        return transaction

    return _mock_transaction


@pytest.fixture
def mock_split():
    """Creates a mock Split object."""

    def _mock_split(account_id, amount):
        # Don't use spec=Split to avoid SQLAlchemy introspection
        split = MagicMock()
        split.account_id = account_id
        split.amount = amount
        return split

    return _mock_split


@pytest.fixture
def mock_matching_rules():
    """Creates a mock MatchingRules object with predefined behaviors."""

    default_patterns = [r"Payment \d+", r"Invoice \d+"]
    default_offset = 5

    mock_rules = MagicMock()
    mock_rules.matching_patterns.return_value = default_patterns
    mock_rules.matching_date_offset.return_value = default_offset

    return mock_rules


@pytest.fixture
def matching_service(mock_matching_rules):
    """Creates an instance of MatchingService with mocked rules."""
    with patch.object(MatchingService, '__init__', lambda self, rules_path=None: None):
        service = MatchingService()
        service.rules = mock_matching_rules
    return service


@pytest.mark.filterwarnings("ignore::ResourceWarning")
@patch(
    "ledger.business.matching_service.MatchingService.compare_splits", return_value=True
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


@pytest.mark.filterwarnings("ignore::ResourceWarning")
@patch(
    "ledger.business.matching_service.MatchingService.compare_splits",
    return_value=None,  # compare_splits returns None on mismatch, not False
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
    """Test when import description does not match any pattern."""
    import_for = mock_account(1)
    # Set import description to something that doesn't match (we check import, not candidate)
    txn_import = mock_transaction(
        "2024-03-10", "Random Text", [mock_split(1, 100), mock_split(2, -100)]
    )
    txn_candidate = mock_transaction(
        "2024-03-08", "Payment 12345", [mock_split(1, 100), mock_split(2, -100)]
    )

    result = matching_service.is_match(import_for, txn_import, txn_candidate)
    assert result is False, "Expected False when import description does not match any pattern"


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


# Parametrized compare_splits tests
@pytest.mark.parametrize("imported_splits,candidate_splits,should_match,description", [
    ([(1, 100), (2, -100)], [(1, 100), (2, -100)], True, "exact match"),
    ([(1, 100), (2, -100)], [(2, -100), (1, 100)], True, "unordered match"),
    ([(1, 100), (2, -100)], [(1, 100), (2, -50)], False, "amount mismatch"),
    ([(1, 100), (2, -100)], [(3, 100), (2, -100)], False, "account mismatch"),
    ([(1, 100), (2, -100)], [(1, 100)], False, "missing split"),
    ([(1, 100), (2, -100)], [(1, 100), (2, -100), (3, 50)], False, "extra split"),
    ([], [], True, "both empty"),
    ([(1, 100), (2, -100)], [], False, "candidate empty"),
    ([], [(1, 100), (2, -100)], False, "imported empty"),
])
@pytest.mark.filterwarnings("ignore::ResourceWarning")
def test_compare_splits(mock_transaction, mock_split, imported_splits, candidate_splits, should_match, description):
    """Test compare_splits with various split configurations."""
    imported = mock_transaction(splits=[mock_split(*s) for s in imported_splits])
    candidate = mock_transaction(splits=[mock_split(*s) for s in candidate_splits])
    result = MatchingService.compare_splits(imported, candidate)
    assert (result is not None) == should_match, f"Failed for: {description}"


def test_matchable_accounts_success(mock_account, mock_matching_rules_from_config):
    """Test retrieving matchable accounts successfully."""
    test_account = mock_account(123)
    test_account.full_name = "checking-chase-personal-1381"

    result = mock_matching_rules_from_config.matchable_accounts(test_account)
    assert result == {"creditcard-chase-personal-6063"}, "Expected matchable account IDs"


def test_matchable_accounts_unknown_account(mock_account, mock_matching_rules_from_config):
    """Test that unknown account returns empty set (uses .get() with default)."""
    test_account = mock_account(123)
    test_account.full_name = "unknown-account"
    # Current implementation uses .get() which returns empty dict, not KeyError
    result = mock_matching_rules_from_config.matchable_accounts(test_account)
    assert result == set() or result == {}.keys(), "Expected empty result for unknown account"


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


@pytest.mark.filterwarnings("ignore::ResourceWarning")
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
