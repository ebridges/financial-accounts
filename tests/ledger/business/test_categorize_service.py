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


class TestCategorizeServiceLookup:
    """Tests for CategorizeService.lookup_category_for_payee() tiered lookup."""

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
        """Tier 1: Cache hit should be returned first."""
        # Mock cache hit
        mock_cache = MagicMock()
        mock_cache.account_id = 10
        mock_data_access.get_category_from_cache.return_value = mock_cache

        mock_account = MagicMock()
        mock_account.id = 10
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account.return_value = mock_account

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        result = service.lookup_category_for_payee("WHOLE FOODS", book_id=1)

        assert result is not None
        category, source = result
        assert category == "Expenses:Food:Groceries"
        assert source == 'cache'
        mock_data_access.increment_cache_hit.assert_called_once_with("WHOLE FOODS")

    def test_tier2_rule_match(self, rules_file, mock_data_access):
        """Tier 2: Rules should be checked if no cache hit."""
        # No cache hit
        mock_data_access.get_category_from_cache.return_value = None

        mock_account = MagicMock()
        mock_account.id = 10
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account_by_fullname_for_book.return_value = mock_account

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        result = service.lookup_category_for_payee("WHOLE FOODS MARKET", book_id=1)

        assert result is not None
        category, source = result
        assert category == "Expenses:Food:Groceries"
        assert source == 'rule'
        # Should cache for future lookups
        mock_data_access.set_category_cache.assert_called_once()

    def test_tier3_no_match_returns_none(self, rules_file, mock_data_access):
        """Tier 3: Returns None when no cache or rule matches."""
        # No cache hit
        mock_data_access.get_category_from_cache.return_value = None
        # No rule match account found
        mock_data_access.get_account_by_fullname_for_book.return_value = None

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        result = service.lookup_category_for_payee("RANDOM UNKNOWN VENDOR", book_id=1)

        assert result is None

    def test_empty_payee_returns_none(self, rules_file, mock_data_access):
        """Empty or None payee should return None."""
        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        assert service.lookup_category_for_payee("", book_id=1) is None
        assert service.lookup_category_for_payee(None, book_id=1) is None

    def test_update_cache_false_skips_cache_update(self, rules_file, mock_data_access):
        """update_cache=False should not update cache on rule match."""
        mock_data_access.get_category_from_cache.return_value = None

        mock_account = MagicMock()
        mock_account.id = 10
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account_by_fullname_for_book.return_value = mock_account

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        result = service.lookup_category_for_payee(
            "WHOLE FOODS", book_id=1, update_cache=False
        )

        assert result is not None
        # Should NOT update cache
        mock_data_access.set_category_cache.assert_not_called()
        mock_data_access.increment_cache_hit.assert_not_called()

    def test_cache_hit_with_update_cache_false(self, rules_file, mock_data_access):
        """Cache hit with update_cache=False should not increment hit count."""
        mock_cache = MagicMock()
        mock_cache.account_id = 10
        mock_data_access.get_category_from_cache.return_value = mock_cache

        mock_account = MagicMock()
        mock_account.full_name = "Expenses:Food:Groceries"
        mock_data_access.get_account.return_value = mock_account

        service = CategorizeService(rules_path=rules_file)
        service.data_access = mock_data_access

        result = service.lookup_category_for_payee(
            "WHOLE FOODS", book_id=1, update_cache=False
        )

        assert result is not None
        # Should NOT increment hit count
        mock_data_access.increment_cache_hit.assert_not_called()
