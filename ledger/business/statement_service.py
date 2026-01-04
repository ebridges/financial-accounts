"""Service for importing and managing account statements."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from logging import getLogger
from typing import TYPE_CHECKING

from ledger.db.models import AccountStatement
from ledger.util.pdf_parser import StatementPdfParser, StatementData, StatementParseError
from ledger.util.statement_uri import AccountUri

if TYPE_CHECKING:
    from ledger.business.book_context import BookContext

logger = getLogger(__name__)


class ImportResult(Enum):
    IMPORTED = "imported"
    ALREADY_RECONCILED = "already_reconciled"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    UPDATED = "updated"


@dataclass
class ImportReport:
    result: ImportResult
    statement_id: int | None = None
    message: str = ""
    statement: AccountStatement | None = None


class StatementService:
    """Import and manage account statements."""

    def __init__(self, ctx: BookContext):
        self._ctx = ctx
        self._parser = StatementPdfParser()

    def import_statement(self, uri: AccountUri) -> ImportReport:
        """Import a statement from a PDF file. Returns IMPORTED, ALREADY_RECONCILED, or NEEDS_RECONCILIATION."""
        account_slug = uri.account_slug
        pdf_path = uri.pdf()
        
        logger.info(f"Importing statement: {pdf_path} for account '{account_slug}'")

        try:
            data = self._parser.parse_statement(uri)
        except StatementParseError as e:
            logger.error(f"Failed to parse statement: {e}")
            raise

        account = self._lookup_account(account_slug)
        if not account:
            raise ValueError(f"Account '{account_slug}' not found in book '{self._ctx.book.name}'")

        existing = self._ctx.dal.get_account_statement_by_period(
            book_id=self._ctx.book.id,
            account_id=account.id,
            start_date=data.start_date,
            end_date=data.end_date,
        )
        
        if existing:
            return self._handle_existing_statement(existing, data)
        else:
            return self._create_new_statement(account.id, data)
    
    def _lookup_account(self, account_slug: str):
        """Look up an account by its slug (name)."""
        for account in self._ctx.accounts.list_accounts():
            if account.name == account_slug or account_slug in account.full_name:
                return account
        return None

    def _handle_existing_statement(self, existing: AccountStatement, data: StatementData) -> ImportReport:
        logger.debug(f"Found existing statement id={existing.id}")
        if existing.discrepancy is not None and existing.discrepancy == Decimal('0'):
            logger.info(f"Statement already reconciled: id={existing.id}")
            return ImportReport(
                result=ImportResult.ALREADY_RECONCILED, statement_id=existing.id,
                statement=existing, message=f"Statement for {data.start_date} to {data.end_date} already reconciled"
            )
        logger.info(f"Statement needs reconciliation: id={existing.id}")
        return ImportReport(
            result=ImportResult.NEEDS_RECONCILIATION, statement_id=existing.id,
            statement=existing, message=f"Statement for {data.start_date} to {data.end_date} needs reconciliation"
        )

    def _create_new_statement(self, account_id: int, data: StatementData) -> ImportReport:
        logger.debug(f"Creating new statement for account_id={account_id}")
        statement = self._ctx.dal.create_account_statement(
            book_id=self._ctx.book.id,
            account_id=account_id,
            start_date=data.start_date,
            end_date=data.end_date,
            start_balance=data.start_balance,
            end_balance=data.end_balance,
            statement_path=data.pdf_path,
        )
        
        logger.info(f"Created statement id={statement.id}")
        return ImportReport(
            result=ImportResult.IMPORTED, statement_id=statement.id, statement=statement,
            message=f"Imported statement for {data.start_date} to {data.end_date}, balance: {data.start_balance} to {data.end_balance}"
        )

    def get_statement(self, statement_id: int) -> AccountStatement | None:
        return self._ctx.dal.get_account_statement(statement_id)

    def list_statements(self, account_slug: str | None = None) -> list[AccountStatement]:
        """List all statements, optionally filtered by account."""
        if account_slug:
            account = self._lookup_account(account_slug)
            if not account:
                return []
            return self._ctx.dal.list_account_statements_for_account(self._ctx.book.id, account.id)
        return self._ctx.dal.list_account_statements_for_book(self._ctx.book.id)

