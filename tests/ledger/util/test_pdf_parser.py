"""Tests for PDF statement parser."""
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch

from ledger.util.pdf_parser import (
    StatementPdfParser, StatementParseError, get_account_type_prefix,
    STATEMENT_DATE_PATTERNS, STATEMENT_BALANCE_PATTERNS,
)
from ledger.util.statement_uri import AccountUri


class TestGetAccountTypePrefix:
    def test_exact_match(self):
        assert get_account_type_prefix("checking-chase-personal") == "checking-chase-personal"

    def test_strips_account_number(self):
        assert get_account_type_prefix("checking-chase-personal-1381") == "checking-chase-personal"
        assert get_account_type_prefix("creditcard-chase-personal-6063") == "creditcard-chase-personal"

    def test_unknown_account_raises(self):
        with pytest.raises(StatementParseError):
            get_account_type_prefix("unknown-account-type")


class TestStatementPdfParser:
    @patch('ledger.util.pdf_parser.fitz')
    def test_parse_chase_checking_statement(self, mock_fitz, mock_fitz_doc):
        mock_fitz.open.return_value = mock_fitz_doc("""
        January 15, 2024 through February 14, 2024
        Beginning Balance                $1,234.56
        Ending Balance                   $1,534.56
        """)
        uri = AccountUri.from_string(
            '2024/checking-chase-personal-1381/2024-01-15--2024-02-14-checking-chase-personal-1381.pdf'
        )
        with patch('pathlib.Path.exists', return_value=True):
            result = StatementPdfParser().parse_statement(uri)
        assert result.account_slug == 'checking-chase-personal-1381'
        assert result.start_date == date(2024, 1, 15)
        assert result.end_date == date(2024, 2, 14)
        assert result.start_balance == Decimal('1234.56')
        assert result.end_balance == Decimal('1534.56')

    @patch('ledger.util.pdf_parser.fitz')
    def test_parse_chase_business_checking(self, mock_fitz, mock_fitz_doc):
        mock_fitz.open.return_value = mock_fitz_doc("""
        February 01, 2018 through February 28, 2018
        Beginning Balance                $852.98
        Ending Balance                3  $783.78
        """)
        uri = AccountUri.from_string(
            '2018/checking-chase-business-9210/2018-02-01--2018-02-28-checking-chase-business-9210.pdf'
        )
        with patch('pathlib.Path.exists', return_value=True):
            result = StatementPdfParser().parse_statement(uri)
        assert result.start_date == date(2018, 2, 1)
        assert result.end_date == date(2018, 2, 28)
        assert result.start_balance == Decimal('852.98')
        assert result.end_balance == Decimal('783.78')

    @patch('ledger.util.pdf_parser.fitz')
    def test_parse_chase_credit_card(self, mock_fitz, mock_fitz_doc):
        mock_fitz.open.return_value = mock_fitz_doc("""
        Opening/Closing Date 06/29/22 - 07/28/22
        Previous Balance                 $2,500.00
        New Balance                      $2,702.99
        """)
        uri = AccountUri.from_string(
            '2022/creditcard-chase-personal-0239/2022-06-29--2022-07-28-creditcard-chase-personal-0239.pdf'
        )
        with patch('pathlib.Path.exists', return_value=True):
            result = StatementPdfParser().parse_statement(uri)
        assert result.start_date == date(2022, 6, 29)
        assert result.end_date == date(2022, 7, 28)
        assert result.start_balance == Decimal('2500.00')
        assert result.end_balance == Decimal('2702.99')

    def test_file_not_found_raises(self):
        uri = AccountUri.from_string(
            '2024/checking-chase-personal/2024-01-01--2024-01-31-checking-chase-personal.pdf'
        )
        with pytest.raises(StatementParseError) as exc_info:
            StatementPdfParser().parse_statement(uri)
        assert "not found" in str(exc_info.value)

    @patch('ledger.util.pdf_parser.fitz')
    def test_missing_dates_raises(self, mock_fitz, mock_fitz_doc):
        mock_fitz.open.return_value = mock_fitz_doc("No dates here")
        uri = AccountUri.from_string(
            '2024/checking-chase-personal/2024-01-01--2024-01-31-checking-chase-personal.pdf'
        )
        with patch('pathlib.Path.exists', return_value=True):
            with pytest.raises(StatementParseError) as exc_info:
                StatementPdfParser().parse_statement(uri)
        assert "date pattern" in str(exc_info.value).lower()

    @patch('ledger.util.pdf_parser.fitz')
    def test_missing_balance_raises(self, mock_fitz, mock_fitz_doc):
        mock_fitz.open.return_value = mock_fitz_doc("""
        January 15, 2024 through February 14, 2024
        No balances here
        """)
        uri = AccountUri.from_string(
            '2024/checking-chase-personal/2024-01-15--2024-02-14-checking-chase-personal.pdf'
        )
        with patch('pathlib.Path.exists', return_value=True):
            with pytest.raises(StatementParseError) as exc_info:
                StatementPdfParser().parse_statement(uri)
        assert "balance" in str(exc_info.value).lower()


class TestStatementPatterns:
    def test_all_date_patterns_have_balance_patterns(self):
        for account_type in STATEMENT_DATE_PATTERNS:
            assert account_type in STATEMENT_BALANCE_PATTERNS

    def test_balance_patterns_have_start_and_end(self):
        for account_type, patterns in STATEMENT_BALANCE_PATTERNS.items():
            assert 'start' in patterns
            assert 'end' in patterns

