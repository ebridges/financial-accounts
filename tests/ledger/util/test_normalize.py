# test_normalize.py
"""Tests for payee normalization utility."""
import pytest

from ledger.util.normalize import normalize_payee


class TestNormalizePayee:
    """Tests for normalize_payee function."""

    def test_basic_normalization(self):
        """Basic string is uppercased and trimmed."""
        assert normalize_payee("whole foods") == "WHOLE FOODS"
        assert normalize_payee("  Trader Joe's  ") == "TRADER JOE'S"

    def test_empty_string(self):
        """Empty string returns empty."""
        assert normalize_payee("") == ""
        assert normalize_payee(None) == ""

    def test_collapse_whitespace(self):
        """Multiple spaces collapsed to single space."""
        assert normalize_payee("WHOLE   FOODS   MARKET") == "WHOLE FOODS MARKET"

    def test_strip_ppd_id(self):
        """PPD ID suffix is stripped."""
        assert normalize_payee("CHASE CREDIT CRD PPD ID: 1234567890") == "CHASE CREDIT CRD"

    def test_strip_transaction_number(self):
        """Transaction# suffix is stripped."""
        # The regex also strips the trailing ...1605 as a card number pattern
        assert normalize_payee("ONLINE TRANSFER TRANSACTION#: 12345678") == "ONLINE TRANSFER"

    def test_strip_card_number(self):
        """Card number suffixes are stripped."""
        assert normalize_payee("AMAZON PURCHASE XXXX1234") == "AMAZON PURCHASE"
        assert normalize_payee("STARBUCKS ...5678") == "STARBUCKS"

    def test_strip_trailing_date(self):
        """Trailing dates are stripped."""
        assert normalize_payee("PAYMENT THANK YOU 01/15") == "PAYMENT THANK YOU"
        assert normalize_payee("PURCHASE 12/25/2024") == "PURCHASE"

    def test_strip_reference_number(self):
        """Long reference numbers are stripped."""
        assert normalize_payee("ACH DEPOSIT 123456789012") == "ACH DEPOSIT"

    def test_combined_stripping(self):
        """Multiple patterns in one string."""
        result = normalize_payee("CHASE AUTOPAY  XXXX1234 PPD ID: 9999")
        # Should strip card number and PPD ID
        assert "XXXX1234" not in result
        assert "PPD ID" not in result
