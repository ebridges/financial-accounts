# test_chase_csv.py
"""Tests for Chase CSV parser."""
import pytest
import tempfile
import os
from decimal import Decimal
from datetime import date

from ledger.util.chase_csv import ChaseCsvParser


class TestChaseCsvParserNormalizePayee:
    """Tests for payee normalization."""

    def test_normalize_empty_string(self):
        assert ChaseCsvParser.normalize_payee("") == ""
        assert ChaseCsvParser.normalize_payee(None) == ""

    def test_normalize_uppercase(self):
        result = ChaseCsvParser.normalize_payee("whole foods market")
        assert result == "WHOLE FOODS MARKET"

    def test_normalize_collapse_whitespace(self):
        result = ChaseCsvParser.normalize_payee("CHASE   CREDIT   CRD")
        assert result == "CHASE CREDIT CRD"

    def test_normalize_strip_ppd_id(self):
        result = ChaseCsvParser.normalize_payee("CHASE CREDIT CRD AUTOPAY PPD ID: 4760039224")
        assert result == "CHASE CREDIT CRD AUTOPAY"

    def test_normalize_strip_card_number_xxxx(self):
        result = ChaseCsvParser.normalize_payee("PAYMENT TO CARD XXXX1234")
        assert result == "PAYMENT TO CARD"

    def test_normalize_strip_card_number_dots(self):
        result = ChaseCsvParser.normalize_payee("Online Transfer from CHK ...1381")
        assert result == "ONLINE TRANSFER FROM CHK"

    def test_normalize_strip_trailing_date(self):
        result = ChaseCsvParser.normalize_payee("Payment to Chase card ending in 6063 07/14")
        assert result == "PAYMENT TO CHASE CARD ENDING IN 6063"

    def test_normalize_strip_transaction_number(self):
        result = ChaseCsvParser.normalize_payee(
            "Online Transfer to CHK ...1605 transaction#: 14782136085"
        )
        assert result == "ONLINE TRANSFER TO CHK"

    def test_normalize_strip_trailing_reference(self):
        result = ChaseCsvParser.normalize_payee("AMAZON MARKETPLACE 123456789")
        assert result == "AMAZON MARKETPLACE"


class TestChaseCsvParserCheckingFormat:
    """Tests for parsing Chase checking account CSV format."""

    @pytest.fixture
    def checking_csv_content(self):
        return """Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
DEBIT,09/26/2022,CHASE CREDIT CRD AUTOPAY,-620.00,ACH_DEBIT,1234.56,
CREDIT,09/25/2022,DIRECT DEPOSIT PAYROLL,2500.00,ACH_CREDIT,1854.56,
"""

    @pytest.fixture
    def checking_csv_file(self, checking_csv_content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(checking_csv_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_parse_checking_csv(self, checking_csv_file):
        parser = ChaseCsvParser()
        parser.init_from_csv_file(
            checking_csv_file,
            'Assets:Checking Accounts:checking-chase-personal-1381'
        )

        assert parser.account_type == 'checking'
        assert len(parser.transactions) == 2
        assert parser.transactions[0]['description'] == 'CHASE CREDIT CRD AUTOPAY'
        assert parser.transactions[0]['amount'] == '-620.00'

    def test_checking_transaction_data(self, checking_csv_file):
        parser = ChaseCsvParser()
        parser.init_from_csv_file(
            checking_csv_file,
            'Assets:Checking Accounts:checking-chase-personal-1381'
        )

        data = parser.as_transaction_data(book_id=1)
        assert len(data) == 2

        # Check first transaction
        txn = data[0]
        assert txn['book_id'] == 1
        assert txn['transaction_date'] == date(2022, 9, 26)
        assert txn['transaction_description'] == 'CHASE CREDIT CRD AUTOPAY'
        assert 'payee_norm' in txn
        assert len(txn['splits']) == 2

        # Check splits balance
        total = sum(s['amount'] for s in txn['splits'])
        assert total == Decimal('0')


class TestChaseCsvParserCreditFormat:
    """Tests for parsing Chase credit card CSV format."""

    @pytest.fixture
    def credit_csv_content(self):
        return """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
09/24/2022,09/26/2022,WHOLE FOODS MARKET,Groceries,Sale,-45.67,
09/23/2022,09/25/2022,AUTOMATIC PAYMENT - THANK,Payment,Payment,500.00,
"""

    @pytest.fixture
    def credit_csv_file(self, credit_csv_content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(credit_csv_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_parse_credit_csv(self, credit_csv_file):
        parser = ChaseCsvParser()
        parser.init_from_csv_file(
            credit_csv_file,
            'Liabilities:Credit Cards:creditcard-chase-personal-6063'
        )

        assert parser.account_type == 'credit'
        assert len(parser.transactions) == 2
        assert parser.transactions[0]['description'] == 'WHOLE FOODS MARKET'
        assert parser.transactions[0]['category'] == 'Groceries'

    def test_credit_transaction_data(self, credit_csv_file):
        parser = ChaseCsvParser()
        parser.init_from_csv_file(
            credit_csv_file,
            'Liabilities:Credit Cards:creditcard-chase-personal-6063'
        )

        data = parser.as_transaction_data(book_id=1)
        assert len(data) == 2

        # Check amounts are correct
        assert data[0]['splits'][0]['amount'] == Decimal('-45.67')
        assert data[0]['splits'][1]['amount'] == Decimal('45.67')


class TestChaseCsvParserCoverageDates:
    """Tests for coverage date extraction."""

    @pytest.fixture
    def csv_with_dates(self):
        content = """Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
DEBIT,01/15/2024,Transaction 1,-100.00,ACH_DEBIT,1000.00,
DEBIT,01/10/2024,Transaction 2,-50.00,ACH_DEBIT,1100.00,
DEBIT,01/25/2024,Transaction 3,-75.00,ACH_DEBIT,950.00,
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_get_coverage_dates(self, csv_with_dates):
        parser = ChaseCsvParser()
        parser.init_from_csv_file(csv_with_dates, 'Test:Account')

        start, end = parser.get_coverage_dates()
        assert start == date(2024, 1, 10)
        assert end == date(2024, 1, 25)

    def test_coverage_dates_empty_file(self):
        parser = ChaseCsvParser()
        parser.transactions = []
        start, end = parser.get_coverage_dates()
        assert start is None
        assert end is None


class TestChaseCsvParserQifConversion:
    """Tests for QIF conversion."""

    @pytest.fixture
    def simple_csv(self):
        content = """Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
DEBIT,09/26/2022,TEST TRANSACTION,-100.00,ACH_DEBIT,1000.00,
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_to_qif_string(self, simple_csv):
        parser = ChaseCsvParser()
        parser.init_from_csv_file(simple_csv, 'Assets:Checking:Test')

        qif = parser.to_qif_string()

        assert '!Account' in qif
        assert 'NAssets:Checking:Test' in qif
        assert '!Type:Bank' in qif
        assert 'PTEST TRANSACTION' in qif
        assert 'T-100.00' in qif
        assert 'D09/26/2022' in qif

