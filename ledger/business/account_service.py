# account_service.py
"""
Account service for managing accounts within a book.

This service is book-scoped - all operations apply to a single book.
Use via BookContext for proper session management.

Usage:
    with BookContext("personal", DB_URL) as ctx:
        accounts = ctx.accounts.list_accounts()
        account = ctx.accounts.lookup_by_name("Assets:Checking")
"""
from ledger.db.data_access import DAL
from ledger.db.models import Book, Account


class AccountService:
    """
    Service for account operations within a specific book.
    
    This service does not manage its own session - it receives a DAL
    and Book from BookContext.
    """
    
    def __init__(self, dal: DAL, book: Book):
        """
        Initialize AccountService with shared DAL and book.
        
        Args:
            dal: Data access layer (shared session)
            book: The Book this service operates on
        """
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
        """
        Add a new account to this book.
        
        Args:
            parent_code: Code of the parent account (optional)
            parent_name: Name of the parent account (optional)
            acct_name: Short name of the account
            full_name: Full hierarchical name (e.g., "Assets:Checking")
            acct_code: Unique code for the account
            acct_type: Account type (ASSET, LIABILITY, etc.)
            description: Account description
            hidden: Whether account is hidden
            placeholder: Whether account is a placeholder
            
        Returns:
            The created Account object
        """
        parent_id = None
        if parent_name:
            parent_acct = self._dal.get_account_by_name_for_book(
                self._book.id, parent_code, parent_name
            )
            if not parent_acct:
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
        """
        Look up an account by its full name within this book.
        
        Args:
            account_name: Full account name (e.g., "Assets:Checking")
            
        Returns:
            The Account object
            
        Raises:
            Exception: If account not found
        """
        account = self._dal.get_account_by_fullname_for_book(
            book_id=self._book.id, acct_fullname=account_name
        )
        if not account:
            raise Exception(f"No account found with name '{account_name}'.")
        return account

    def lookup_by_id(self, account_id: int) -> Account:
        """
        Look up an account by its ID.
        
        Note: account_id is globally unique, so this doesn't require book context.
        
        Args:
            account_id: The account ID
            
        Returns:
            The Account object
            
        Raises:
            Exception: If account not found
        """
        account = self._dal.get_account(account_id=account_id)
        if not account:
            raise Exception(f"No account found with id '{account_id}'.")
        return account
