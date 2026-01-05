"""PDF statement parser for extracting dates and balances from bank statements."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from logging import getLogger
from pathlib import Path
import re
from typing import TYPE_CHECKING

import fitz  # PyMuPDF

if TYPE_CHECKING:
    from ledger.util.statement_uri import AccountUri

logger = getLogger(__name__)


@dataclass
class StatementData:
    account_slug: str
    start_date: date
    end_date: date
    start_balance: Decimal
    end_balance: Decimal
    pdf_path: str


class StatementParseError(Exception):
    pass


STATEMENT_PATTERNS = {
    'checking-chase-personal': {
        'date_pattern': r'([A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4})\s*through\s*([A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4})',
        'date_format': '%B %d, %Y',
        # Balances extracted by account-specific logic (see _extract_chase_checking_balances)
        'start_bal': None,
        'end_bal': None,
        'has_account_specific_balances': True,
    },
    'checking-chase-business': {
        'date_pattern': r'([A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4})\s*through\s*([A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4})',
        'date_format': '%B %d, %Y',
        'start_bal': r'Beginning Balance\s+(-?\$?[\d,]+\.\d{2})',
        'end_bal': r'Ending Balance\s+\d*\s*(-?\$?[\d,]+\.\d{2})',
    },
    'creditcard-chase-personal': {
        'date_pattern': r'Opening/Closing Date\s+([0-9]{2}/[0-9]{2}/[0-9]{2})\s*-\s*([0-9]{2}/[0-9]{2}/[0-9]{2})',
        'date_format': '%m/%d/%y',
        'start_bal': r'Previous Balance\s+(-?\$?[\d,]+\.\d{2})',
        'end_bal': r'New Balance\s+(-?\$?[\d,]+\.\d{2})',
    },
    'creditcard-citi-business': {
        'date_pattern': r'([0-9]{2}/[0-9]{2}/[0-9]{2})-([0-9]{2}/[0-9]{2}/[0-9]{2})',
        'date_format': '%m/%d/%y',
        'start_bal': r'Previous balance\s*\n(-?\$?[\d,]+\.\d{2})',
        'end_bal': r'New balance\s*\n(-?\$?[\d,]+\.\d{2})',
    },
    'creditcard-citi-personal': {
        'date_pattern': r'([0-9]{2}/[0-9]{2}/[0-9]{2})-([0-9]{2}/[0-9]{2}/[0-9]{2})',
        'date_format': '%m/%d/%y',
        'start_bal': r'Previous balance\s*\n(-?\$?[\d,]+\.\d{2})',
        'end_bal': r'New balance\s*\n(-?\$?[\d,]+\.\d{2})',
    },
}


def get_patterns(account_slug: str) -> dict:
    """Get patterns for an account slug (e.g., 'checking-chase-personal-1381')."""
    for key in STATEMENT_PATTERNS:
        if account_slug.startswith(key):
            return STATEMENT_PATTERNS[key]
    raise StatementParseError(f"No parser pattern found for account: {account_slug}")


class StatementPdfParser:
    """Parser for extracting statement data from PDF files."""

    def parse_statement(self, uri: AccountUri) -> StatementData:
        """Parse a PDF statement and extract dates and balances."""
        pdf_path, account_slug = uri.pdf(), uri.account_slug
        logger.info(f"Parsing statement: {pdf_path}")
        if not pdf_path.exists():
            raise StatementParseError(f"PDF file not found: {pdf_path}")

        patterns = get_patterns(account_slug)
        text = self._extract_text(pdf_path)
        start_date, end_date = self._extract_dates(text, patterns, pdf_path)

        if patterns.get('has_account_specific_balances'):
            start_balance, end_balance = self._extract_chase_checking_balances(text, account_slug, pdf_path)
        else:
            start_balance, end_balance = self._extract_balances(text, patterns, pdf_path)

        logger.info(f"Parsed: {account_slug} {start_date} to {end_date}, ${start_balance} to ${end_balance}")
        return StatementData(account_slug, start_date, end_date, start_balance, end_balance, str(pdf_path))

    def _extract_text(self, pdf_path: Path) -> str:
        try:
            with fitz.open(pdf_path) as doc:
                return '\n'.join(page.get_text() for page in doc)
        except Exception as e:
            raise StatementParseError(f"Failed to read PDF {pdf_path}: {e}")

    def _extract_dates(self, text: str, patterns: dict, pdf_path: Path) -> tuple[date, date]:
        match = re.search(patterns['date_pattern'], text)
        if not match:
            raise StatementParseError(f"Could not find date pattern in {pdf_path}")
        try:
            return (datetime.strptime(match.group(1), patterns['date_format']).date(),
                    datetime.strptime(match.group(2), patterns['date_format']).date())
        except ValueError as e:
            raise StatementParseError(f"Failed to parse dates: {e}")

    def _extract_balances(self, text: str, patterns: dict, pdf_path: Path) -> tuple[Decimal, Decimal]:
        start_match = re.search(patterns['start_bal'], text)
        end_match = re.search(patterns['end_bal'], text)
        if not start_match:
            raise StatementParseError(f"Could not find start balance in {pdf_path}")
        if not end_match:
            raise StatementParseError(f"Could not find end balance in {pdf_path}")
        try:
            return (self._parse_amount(start_match.group(1)),
                    self._parse_amount(end_match.group(1)))
        except Exception as e:
            raise StatementParseError(f"Failed to parse balance amounts: {e}")

    def _extract_chase_checking_balances(self, text: str, account_slug: str, pdf_path: Path) -> tuple[Decimal, Decimal]:
        """Extract account-specific balances from Chase checking consolidated statements.
        
        Chase checking PDFs contain a Consolidated Balance Summary with separate
        entries for each account (e.g., 1381, 1605). Format is:
        Chase Checking
        000000816191381
        $1,767.21        <- beginning balance
        $3,207.34        <- ending balance
        """
        # Extract account number suffix (e.g., "1381" from "checking-chase-personal-1381")
        parts = account_slug.split('-')
        if len(parts) < 4 or not parts[-1].isdigit():
            raise StatementParseError(f"Cannot extract account number from slug: {account_slug}")
        acct_num_suffix = parts[-1]
        
        # Find the account entry in Consolidated Balance Summary
        # Pattern: account number followed by two balance amounts on separate lines
        pattern = rf'0+\d*{acct_num_suffix}\s*\n\s*\$?([\d,]+\.\d{{2}})\s*\n\s*\$?([\d,]+\.\d{{2}})'
        match = re.search(pattern, text)
        
        if not match:
            raise StatementParseError(
                f"Could not find balances for account {acct_num_suffix} in {pdf_path}"
            )
        
        try:
            start_balance = self._parse_amount(match.group(1))
            end_balance = self._parse_amount(match.group(2))
            return (start_balance, end_balance)
        except Exception as e:
            raise StatementParseError(f"Failed to parse Chase checking balances: {e}")

    def _parse_amount(self, text: str) -> Decimal:
        """Parse amount string, handling $, commas, and negative signs."""
        clean = text.replace('$', '').replace(',', '')
        return Decimal(clean)


def parse_statement_pdf(uri: AccountUri) -> StatementData:
    """Convenience function to parse a statement PDF."""
    return StatementPdfParser().parse_statement(uri)
