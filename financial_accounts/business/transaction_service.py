from decimal import Decimal

from financial_accounts.business.base_service import BaseService


class TransactionService(BaseService):
    def enter_transaction(self, book_name, txn_date, txn_desc, debit_acct, credit_acct, amount):
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise Exception(f"No book found named '{book_name}'.")

        # parse amount
        amt = Decimal(value=amount)

        debit_acct = self.data_access.get_account_by_name_for_book(book.id, debit_acct)
        if not debit_acct:
            print(f"Debit account '{debit_acct}' not found in book '{book_name}'.")
            return 1

        credit_acct = self.data_access.get_account_by_name_for_book(book.id, credit_acct)
        if not credit_acct:
            raise Exception(f"Credit account '{credit_acct}' not found in book '{book_name}'.")

        txn = self.data_access.create_transaction(
            book_id=book.id,
            transaction_date=txn_date,
            transaction_description=txn_desc,
        )

        # debit is +, credit is -
        self.data_access.create_split(transaction_id=txn.id, account_id=debit_acct.id, amount=amt)
        self.data_access.create_split(transaction_id=txn.id, account_id=credit_acct.id, amount=-amt)

        return txn.id
