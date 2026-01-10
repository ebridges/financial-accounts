from logging import getLogger

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ledger.db.data_access import DAL

logger = getLogger(__name__)


class BaseService:
    """
    Base class for all services providing database session management.

    Supports two modes:
    1. Independent session: Service creates and manages its own session
    2. Shared session: Service uses an externally-provided session (for coordinated operations)

    Usage (independent):
        with TransactionService().init_with_url(DB_URL) as txn_svc:
            txn_svc.enter_transaction(...)

    Usage (shared session):
        engine = create_engine(DB_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            acct_svc = AccountService(session=session)
            txn_svc = TransactionService(session=session)
            # Both services share the same session
            account = acct_svc.lookup_account(...)
            session.commit()
        finally:
            session.close()
    """

    def __init__(self, session=None):
        self._external_session = session is not None
        self.session = session
        self.data_access = DAL(session=session) if session else None
        self.db_url = None
        self.engine = None
        self.SessionLocal = None

    def init_with_url(self, db_url):
        """Initialize the service with a database URL. Creates engine for session creation."""
        if not self._external_session:
            self.db_url = db_url
            self.engine = create_engine(db_url, echo=False)
            self.SessionLocal = sessionmaker(bind=self.engine)
        return self

    def __enter__(self):
        """Enter context manager. Creates session if not using external session."""
        if not self._external_session:
            self.session = self.SessionLocal()
            self.data_access = DAL(session=self.session)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        Exit context manager.

        If using external session: does nothing (caller manages session lifecycle)
        If using own session: commits/rollbacks and closes session
        """
        # Don't manage lifecycle for external sessions
        if self._external_session:
            logger.debug("External session, skipping cleanup")
            return False

        logger.debug("Exiting BaseService context")
        try:
            if exc_type:
                # Rollback on any exception
                if self.session:
                    self.session.rollback()
                logger.error(
                    f"Exception during service operation: {exc_type.__name__}: {exc_value}"
                )
            else:
                # Commit successful operations
                if self.session:
                    logger.debug("Committing session")
                    self.session.commit()

            # Always close the session
            if self.data_access:
                logger.debug("Closing data access")
                self.data_access.close()
        except Exception as cleanup_error:
            logger.error(f"Error during session cleanup: {cleanup_error}")
        finally:
            # Dispose engine to close all database connections
            if self.engine:
                logger.debug("Disposing engine")
                self.engine.dispose()
            # Ensure session is cleared
            self.session = None
            self.data_access = None
            self.engine = None

        return False  # Allow exception propagation
