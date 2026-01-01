# test_categorize_service.py
"""Tests for Categorize Service."""
import pytest
import tempfile
import os
import json
from unittest.mock import MagicMock

from ledger.business.categorize_service import (
    CategorizeService,
    CategoryRules,
    CategorizationReport,
    CategorizationResult,
)


class TestCategoryRules:
    """Tests for CategoryRules rule matching."""

    @pytest.fixture
    def rules_file(self):
        rules = {
            "Expenses:Food:Groceries": [
                {"payee": "WHOLE FOODS", "type": "literal"},
                {"payee": "^TRADER JOE", "type": "regex"},
            ],
            "Expenses:Transportation:Gas": [
                {"payee": "SHELL", "type": "literal"},
                {"payee": "EXXON", "type": "literal"},
            ],
            "Assets:Checking Accounts:checking-chase-personal-1381": [
                {"payee": "^AUTOMATIC PAYMENT", "type": "regex"},
            ],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(rules, f)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_match_literal(self, rules_file):
        rules = CategoryRules(rules_file)
        result = rules.match("WHOLE FOODS MARKET #123")
        assert result == "Expenses:Food:Groceries"

    def test_match_regex(self, rules_file):
        rules = CategoryRules(rules_file)
        result = rules.match("TRADER JOES #456")
        assert result == "Expenses:Food:Groceries"

    def test_match_case_insensitive(self, rules_file):
        rules = CategoryRules(rules_file)
        result = rules.match("whole foods")
        assert result == "Expenses:Food:Groceries"

    def test_no_match(self, rules_file):
        rules = CategoryRules(rules_file)
        result = rules.match("RANDOM STORE XYZ")
        assert result is None

    def test_match_empty_string(self, rules_file):
        rules = CategoryRules(rules_file)
        result = rules.match("")
        assert result is None

    def test_match_none(self, rules_file):
        rules = CategoryRules(rules_file)
        result = rules.match(None)
        assert result is None

    def test_get_categories(self, rules_file):
        rules = CategoryRules(rules_file)
        categories = rules.get_categories()
        assert "Expenses:Food:Groceries" in categories
        assert "Expenses:Transportation:Gas" in categories

    def test_missing_rules_file(self):
        rules = CategoryRules('/nonexistent/path.json')
        assert rules.rules == {}
        assert rules.match("anything") is None


class TestCategorizationReport:
    """Tests for CategorizationReport."""

    def test_empty_report(self):
        report = CategorizationReport()
        assert report.transactions_processed == 0
        assert report.total_categorized == 0
        assert report.success_rate == 0.0

    def test_report_with_results(self):
        report = CategorizationReport(
            transactions_processed=10,
            categorized_from_cache=3,
            categorized_from_rules=5,
            categorized_fallback=2,
        )
        assert report.total_categorized == 8
        assert report.success_rate == 80.0

    def test_report_with_errors(self):
        report = CategorizationReport()
        report.errors.append("Test error")
        assert len(report.errors) == 1


class TestCategorizationResult:
    """Tests for CategorizationResult."""

    def test_cache_result(self):
        result = CategorizationResult(
            transaction_id=1,
            payee_norm="WHOLE FOODS",
            category_account="Expenses:Food:Groceries",
            source='cache',
            confidence=1.0
        )
        assert result.source == 'cache'
        assert result.confidence == 1.0

    def test_rule_result(self):
        result = CategorizationResult(
            transaction_id=2,
            payee_norm="TRADER JOES",
            category_account="Expenses:Food:Groceries",
            source='rule',
            confidence=0.9
        )
        assert result.source == 'rule'
        assert result.confidence == 0.9

    def test_fallback_result(self):
        result = CategorizationResult(
            transaction_id=3,
            payee_norm="UNKNOWN VENDOR",
            category_account="Expenses:Uncategorized",
            source='fallback',
            confidence=0.0
        )
        assert result.source == 'fallback'
        assert result.confidence == 0.0


class TestCategorizeServiceTieredMatching:
    """Tests for tiered categorization behavior."""

    @pytest.fixture
    def rules_file(self):
        rules = {
            "Expenses:Food:Groceries": [
                {"payee": "WHOLE FOODS", "type": "literal"},
            ],
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(rules, f)
            f.flush()
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def mock_data_access(self):
        dal = MagicMock()
        dal.get_book_by_name.return_value = MagicMock(id=1, name='test')
        return dal

    def test_tier1_cache_hit(self, rules_file, mock_data_access):
        """Tier 1: Cache hit should be used first."""
        # Mock cache hit
        mock_cache = MagicMock()
        mock_cache.account_id = 10
        mock_data_access.get_category_from_cache.return_value = mock_cache

        mock_account = MagicMock()
        mock_account.id = 10
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account.return_value = mock_account

        # Mock transaction
        mock_split = MagicMock()
        mock_split.account = MagicMock(placeholder=True, full_name='Expenses:Uncategorized')
        mock_txn = MagicMock()
        mock_txn.id = 1
        mock_txn.payee_norm = "WHOLE FOODS"
        mock_txn.splits = [mock_split, MagicMock()]

        mock_data_access.list_uncategorized_transactions.return_value = [mock_txn]
        mock_data_access.get_account_by_fullname_for_book.return_value = None  # No uncategorized account

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        report = service.categorize_transactions(book_name='test')

        assert report.categorized_from_cache == 1
        assert report.categorized_from_rules == 0

    def test_tier2_rule_match(self, rules_file, mock_data_access):
        """Tier 2: Rules should be checked if no cache hit."""
        # No cache hit
        mock_data_access.get_category_from_cache.return_value = None

        mock_account = MagicMock()
        mock_account.id = 10
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account_by_fullname_for_book.return_value = mock_account

        # Mock transaction
        mock_split = MagicMock()
        mock_split.account = MagicMock(placeholder=True, full_name='Expenses:Uncategorized')
        mock_txn = MagicMock()
        mock_txn.id = 1
        mock_txn.payee_norm = "WHOLE FOODS MARKET"  # Matches rule
        mock_txn.transaction_description = "WHOLE FOODS MARKET"
        mock_txn.splits = [mock_split, MagicMock()]

        mock_data_access.list_uncategorized_transactions.return_value = [mock_txn]

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        report = service.categorize_transactions(book_name='test')

        assert report.categorized_from_rules == 1
        assert report.categorized_from_cache == 0
        # Should also update cache
        mock_data_access.set_category_cache.assert_called()

    def test_tier3_fallback(self, rules_file, mock_data_access):
        """Tier 3: Fallback when no cache or rule matches."""
        # No cache hit
        mock_data_access.get_category_from_cache.return_value = None
        # No rule match account found
        mock_data_access.get_account_by_fullname_for_book.return_value = None

        # Mock transaction with unmatched payee
        mock_split = MagicMock()
        mock_split.account = MagicMock(placeholder=True, full_name='Expenses:Uncategorized')
        mock_txn = MagicMock()
        mock_txn.id = 1
        mock_txn.payee_norm = "RANDOM UNKNOWN VENDOR"
        mock_txn.transaction_description = "RANDOM UNKNOWN VENDOR"
        mock_txn.splits = [mock_split, MagicMock()]

        mock_data_access.list_uncategorized_transactions.return_value = [mock_txn]

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        report = service.categorize_transactions(book_name='test')

        assert report.categorized_fallback == 1
        assert report.categorized_from_cache == 0
        assert report.categorized_from_rules == 0

    def test_dry_run_no_changes(self, rules_file, mock_data_access):
        """Dry run should not update database."""
        mock_data_access.get_category_from_cache.return_value = None

        mock_account = MagicMock()
        mock_account.id = 10
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account_by_fullname_for_book.return_value = mock_account

        # Mock transaction
        mock_split = MagicMock()
        mock_split.account = MagicMock(placeholder=True, full_name='Expenses:Uncategorized')
        mock_txn = MagicMock()
        mock_txn.id = 1
        mock_txn.payee_norm = "WHOLE FOODS"
        mock_txn.transaction_description = "WHOLE FOODS"
        mock_txn.splits = [mock_split, MagicMock()]

        mock_data_access.list_uncategorized_transactions.return_value = [mock_txn]

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        report = service.categorize_transactions(book_name='test', dry_run=True)

        assert report.categorized_from_rules == 1
        # Should NOT update split or cache in dry run
        mock_data_access.update_split.assert_not_called()
        mock_data_access.set_category_cache.assert_not_called()

