# data_access.py
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from financial_accounts.db.models import Book, Account, Transactions, Split


def check_for_circular_path(
    session: Session, account_id: str, parent_account_id: Optional[str]
) -> bool:
    """
    Returns True if a cycle is found, False otherwise.
    We'll do a simple upward traversal from parent_account_id until we either
    reach None or the 'account_id' itself.
    """
    if not parent_account_id:
        return False  # no parent => no cycle

    current_id = parent_account_id
    while current_id is not None:
        if current_id == account_id:
            return True
        parent = session.query(Account.parent_account_id).filter(Account.id == current_id).first()
        if parent is None or parent[0] is None:
            return False
        current_id = parent[0]
    return False


class DAL:
    def __init__(self, session):
        self.session = session

    def close(self):
        self.session.close()

    # --------------------------------------------------------------------------
    # Book
    # --------------------------------------------------------------------------
    def create_book(self, name: str) -> Book:
        new_id = uuid.uuid4()
        book = Book(id=new_id, name=name)
        self.session.add(book)
        self.session.commit()
        return book

    def get_book(self, book_id: str) -> Optional[Book]:
        return self.session.query(Book).filter_by(id=book_id).one_or_none()

    def get_book_by_name(self, name: str) -> Optional[Book]:
        return self.session.query(Book).filter_by(name=name).one_or_none()

    def list_books(self) -> List[Book]:
        return self.session.query(Book).all()

    def update_book_name(self, book_id: str, new_name: str) -> Optional[Book]:
        book = self.session.query(Book).filter_by(id=book_id).one_or_none()
        if not book:
            return None
        book.name = new_name
        self.session.commit()
        return book

    def delete_book(self, book_id: str) -> bool:
        book = self.session.query(Book).filter_by(id=book_id).one_or_none()
        if not book:
            return False
        self.session.delete(book)
        self.session.commit()
        return True

    # --------------------------------------------------------------------------
    # Account
    # --------------------------------------------------------------------------
    def create_account(
        self,
        book_id: str,
        acct_type: str,  # or AccountTypeEnum if you prefer
        code: str,
        name: str,
        parent_account_id: Optional[str] = None,
        description: Optional[str] = None,
        hidden: bool = False,
        placeholder: bool = False,
    ) -> Account:
        """
        Creates a new Account. The acct_type param must be one of
        ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY').
        """
        new_id = uuid.uuid4()

        # Check for circular references
        if parent_account_id:
            if check_for_circular_path(self.session, str(new_id), parent_account_id):
                raise ValueError("Circular parent reference detected.")

        account = Account(
            id=new_id,
            book_id=book_id,
            acct_type=acct_type,  # If using an Enum, do acct_type.value
            code=code,
            name=name,
            parent_account_id=parent_account_id,
            description=description,
            hidden=hidden,
            placeholder=placeholder,
        )
        self.session.add(account)
        self.session.commit()
        return account

    def get_account(self, account_id: str) -> Optional[Account]:
        return self.session.query(Account).filter_by(id=account_id).one_or_none()

    def get_account_by_name_for_book(self, book_id: str, acct_name: str) -> Optional[Account]:
        return self.session.query(Account).filter_by(book_id=book_id, name=acct_name).one_or_none()

    def update_account(self, account_id: str, **kwargs) -> Optional[Account]:
        """
        Updates an account. If parent_account_id changes, verify no circular references.
        """
        account = self.session.query(Account).filter_by(id=account_id).one_or_none()
        if not account:
            return None

        new_parent_id = kwargs.get("parent_account_id", account.parent_account_id)
        if new_parent_id != account.parent_account_id:
            # check for cycle
            if check_for_circular_path(self.session, account_id, new_parent_id):
                raise ValueError("Circular parent reference detected.")

        # updatable fields
        for field in [
            "book_id",
            "acct_type",
            "code",
            "name",
            "description",
            "hidden",
            "placeholder",
            "parent_account_id",
        ]:
            if field in kwargs:
                setattr(account, field, kwargs[field])

        self.session.commit()
        return account

    def delete_account(self, account_id: str) -> bool:
        account = self.session.query(Account).filter_by(id=account_id).one_or_none()
        if not account:
            return False
        self.session.delete(account)
        self.session.commit()
        return True

    def list_accounts_for_book(self, book_id: str) -> List[Account]:
        return self.session.query(Account).filter_by(book_id=book_id).all()

    # --------------------------------------------------------------------------
    # Transactions
    # --------------------------------------------------------------------------
    def create_transaction(
        self, book_id: str, transaction_date, transaction_description: str
    ) -> Transactions:
        new_id = uuid.uuid4()
        txn = Transactions(
            id=new_id,
            book_id=book_id,
            transaction_date=transaction_date,
            transaction_description=transaction_description,
        )
        self.session.add(txn)
        self.session.commit()
        return txn

    def get_transaction(self, txn_id: str) -> Optional[Transactions]:
        return self.session.query(Transactions).filter_by(id=txn_id).one_or_none()

    def list_transactions_for_book(self, book_id: str) -> List[Transactions]:
        return self.session.query(Transactions).filter_by(book_id=book_id).all()

    def update_transaction(self, txn_id: str, **kwargs) -> Optional[Transactions]:
        txn = self.session.query(Transactions).filter_by(id=txn_id).one_or_none()
        if not txn:
            return None

        for field in ["transaction_date", "transaction_description", "book_id"]:
            if field in kwargs:
                setattr(txn, field, kwargs[field])

        self.session.commit()
        return txn

    def delete_transaction(self, txn_id: str) -> bool:
        txn = self.session.query(Transactions).filter_by(id=txn_id).one_or_none()
        if not txn:
            return False
        self.session.delete(txn)
        self.session.commit()
        return True

    # --------------------------------------------------------------------------
    # Split
    # --------------------------------------------------------------------------
    def create_split(
        self,
        transaction_id: str,
        account_id: str,
        amount,
        memo: str = None,
        reconcile_state: str = 'n',
    ) -> Split:
        new_id = uuid.uuid4()
        spl = Split(
            id=new_id,
            transaction_id=transaction_id,
            account_id=account_id,
            amount=amount,
            memo=memo,
            reconcile_state=reconcile_state,
        )
        self.session.add(spl)
        self.session.commit()
        return spl

    def get_split(self, split_id: str) -> Optional[Split]:
        return self.session.query(Split).filter_by(id=split_id).one_or_none()

    def update_split(self, split_id: str, **kwargs) -> Optional[Split]:
        spl = self.session.query(Split).filter_by(id=split_id).one_or_none()
        if not spl:
            return None

        for field in [
            "transaction_id",
            "account_id",
            "amount",
            "memo",
            "reconcile_date",
            "reconcile_state",
        ]:
            if field in kwargs:
                setattr(spl, field, kwargs[field])

        self.session.commit()
        return spl

    def delete_split(self, split_id: str) -> bool:
        spl = self.session.query(Split).filter_by(id=split_id).one_or_none()
        if not spl:
            return False
        self.session.delete(spl)
        self.session.commit()
        return True

    def list_splits_for_transaction(self, txn_id: str) -> List[Split]:
        return self.session.query(Split).filter_by(transaction_id=txn_id).all()

    def list_splits_for_account(self, account_id: str) -> List[Split]:
        return self.session.query(Split).filter_by(account_id=account_id).all()
