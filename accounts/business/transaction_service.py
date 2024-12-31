from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from accounts.db.data_access import DAL


class TransactionService:
    def __init__(self, db_url):
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def __enter__(self):
        self.session = self.SessionLocal()
        self.data_access = DAL(session=self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.data_access.close()

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
