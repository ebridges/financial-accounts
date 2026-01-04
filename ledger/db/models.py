# models.py (excerpt)
from enum import Enum

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    DECIMAL,
    Date,
    Text,
    CheckConstraint,
    UniqueConstraint,
    Integer,
    text,
)
from sqlalchemy.orm import declarative_base, relationship
from ledger.db.updated_mixin import UpdatedAtMixin


Base = declarative_base()


class AccountTypeEnum(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"
    ROOT = "ROOT"


class Book(Base, UpdatedAtMixin):
    __tablename__ = 'book'
    id = Column(Integer, autoincrement=True, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    accounts = relationship("Account", back_populates="book", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="book", cascade="all, delete-orphan")
    import_files = relationship("ImportFile", back_populates="book", cascade="all, delete-orphan")
    account_statements = relationship(
        "AccountStatement", back_populates="book", cascade="all, delete-orphan"
    )

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()


class Account(Base, UpdatedAtMixin):
    __tablename__ = 'account'
    id = Column(Integer, autoincrement=True, primary_key=True)
    book_id = Column(
        Integer, ForeignKey('book.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    parent_account_id = Column(
        Integer, ForeignKey('account.id', ondelete="RESTRICT", onupdate="RESTRICT")
    )
    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    full_name = Column(String(1024), nullable=False)
    description = Column(Text)
    hidden = Column(Boolean, nullable=False, default=False)
    placeholder = Column(Boolean, nullable=False, default=False)
    acct_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("acct_type IN ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY','ROOT')"),
        UniqueConstraint('book_id', 'code'),
    )

    book = relationship("Book", back_populates="accounts")
    parent_account = relationship("Account", remote_side="Account.id", uselist=False)
    splits = relationship("Split", back_populates="account", cascade="all, delete-orphan")

    def __str__(self):
        return self.full_name

    def __repr__(self):
        return self.__str__()


class InvalidTransactionSplitError(Exception):
    """Exception raised when a transaction does not have exactly two splits."""

    pass


class CorrespondingSplitNotFoundError(Exception):
    """Exception raised when a corresponding split is not found for the given account."""

    pass


class Transaction(Base, UpdatedAtMixin):
    __tablename__ = 'transactions'
    id = Column(Integer, autoincrement=True, primary_key=True)
    book_id = Column(
        Integer, ForeignKey('book.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    import_file_id = Column(
        Integer, ForeignKey('import_file.id', ondelete="SET NULL", onupdate="RESTRICT"), nullable=True
    )
    transaction_date = Column(Date, nullable=False)
    entry_date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    transaction_description = Column(Text, nullable=False)
    payee_norm = Column(String(255), nullable=True)  # normalized payee for categorization cache
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    match_status = Column(
        String(1), server_default='n', nullable=False, default='n'
    )  # n=not, m=matched
    memo = Column(String(1024), nullable=True)
    book = relationship("Book", back_populates="transactions")
    import_file = relationship("ImportFile", back_populates="transactions")
    splits = relationship("Split", back_populates="transaction", cascade="all, delete-orphan")

    def corresponding_account(self, candidate: Account):
        """
        Find the split in this transaction that belongs to the other account
        compared to the given account.

        Assumes that a valid transaction has exactly two splits.

        Args:
            candidate (Account): The account whose corresponding split is to be found.

        Returns:
            Split: The split for the other account in this transaction.

        Raises:
            InvalidTransactionSplitError: If the transaction does not have exactly two splits.
            CorrespondingSplitNotFoundError: If a corresponding split is not found.
        """
        if len(self.splits) != 2:
            raise InvalidTransactionSplitError(
                f"Transaction {self.id} must have exactly two splits, but has {len(self.splits)}"
            )

        for split in self.splits:
            # Use cached account if relationship not loaded (for unsaved transactions)
            acct = getattr(split, '_account_cache', None) or split.account
            if acct is None:
                raise CorrespondingSplitNotFoundError(
                    f"Split {split.id} has no account loaded for transaction {self.id}"
                )
            if acct.full_name != candidate.full_name:
                return acct  # Return the account from the split that does not match the given account

        raise CorrespondingSplitNotFoundError(
            f"No corresponding split found for account {candidate.id} in transaction {self.id}"
        )

    def __str__(self):
        return f'txn_date: {self.transaction_date}, match_status: {self.match_status}, description: {self.transaction_description}, amount: {self.splits[0].amount}'

    def __repr__(self):
        return self.__str__()


class Split(Base, UpdatedAtMixin):
    __tablename__ = 'split'
    id = Column(Integer, autoincrement=True, primary_key=True)
    transaction_id = Column(
        Integer,
        ForeignKey('transactions.id', ondelete="CASCADE", onupdate="RESTRICT"),
        nullable=False,
    )
    account_id = Column(
        Integer, ForeignKey('account.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    amount = Column(DECIMAL(20, 4), nullable=False)  # negative for credits, positive for debits
    memo = Column(Text)
    reconcile_date = Column(DateTime)
    reconcile_state = Column(
        String(1), server_default='n', nullable=False
    )  # n=not, c=cleared, r=reconciled
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    transaction = relationship("Transaction", back_populates="splits")
    account = relationship("Account", back_populates="splits")


class ImportFile(Base, UpdatedAtMixin):
    """
    Tracks imported files for file-level idempotency.
    
    Each import file is uniquely identified by (book_id, account_id, filename).
    Re-importing the same file (by hash) is a no-op.
    """
    __tablename__ = 'import_file'
    id = Column(Integer, autoincrement=True, primary_key=True)
    book_id = Column(
        Integer, ForeignKey('book.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    account_id = Column(
        Integer, ForeignKey('account.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    filename = Column(String(255), nullable=False)  # logical name for replacement scope
    source_path = Column(String(1024))  # original file path
    archive_path = Column(String(1024))  # archived file path
    source_type = Column(String(50), nullable=False)  # 'chase_csv', 'qif'
    file_hash = Column(String(64), nullable=False)  # sha256 of file bytes
    coverage_start = Column(Date)  # min transaction date in file
    coverage_end = Column(Date)  # max transaction date in file
    row_count = Column(Integer)  # number of transactions imported
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        UniqueConstraint('book_id', 'account_id', 'filename', name='uq_import_file_scope'),
    )

    book = relationship("Book", back_populates="import_files")
    account = relationship("Account")
    transactions = relationship("Transaction", back_populates="import_file")

    def __str__(self):
        return f"ImportFile({self.filename}, {self.source_type}, {self.coverage_start}-{self.coverage_end})"

    def __repr__(self):
        return self.__str__()


class CategoryCache(Base, UpdatedAtMixin):
    """
    Cache for payee → category mappings to speed up categorization.
    
    When a payee is successfully categorized, store the mapping here
    for fast lookup on subsequent imports.
    """
    __tablename__ = 'category_cache'
    payee_norm = Column(String(255), primary_key=True)  # normalized payee string
    account_id = Column(
        Integer, ForeignKey('account.id', ondelete="CASCADE", onupdate="RESTRICT"), nullable=False
    )
    last_seen_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    hit_count = Column(Integer, default=1)

    account = relationship("Account")

    def __str__(self):
        return f"CategoryCache({self.payee_norm} -> {self.account_id})"

    def __repr__(self):
        return self.__str__()


class AccountStatement(Base, UpdatedAtMixin):
    """
    Tracks statement periods and reconciliation status for accounts.
    
    Each statement is uniquely identified by (book_id, account_id, start_date, end_date).
    Stores balances from PDF statements and computed balances from transactions.
    """
    __tablename__ = 'account_statement'
    id = Column(Integer, autoincrement=True, primary_key=True)
    book_id = Column(
        Integer, ForeignKey('book.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    account_id = Column(
        Integer, ForeignKey('account.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    start_balance = Column(DECIMAL(20, 4), nullable=False)
    end_balance = Column(DECIMAL(20, 4), nullable=False)
    statement_path = Column(String(1024))  # path to PDF
    reconcile_status = Column(
        String(1), server_default='n', nullable=False, default='n'
    )  # n=not reconciled, r=reconciled, d=discrepancy
    computed_end_balance = Column(DECIMAL(20, 4))  # calculated from transactions
    discrepancy = Column(DECIMAL(20, 4))  # null=not computed, 0=reconciled, other=mismatch
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("reconcile_status IN ('n','r','d')"),
        UniqueConstraint(
            'book_id', 'account_id', 'start_date', 'end_date',
            name='uq_account_statement_period'
        ),
    )

    book = relationship("Book", back_populates="account_statements")
    account = relationship("Account")

    def __str__(self):
        return (
            f"AccountStatement({self.account.name if self.account else self.account_id}, "
            f"{self.start_date} - {self.end_date}, status={self.reconcile_status})"
        )

    def __repr__(self):
        return self.__str__()
