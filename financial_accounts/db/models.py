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
from financial_accounts.db.updated_mixin import UpdatedAtMixin


Base = declarative_base()


# from uuid import uuid4, UUID
# from sqlalchemy.types import TypeDecorator
# from sqlalchemy.dialects.postgresql import UUID as PG_UUID
#
# class GUID(TypeDecorator):
#     """Platform-independent GUID type.
#     When used with PostgreSQL, uses native UUID.
#     Otherwise, stores as String(36).
#     """

#     impl = String(36)
#     cache_ok = True

#     def load_dialect_impl(self, dialect):
#         if dialect.name == 'postgresql':
#             return dialect.type_descriptor(PG_UUID())
#         else:
#             return dialect.type_descriptor(String(36))

#     def process_bind_param(self, value, dialect):
#         if value is None:
#             return None
#         if not isinstance(value, UUID):
#             value = UUID(value)
#         if dialect.name == 'postgresql':
#             return value
#         else:
#             return str(value)

#     def process_result_value(self, value, dialect):
#         if value is None:
#             return None
#         return UUID(value)


# def uuid():
#     return str(uuid4())


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
    transaction_date = Column(Date, nullable=False)
    entry_date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    transaction_description = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    match_status = Column(String(1), server_default='n', nullable=False)  # n=not, m=matched
    book = relationship("Book", back_populates="transactions")
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
            if split.account_id != candidate.id:
                return (
                    split.account
                )  # Return the account from the split that does not match the given account

        raise CorrespondingSplitNotFoundError(
            f"No corresponding split found for account {candidate.id} in transaction {self.id}"
        )

    def __str__(self):
        return f'txn_date: {self.transaction_date}, match_status: {self.match_status}, description: {self.transaction_description}, amount: {self.splits[0].amount}'


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
