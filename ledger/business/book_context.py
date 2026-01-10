# book_context.py
"""
BookContext provides coordinated access to book-scoped services with a shared session.

Usage:
    with BookContext("personal", DB_URL) as ctx:
        accounts = ctx.accounts.list_accounts()
        ctx.transactions.enter_transaction(...)
"""
from logging import getLogger

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ledger.db.data_access import DAL
from ledger.db.models import Book

from ledger.business.account_service import AccountService
from ledger.business.transaction_service import TransactionService
from ledger.business.statement_service import StatementService
from ledger.business.reconciliation_service import ReconciliationService

logger = getLogger(__name__)


class BookContext:
    """Coordinator for book-scoped services with shared session and auto commit/rollback."""

    def __init__(self, book_name: str, db_url: str):
        self.book_name = book_name
        self.db_url = db_url
        self._engine = create_engine(db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)
        self._session = None
        self._dal = None
        self._book = None
        self._accounts = None
        self._transactions = None
        self._statements = None
        self._reconciliation = None

    def __enter__(self):
        logger.debug(f"Entering BookContext for book '{self.book_name}'")
        self._session = self._session_factory()
        self._dal = DAL(session=self._session)

        self._book = self._dal.get_book_by_name(self.book_name)
        if not self._book:
            logger.error(f"Book '{self.book_name}' not found")
            self._session.close()
            raise ValueError(f"Book '{self.book_name}' not found")

        logger.debug(f"Resolved book '{self.book_name}' to id={self._book.id}")
        self._accounts = AccountService(self._dal, self._book)
        self._transactions = TransactionService(self._dal, self._book)
        self._statements = StatementService(self)
        self._reconciliation = ReconciliationService(self)
        logger.debug("BookContext services initialized")

        return self

    def _require_entered(self, attr):
        value = getattr(self, f'_{attr}')
        if value is None:
            raise RuntimeError("BookContext not entered - use 'with' statement")
        return value

    @property
    def book(self) -> Book:
        return self._require_entered('book')

    @property
    def accounts(self) -> 'AccountService':
        return self._require_entered('accounts')

    @property
    def transactions(self) -> 'TransactionService':
        return self._require_entered('transactions')

    @property
    def dal(self) -> DAL:
        """Get DAL for operations not covered by services (e.g., import files, cache)."""
        return self._require_entered('dal')

    @property
    def statements(self) -> 'StatementService':
        """Get the statement service for importing and managing account statements."""
        return self._require_entered('statements')

    @property
    def reconciliation(self) -> 'ReconciliationService':
        """Get the reconciliation service for verifying statement balances."""
        return self._require_entered('reconciliation')

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.debug(f"Exiting BookContext for book '{self.book_name}'")
        try:
            if exc_type:
                logger.debug(f"Exception occurred ({exc_type.__name__}), rolling back")
                self._session.rollback()
            else:
                logger.debug("Committing session")
                self._session.commit()
        finally:
            if self._session:
                logger.debug("Closing session")
                self._session.close()
            if self._engine:
                logger.debug("Disposing engine")
                self._engine.dispose()
            self._session = None
            self._dal = None
            self._book = None
            self._accounts = None
            self._transactions = None
            self._statements = None
            self._reconciliation = None
            self._engine = None
        return False
