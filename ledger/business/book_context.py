# book_context.py
"""
BookContext provides coordinated access to book-scoped services with a shared session.

All services within a BookContext share:
- The same database session (transactional consistency)
- The same Book instance (no mismatch possible)

Usage:
    with BookContext("personal", DB_URL) as ctx:
        accounts = ctx.accounts.list_accounts()
        ctx.transactions.enter_transaction(...)
        # Automatically commits on success, rolls back on exception
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ledger.db.data_access import DAL
from ledger.db.models import Book


class BookContext:
    """
    Coordinator for book-scoped services with a shared session.
    
    Provides:
    - Shared SQLAlchemy session across all services
    - Single Book instance resolution
    - Automatic commit/rollback on context exit
    """
    
    def __init__(self, book_name: str, db_url: str):
        """
        Initialize BookContext.
        
        Args:
            book_name: Name of the book to operate on
            db_url: Database connection URL
        """
        self.book_name = book_name
        self.db_url = db_url
        self._engine = create_engine(db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)
        self._session = None
        self._dal = None
        self._book = None
        self._accounts = None
        self._transactions = None
    
    def __enter__(self):
        """Enter context manager - create session and resolve book."""
        self._session = self._session_factory()
        self._dal = DAL(session=self._session)
        
        # Resolve and cache the book
        self._book = self._dal.get_book_by_name(self.book_name)
        if not self._book:
            self._session.close()
            raise ValueError(f"Book '{self.book_name}' not found")
        
        # Import here to avoid circular imports
        from ledger.business.account_service import AccountService
        from ledger.business.transaction_service import TransactionService
        
        # Initialize services with shared DAL and book
        self._accounts = AccountService(self._dal, self._book)
        self._transactions = TransactionService(self._dal, self._book)
        
        return self
    
    @property
    def book(self) -> Book:
        """Get the Book instance this context operates on."""
        if self._book is None:
            raise RuntimeError("BookContext not entered - use 'with' statement")
        return self._book
    
    @property
    def accounts(self) -> 'AccountService':
        """Get the AccountService for this book."""
        if self._accounts is None:
            raise RuntimeError("BookContext not entered - use 'with' statement")
        return self._accounts
    
    @property
    def transactions(self) -> 'TransactionService':
        """Get the TransactionService for this book."""
        if self._transactions is None:
            raise RuntimeError("BookContext not entered - use 'with' statement")
        return self._transactions
    
    @property
    def dal(self) -> DAL:
        """
        Get the DAL for direct database access when needed.
        
        Note: Prefer using accounts/transactions services for account/transaction
        operations. Use DAL directly only for operations not covered by services.
        """
        if self._dal is None:
            raise RuntimeError("BookContext not entered - use 'with' statement")
        return self._dal
    
    def commit(self):
        """Explicitly commit changes."""
        if self._session:
            self._session.commit()
    
    def rollback(self):
        """Explicitly rollback changes."""
        if self._session:
            self._session.rollback()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager - commit or rollback and close session."""
        try:
            if exc_type:
                self._session.rollback()
            else:
                self._session.commit()
        finally:
            if self._session:
                self._session.close()
            self._session = None
            self._dal = None
            self._book = None
            self._accounts = None
            self._transactions = None
        return False  # Don't suppress exceptions

