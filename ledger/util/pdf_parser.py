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


CHASE_DATE = (r'([A-Za-z]+ [0-9]{1,2}, [0-9]{4}) through ([A-Za-z]+ [0-9]{1,2}, [0-9]{4})', '%B %d, %Y')
CHASE_CC_DATE = (r'Opening/Closing Date\s+([0-9]{2}/[0-9]{2}/[0-9]{2}) - ([0-9]{2}/[0-9]{2}/[0-9]{2})', '%m/%d/%y')
CITI_DATE = (r'Billing Period:\s*([0-9]{2}/[0-9]{2}/[0-9]{2,4})\s*-\s*([0-9]{2}/[0-9]{2}/[0-9]{2,4})', '%m/%d/%y')

STATEMENT_DATE_PATTERNS = {
    'checking-chase-personal': {'pattern': CHASE_DATE[0], 'format': CHASE_DATE[1]},
    'checking-chase-business': {'pattern': CHASE_DATE[0], 'format': CHASE_DATE[1]},
    'creditcard-chase-personal': {'pattern': CHASE_CC_DATE[0], 'format': CHASE_CC_DATE[1]},
    'creditcard-citi-business': {'pattern': CITI_DATE[0], 'format': CITI_DATE[1]},
    'creditcard-citi-personal': {'pattern': CITI_DATE[0], 'format': CITI_DATE[1]},
}

CHASE_BAL = {'start': r'Beginning Balance\s+\$?([\d,]+\.\d{2})', 'end': r'Ending Balance\s+\$?([\d,]+\.\d{2})'}
CHASE_BIZ_BAL = {'start': r'Beginning Balance\s+\$?([\d,]+\.\d{2})', 'end': r'Ending Balance\s+\d*\s*\$?([\d,]+\.\d{2})'}
CC_BAL = {'start': r'Previous Balance\s+\$?([\d,]+\.\d{2})', 'end': r'New Balance\s+\$?([\d,]+\.\d{2})'}

STATEMENT_BALANCE_PATTERNS = {
    'checking-chase-personal': CHASE_BAL,
    'checking-chase-business': CHASE_BIZ_BAL,
    'creditcard-chase-personal': CC_BAL,
    'creditcard-citi-business': CC_BAL,
    'creditcard-citi-personal': CC_BAL,
}


def get_account_type_prefix(account_slug: str) -> str:
    """Extract account type prefix (e.g., 'checking-chase-personal-1381' -> 'checking-chase-personal')."""
    if account_slug in STATEMENT_DATE_PATTERNS:
        return account_slug
    parts = account_slug.rsplit('-', 1)
    if len(parts) == 2 and parts[1].isdigit() and parts[0] in STATEMENT_DATE_PATTERNS:
        return parts[0]
    for key in STATEMENT_DATE_PATTERNS:
        if account_slug.startswith(key):
            return key
    raise StatementParseError(f"No parser pattern found for account: {account_slug}")


class StatementPdfParser:
    """Parser for extracting statement data from PDF files."""

    def parse_statement(self, uri: AccountUri) -> StatementData:
        """Parse a PDF statement and extract dates and balances."""
        pdf_path, account_slug = uri.pdf(), uri.account_slug
        logger.info(f"Parsing statement: {pdf_path}")
        if not pdf_path.exists():
            raise StatementParseError(f"PDF file not found: {pdf_path}")

        account_type = get_account_type_prefix(account_slug)
        text = self._extract_text(pdf_path)
        start_date, end_date = self._extract_dates(text, account_type, pdf_path)
        start_balance, end_balance = self._extract_balances(text, account_type, pdf_path)

        logger.info(f"Parsed: {account_slug} {start_date} to {end_date}, ${start_balance} to ${end_balance}")
        return StatementData(account_slug, start_date, end_date, start_balance, end_balance, str(pdf_path))

    def _extract_text(self, pdf_path: Path) -> str:
        try:
            with fitz.open(pdf_path) as doc:
                return '\n'.join(page.get_text() for page in doc)
        except Exception as e:
            raise StatementParseError(f"Failed to read PDF {pdf_path}: {e}")

    def _extract_dates(self, text: str, account_type: str, pdf_path: Path) -> tuple[date, date]:
        if account_type not in STATEMENT_DATE_PATTERNS:
            raise StatementParseError(f"No date pattern for account type: {account_type}")
        info = STATEMENT_DATE_PATTERNS[account_type]
        match = re.search(info['pattern'], text)
        if not match:
            raise StatementParseError(f"Could not find date pattern in {pdf_path}")
        try:
            return (datetime.strptime(match.group(1), info['format']).date(),
                    datetime.strptime(match.group(2), info['format']).date())
        except ValueError as e:
            raise StatementParseError(f"Failed to parse dates: {e}")

    def _extract_balances(self, text: str, account_type: str, pdf_path: Path) -> tuple[Decimal, Decimal]:
        if account_type not in STATEMENT_BALANCE_PATTERNS:
            raise StatementParseError(f"No balance pattern for account type: {account_type}")
        info = STATEMENT_BALANCE_PATTERNS[account_type]
        start_match, end_match = re.search(info['start'], text), re.search(info['end'], text)
        if not start_match:
            raise StatementParseError(f"Could not find start balance in {pdf_path}")
        if not end_match:
            raise StatementParseError(f"Could not find end balance in {pdf_path}")
        try:
            return (Decimal(start_match.group(1).replace(',', '')),
                    Decimal(end_match.group(1).replace(',', '')))
        except Exception as e:
            raise StatementParseError(f"Failed to parse balance amounts: {e}")


def parse_statement_pdf(uri: AccountUri) -> StatementData:
    """Convenience function to parse a statement PDF."""
    return StatementPdfParser().parse_statement(uri)
