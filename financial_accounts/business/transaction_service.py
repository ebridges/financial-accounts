from typing import List
from decimal import Decimal
from datetime import datetime

from financial_accounts.db.models import Transaction, Split
from financial_accounts.business.base_service import BaseService


class TransactionService(BaseService):
    def insert_bulk(self, txns: List[Transaction]):
        self.data_access.insert_transactions(txns)

    def insert_transaction(self, txn: Transaction):
        return self.data_access.insert_transaction(txn)

    def enter_transaction(
        self, book_name, txn_date, txn_desc, to_acct, from_acct, amount, memo=None
    ):
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise Exception(f"No book found named '{book_name}'.")

        # parse amount
        amt = Decimal(value=amount)

        # parse date
        date = datetime.strptime(txn_date, "%Y-%m-%d").date()

        to_acct = self.data_access.get_account_by_fullname_for_book(book.id, to_acct)
        if not to_acct:
            print(f"Debit account '{to_acct}' not found in book '{book_name}'.")
            return 1

        from_acct = self.data_access.get_account_by_fullname_for_book(book.id, from_acct)
        if not from_acct:
            raise Exception(f"Credit account '{from_acct}' not found in book '{book_name}'.")

        txn = self.data_access.create_transaction(
            book_id=book.id,
            transaction_date=date,
            transaction_description=txn_desc,
            memo=memo,
        )

        self.data_access.create_split(transaction_id=txn.id, account_id=from_acct.id, amount=amt)
        self.data_access.create_split(transaction_id=txn.id, account_id=to_acct.id, amount=-amt)

        return txn.id

    def query_matchable_transactions(
        self,
        book_id: int,
        start_date: datetime.date,
        end_date: datetime.date,
        accounts_to_match_for: List[str] = [],
    ):
        return self.data_access.query_for_unmatched_transactions_in_range(
            book_id, start_date, end_date, accounts_to_match_for
        )

    def delete_transaction(self, transaction_id):
        txn = self.data_access.get_transaction(txn_id=transaction_id)
        if not txn:
            raise ValueError(f'No transaction exists with ID: {transaction_id}')
        return self.data_access.delete_transaction(txn_id=transaction_id)

    def mark_transaction_matched(self, transaction) -> None:
        self.data_access.update_transaction_match_status(transaction)

    def get_all_transactions_for_book(self, book_id):
        return self.data_access.list_transactions_for_book(book_id=book_id)

    def import_transactions_from_qif_data(self, transaction_data_list, account_service):
        """
        Import transactions from QIF data, resolving accounts within this service's session.
        
        Args:
            transaction_data_list: List of transaction data dicts from qif.as_transaction_data()
            account_service: AccountService instance (should share same session context)
        
        Returns:
            List of imported transaction IDs
        """
        imported_ids = []
        
        for data in transaction_data_list:
            transaction = Transaction()
            transaction.book_id = data['book_id']
            transaction.transaction_date = data['transaction_date']
            transaction.transaction_description = data['transaction_description']
            
            transaction.splits = []
            for split_data in data['splits']:
                split = Split()
                split.transaction = transaction
                # Resolve account within this service's session context
                split.account = account_service.lookup_account_by_name(
                    data['book_id'], split_data['account_name']
                )
                split.amount = split_data['amount']
                transaction.splits.append(split)
            
            try:
                txn_id = self.insert_transaction(transaction)
                imported_ids.append(txn_id)
            except Exception as e:
                raise Exception(f"Failed to import transaction '{transaction.transaction_description}': {e}")
        
        return imported_ids
