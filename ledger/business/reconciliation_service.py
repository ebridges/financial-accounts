"""Service for reconciling account statements against transaction sums."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from logging import getLogger
from typing import TYPE_CHECKING

from ledger.db.models import AccountStatement, Transaction

if TYPE_CHECKING:
    from ledger.business.book_context import BookContext

logger = getLogger(__name__)


@dataclass
class ReconciliationResult:
    matches: bool
    computed_end_balance: Decimal
    discrepancy: Decimal
    transaction_count: int
    statement: AccountStatement


class ReconciliationService:
    """Reconcile account statements against transactions."""

    def __init__(self, ctx: BookContext):
        self._ctx = ctx

    def reconcile_statement(self, statement_id: int) -> ReconciliationResult:
        """Reconcile a statement by comparing computed balance against statement balance."""
        statement = self._ctx.dal.get_account_statement(statement_id)
        if not statement:
            raise ValueError(f"Statement with id={statement_id} not found")

        account_name = statement.account.name if statement.account else statement.account_id
        logger.info(f"Reconciling statement id={statement_id}: {account_name} ({statement.start_date} to {statement.end_date})")

        transactions = self._ctx.dal.query_transactions_for_account_in_range(
            book_id=self._ctx.book.id, account_id=statement.account_id,
            start_date=statement.start_date, end_date=statement.end_date,
        )
        logger.debug(f"Found {len(transactions)} transactions in period")

        computed_change = self._compute_balance_change(transactions, statement.account_id)
        computed_end = statement.start_balance + computed_change
        discrepancy = computed_end - statement.end_balance
        matches = abs(discrepancy) < Decimal('0.01')

        self._ctx.dal.update_account_statement_reconciliation(
            statement=statement, computed_end_balance=computed_end,
            discrepancy=discrepancy, reconcile_status='r' if matches else 'd',
        )

        logger.info(f"Reconciliation: {'MATCHED' if matches else 'DISCREPANCY'} (computed={computed_end}, expected={statement.end_balance})")
        return ReconciliationResult(
            matches=matches, computed_end_balance=computed_end,
            discrepancy=discrepancy, transaction_count=len(transactions), statement=statement,
        )

    def _compute_balance_change(self, transactions: list[Transaction], account_id: int) -> Decimal:
        """Sum split amounts for account_id across transactions."""
        total = Decimal('0')
        for txn in transactions:
            for split in txn.splits:
                if split.account_id == account_id:
                    total += split.amount
        return total

    def reconcile_by_account(self, account_slug: str, all_periods: bool = False) -> list[ReconciliationResult]:
        """Reconcile statements for an account. If all_periods=False, only unreconciled."""
        account = self._lookup_account(account_slug)
        if not account:
            raise ValueError(f"Account '{account_slug}' not found")

        statements = self._ctx.dal.list_account_statements_for_account(self._ctx.book.id, account.id)
        results = []
        for stmt in statements:
            if not all_periods and stmt.discrepancy == Decimal('0'):
                continue
            results.append(self.reconcile_statement(stmt.id))
        return results

    def _lookup_account(self, account_slug: str):
        for account in self._ctx.accounts.list_accounts():
            if account.name == account_slug or account_slug in account.full_name:
                return account
        return None


def display_reconciliation_result(result: ReconciliationResult) -> None:
    """Display reconciliation results to stdout (placeholder for future interactive mode)."""
    stmt = result.statement
    name = stmt.account.name if stmt.account else f"account_id={stmt.account_id}"
    print(f"\n=== Reconciliation: {name} ===")
    print(f"Period: {stmt.start_date} to {stmt.end_date}")
    print(f"Transactions: {result.transaction_count}")
    print(f"Statement start: ${stmt.start_balance:,.2f}  end: ${stmt.end_balance:,.2f}")
    print(f"Computed end:    ${result.computed_end_balance:,.2f}  Discrepancy: ${result.discrepancy:,.2f}")
    print(f"Status: {'RECONCILED' if result.matches else 'DISCREPANCY'}")

