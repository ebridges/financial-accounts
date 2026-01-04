"""Tests for ReconciliationService."""
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock

from ledger.business.reconciliation_service import (
    ReconciliationService, ReconciliationResult, display_reconciliation_result,
)
from ledger.db.models import AccountStatement, Transaction, Split


class TestReconciliationService:
    """Tests for ReconciliationService class."""

    def test_reconcile_statement_matches(self, mock_ctx, sample_statement, sample_transactions):
        """Reconciliation succeeds when computed balance matches."""
        mock_ctx.dal.get_account_statement.return_value = sample_statement
        mock_ctx.dal.query_transactions_for_account_in_range.return_value = sample_transactions
        
        service = ReconciliationService(mock_ctx)
        result = service.reconcile_statement(1)
        
        assert result.matches is True
        assert result.computed_end_balance == Decimal('1500.00')
        assert result.discrepancy == Decimal('0.00')
        assert result.transaction_count == 2
        
        # Verify update was called
        mock_ctx.dal.update_account_statement_reconciliation.assert_called_once()
        call_args = mock_ctx.dal.update_account_statement_reconciliation.call_args
        assert call_args.kwargs['reconcile_status'] == 'r'

    def test_reconcile_statement_discrepancy(self, mock_ctx, sample_statement):
        """Reconciliation detects discrepancy."""
        # Transactions only sum to +400, but end_balance is +500 from start
        txns = []
        split = MagicMock(spec=Split)
        split.account_id = 10
        split.amount = Decimal('400.00')
        txn = MagicMock(spec=Transaction)
        txn.splits = [split]
        txns.append(txn)
        
        mock_ctx.dal.get_account_statement.return_value = sample_statement
        mock_ctx.dal.query_transactions_for_account_in_range.return_value = txns
        
        service = ReconciliationService(mock_ctx)
        result = service.reconcile_statement(1)
        
        assert result.matches is False
        assert result.computed_end_balance == Decimal('1400.00')
        assert result.discrepancy == Decimal('-100.00')
        
        # Verify update was called with discrepancy status
        call_args = mock_ctx.dal.update_account_statement_reconciliation.call_args
        assert call_args.kwargs['reconcile_status'] == 'd'

    def test_reconcile_statement_not_found(self, mock_ctx):
        """Raises error if statement not found."""
        mock_ctx.dal.get_account_statement.return_value = None
        
        service = ReconciliationService(mock_ctx)
        
        with pytest.raises(ValueError) as exc_info:
            service.reconcile_statement(999)
        assert "not found" in str(exc_info.value)

    def test_reconcile_statement_no_transactions(self, mock_ctx, sample_statement):
        """Handles period with no transactions."""
        # End balance same as start (no change expected)
        sample_statement.end_balance = Decimal('1000.00')
        
        mock_ctx.dal.get_account_statement.return_value = sample_statement
        mock_ctx.dal.query_transactions_for_account_in_range.return_value = []
        
        service = ReconciliationService(mock_ctx)
        result = service.reconcile_statement(1)
        
        assert result.matches is True
        assert result.computed_end_balance == Decimal('1000.00')
        assert result.transaction_count == 0

    def test_reconcile_by_account(self, mock_ctx, sample_statement, sample_transactions):
        """Reconcile all statements for an account."""
        # Create two statements
        stmt2 = MagicMock(spec=AccountStatement)
        stmt2.id = 2
        stmt2.discrepancy = Decimal('0')  # Already reconciled
        
        sample_statement.discrepancy = None  # Not yet reconciled
        
        mock_ctx.dal.list_account_statements_for_account.return_value = [sample_statement, stmt2]
        mock_ctx.dal.get_account_statement.return_value = sample_statement
        mock_ctx.dal.query_transactions_for_account_in_range.return_value = sample_transactions
        
        # Mock account lookup
        account = MagicMock()
        account.name = 'checking-chase-personal-1381'
        mock_ctx.accounts.list_accounts.return_value = [account]
        
        service = ReconciliationService(mock_ctx)
        results = service.reconcile_by_account('checking-chase-personal-1381')
        
        # Should only reconcile statement 1 (stmt2 already reconciled)
        assert len(results) == 1

    def test_reconcile_by_account_all_periods(self, mock_ctx, sample_statement, sample_transactions):
        """Reconcile all periods including already-reconciled."""
        # Both statements will be reconciled
        stmt2 = MagicMock(spec=AccountStatement)
        stmt2.id = 2
        stmt2.discrepancy = Decimal('0')
        
        sample_statement.discrepancy = Decimal('0')
        
        mock_ctx.dal.list_account_statements_for_account.return_value = [sample_statement, stmt2]
        mock_ctx.dal.get_account_statement.side_effect = [sample_statement, stmt2]
        mock_ctx.dal.query_transactions_for_account_in_range.return_value = sample_transactions
        
        # Set up stmt2 balances for reconciliation
        stmt2.start_date = date(2024, 2, 1)
        stmt2.end_date = date(2024, 2, 29)
        stmt2.start_balance = Decimal('1500.00')
        stmt2.end_balance = Decimal('2000.00')
        stmt2.account_id = 10
        stmt2.account = MagicMock(name='Test Checking')
        
        # Mock account lookup
        account = MagicMock()
        account.name = 'checking-chase-personal-1381'
        mock_ctx.accounts.list_accounts.return_value = [account]
        
        service = ReconciliationService(mock_ctx)
        results = service.reconcile_by_account('checking-chase-personal-1381', all_periods=True)
        
        assert len(results) == 2


class TestDisplayReconciliationResult:
    """Tests for display_reconciliation_result function."""

    def test_display_matched(self, capsys):
        """Display matched result."""
        stmt = MagicMock(spec=AccountStatement)
        stmt.start_date = date(2024, 1, 1)
        stmt.end_date = date(2024, 1, 31)
        stmt.start_balance = Decimal('1000.00')
        stmt.end_balance = Decimal('1500.00')
        stmt.account = MagicMock()
        stmt.account.name = 'Test Account'
        
        result = ReconciliationResult(
            matches=True,
            computed_end_balance=Decimal('1500.00'),
            discrepancy=Decimal('0.00'),
            transaction_count=5,
            statement=stmt,
        )
        
        display_reconciliation_result(result)
        
        captured = capsys.readouterr()
        assert 'Test Account' in captured.out
        assert 'RECONCILED' in captured.out
        assert '1,500.00' in captured.out

    def test_display_discrepancy(self, capsys):
        """Display discrepancy result."""
        stmt = MagicMock(spec=AccountStatement)
        stmt.start_date = date(2024, 1, 1)
        stmt.end_date = date(2024, 1, 31)
        stmt.start_balance = Decimal('1000.00')
        stmt.end_balance = Decimal('1500.00')
        stmt.account = MagicMock()
        stmt.account.name = 'Test Account'
        
        result = ReconciliationResult(
            matches=False,
            computed_end_balance=Decimal('1400.00'),
            discrepancy=Decimal('-100.00'),
            transaction_count=3,
            statement=stmt,
        )
        
        display_reconciliation_result(result)
        
        captured = capsys.readouterr()
        assert 'DISCREPANCY' in captured.out
        assert '-100.00' in captured.out

