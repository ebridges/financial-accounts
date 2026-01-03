# account_service.py
"""Account service for managing accounts within a book."""
from logging import getLogger

from ledger.db.data_access import DAL
from ledger.db.models import Book, Account

logger = getLogger(__name__)


class AccountService:
    """Book-scoped service for account operations. Use via BookContext."""
    
    def __init__(self, dal: DAL, book: Book):
        self._dal = dal
        self._book = book
    
    def list_accounts(self):
        """List all accounts in this book."""
        return self._dal.list_accounts_for_book(self._book.id)

    def add_account(
        self,
        parent_code,
        parent_name,
        acct_name,
        full_name,
        acct_code,
        acct_type,
        description,
        hidden,
        placeholder,
    ):
        """Add a new account to this book. Returns the created Account."""
        parent_id = None
        if parent_name:
            parent_acct = self._dal.get_account_by_name_for_book(
                self._book.id, parent_code, parent_name
            )
            if not parent_acct:
                logger.error(f"Parent account '{parent_name}' (code={parent_code}) not found in book '{self._book.name}'")
                raise Exception(f"Parent account named '{parent_name}' not found.")
            parent_id = parent_acct.id

        new_acct = self._dal.create_account(
            book_id=self._book.id,
            name=acct_name,
            code=acct_code,
            acct_type=acct_type,
            description=description,
            hidden=hidden,
            placeholder=placeholder,
            parent_account_id=parent_id,
            full_name=full_name,
        )
        return new_acct

    def lookup_by_name(self, account_name: str) -> Account:
        """Look up account by full name. Raises Exception if not found."""
        account = self._dal.get_account_by_fullname_for_book(
            book_id=self._book.id, acct_fullname=account_name
        )
        if not account:
            logger.error(f"Account '{account_name}' not found in book '{self._book.name}'")
            raise Exception(f"No account found with name '{account_name}'.")
        return account

    def lookup_by_id(self, account_id: int) -> Account:
        """Look up account by ID. Raises Exception if not found."""
        account = self._dal.get_account(account_id=account_id)
        if not account:
            logger.error(f"Account id={account_id} not found")
            raise Exception(f"No account found with id '{account_id}'.")
        return account
