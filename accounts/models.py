# models.py (excerpt)
import uuid
from enum import Enum

from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey,
    DECIMAL, Date, Text, CheckConstraint, text
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.sqlite import BLOB as UUID  # or TEXT for storing UUIDs in SQLite

Base = declarative_base()


class AccountTypeEnum(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"
    EQUITY = "EQUITY"


class Book(Base):
    __tablename__ = 'book'
    id = Column(UUID, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    accounts = relationship("Account", back_populates="book", cascade="all, delete-orphan")
    transactions = relationship("Transactions", back_populates="book", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = 'account'
    id = Column(UUID, primary_key=True)
    book_id = Column(UUID, ForeignKey('book.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False)
    parent_account_id = Column(UUID, ForeignKey('account.id', ondelete="RESTRICT", onupdate="RESTRICT"))
    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    hidden = Column(Boolean, nullable=False, default=False)
    placeholder = Column(Boolean, nullable=False, default=False)
    acct_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("acct_type IN ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY')"),
        UniqueConstraint('book_id','code')
    )

    book = relationship("Book", back_populates="accounts")
    parent_account = relationship("Account", remote_side="Account.id", uselist=False)
    splits = relationship("Split", back_populates="account", cascade="all, delete-orphan")


class Transactions(Base):
    __tablename__ = 'transactions'
    id = Column(UUID, primary_key=True)
    book_id = Column(UUID, ForeignKey('book.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False)
    transaction_date = Column(Date, nullable=False)
    entry_date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    transaction_description = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    book = relationship("Book", back_populates="transactions")
    splits = relationship("Split", back_populates="transaction", cascade="all, delete-orphan")


class Split(Base):
    __tablename__ = 'split'
    id = Column(UUID, primary_key=True)
    transaction_id = Column(UUID, ForeignKey('transactions.id', ondelete="CASCADE", onupdate="RESTRICT"), nullable=False)
    account_id = Column(UUID, ForeignKey('account.id', ondelete="RESTRICT", onupdate="RESTRICT"), nullable=False)
    amount = Column(DECIMAL(20,4), nullable=False)  # negative for credits, positive for debits
    memo = Column(Text)
    reconcile_date = Column(DateTime)
    reconcile_state = Column(String(1), server_default='n', nullable=False)  # n=not, c=cleared, r=reconciled
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    transaction = relationship("Transactions", back_populates="splits")
    account = relationship("Account", back_populates="splits")
