# transaction_service.py
"""
Transaction service for managing transactions within a book.

This service is book-scoped - all operations apply to a single book.
Use via BookContext for proper session management.

Usage:
    with BookContext("personal", DB_URL) as ctx:
        txns = ctx.transactions.get_all()
        ctx.transactions.enter_transaction(...)
"""
from typing import List
from decimal import Decimal
from datetime import datetime, date

from ledger.db.models import Transaction, Split, Book
from ledger.db.data_access import DAL


class TransactionService:
    """
    Service for transaction operations within a specific book.
    
    This service does not manage its own session - it receives a DAL
    and Book from BookContext.
    """
    
    def __init__(self, dal: DAL, book: Book):
        """
        Initialize TransactionService with shared DAL and book.
        
        Args:
            dal: Data access layer (shared session)
            book: The Book this service operates on
        """
        self._dal = dal
        self._book = book

    def insert_bulk(self, txns: List[Transaction]):
        """Insert multiple transactions."""
        self._dal.insert_transactions(txns)

    def insert(self, txn: Transaction):
        """
        Insert a single transaction.
        
        Args:
            txn: Transaction object to insert
            
        Returns:
            The inserted transaction
        """
        return self._dal.insert_transaction(txn)

    def enter_transaction(
        self, txn_date: str, txn_desc: str, to_acct: str, from_acct: str, 
        amount: str, memo: str = None
    ):
        """
        Create and enter a new transaction with two splits.
        
        Args:
            txn_date: Transaction date in YYYY-MM-DD format
            txn_desc: Transaction description
            to_acct: Full name of debit account
            from_acct: Full name of credit account
            amount: Transaction amount as string
            memo: Optional memo
            
        Returns:
            The transaction ID
        """
        amt = Decimal(value=amount)
        txn_date_parsed = datetime.strptime(txn_date, "%Y-%m-%d").date()

        to_account = self._dal.get_account_by_fullname_for_book(self._book.id, to_acct)
        if not to_account:
            raise Exception(f"Debit account '{to_acct}' not found in book.")

        from_account = self._dal.get_account_by_fullname_for_book(self._book.id, from_acct)
        if not from_account:
            raise Exception(f"Credit account '{from_acct}' not found in book.")

        txn = self._dal.create_transaction(
            book_id=self._book.id,
            transaction_date=txn_date_parsed,
            transaction_description=txn_desc,
            memo=memo,
        )

        # In double-entry accounting: debit account gets +amount, credit account gets -amount
        self._dal.create_split(transaction_id=txn.id, account_id=to_account.id, amount=amt)    # debit
        self._dal.create_split(transaction_id=txn.id, account_id=from_account.id, amount=-amt)  # credit

        return txn.id

    def query_unmatched(
        self,
        start_date: date,
        end_date: date,
        account_names: List[str] = None,
    ) -> List[Transaction]:
        """
        Query for unmatched transactions within a date range.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            account_names: Optional list of account full names to filter by
            
        Returns:
            List of unmatched transactions
        """
        return self._dal.query_for_unmatched_transactions_in_range(
            self._book.id, start_date, end_date, account_names or []
        )

    def delete(self, transaction_id: int):
        """
        Delete a transaction by ID.
        
        Args:
            transaction_id: ID of transaction to delete
            
        Returns:
            Result of deletion
            
        Raises:
            ValueError: If transaction not found
        """
        txn = self._dal.get_transaction(txn_id=transaction_id)
        if not txn:
            raise ValueError(f'No transaction exists with ID: {transaction_id}')
        return self._dal.delete_transaction(txn_id=transaction_id)

    def mark_matched(self, transaction: Transaction) -> None:
        """
        Mark a transaction as matched.
        
        Args:
            transaction: Transaction to mark as matched
        """
        self._dal.update_transaction_match_status(transaction)

    def get_all(self) -> List[Transaction]:
        """
        Get all transactions in this book.
        
        Returns:
            List of all transactions
        """
        return self._dal.list_transactions_for_book(book_id=self._book.id)
