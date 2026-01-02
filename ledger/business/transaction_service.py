# transaction_service.py
"""Transaction service for managing transactions within a book."""
from typing import List
from decimal import Decimal
from datetime import datetime, date

from ledger.db.models import Transaction, Book
from ledger.db.data_access import DAL


class TransactionService:
    """Book-scoped service for transaction operations. Use via BookContext."""
    
    def __init__(self, dal: DAL, book: Book):
        self._dal = dal
        self._book = book

    def insert_bulk(self, txns: List[Transaction]):
        """Insert multiple transactions."""
        self._dal.insert_transactions(txns)

    def insert(self, txn: Transaction):
        """Insert a single transaction. Returns the inserted transaction."""
        return self._dal.insert_transaction(txn)

    def enter_transaction(
        self, txn_date: str, txn_desc: str, to_acct: str, from_acct: str, 
        amount: str, memo: str = None
    ):
        """Create a transaction with two splits (debit/credit). Returns transaction ID."""
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

        # Double-entry: debit account gets +amount, credit account gets -amount
        self._dal.create_split(transaction_id=txn.id, account_id=to_account.id, amount=amt)
        self._dal.create_split(transaction_id=txn.id, account_id=from_account.id, amount=-amt)

        return txn.id

    def query_unmatched(
        self,
        start_date: date,
        end_date: date,
        account_names: List[str] = None,
    ) -> List[Transaction]:
        """Query unmatched transactions in date range, optionally filtered by accounts."""
        return self._dal.query_for_unmatched_transactions_in_range(
            self._book.id, start_date, end_date, account_names or []
        )

    def delete(self, transaction_id: int):
        """Delete a transaction. Raises ValueError if not found."""
        txn = self._dal.get_transaction(txn_id=transaction_id)
        if not txn:
            raise ValueError(f'No transaction exists with ID: {transaction_id}')
        return self._dal.delete_transaction(txn_id=transaction_id)

    def mark_matched(self, transaction: Transaction) -> None:
        """Mark a transaction as matched."""
        self._dal.update_transaction_match_status(transaction)

    def get_all(self) -> List[Transaction]:
        """Get all transactions in this book."""
        return self._dal.list_transactions_for_book(book_id=self._book.id)
