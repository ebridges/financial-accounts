# data_access.py
from datetime import datetime
from logging import getLogger

from sqlalchemy.orm import joinedload
from sqlalchemy import and_

from ledger.db.models import (
    Book,
    Account,
    Transaction,
    Split,
    ImportFile,
    CategoryCache,
    AccountStatement,
)

logger = getLogger(__name__)


class DAL:
    def __init__(self, session):
        self.session = session

    def close(self):
        self.session.close()

    # --------------------------------------------------------------------------
    # Book
    # --------------------------------------------------------------------------
    def create_book(self, name: str) -> Book:
        logger.debug(f"Creating book '{name}'")
        book = Book(name=name)
        self.session.add(book)
        self.session.commit()
        logger.debug(f"Created book '{name}' with id={book.id}")
        return book

    def get_book_by_name(self, name: str) -> Book | None:
        return self.session.query(Book).filter_by(name=name).one_or_none()

    # --------------------------------------------------------------------------
    # Account
    # --------------------------------------------------------------------------
    def create_account(
        self,
        book_id: str,
        acct_type: str,  # or AccountTypeEnum if you prefer
        code: str,
        name: str,
        full_name: str,
        parent_account_id: str | None = None,
        description: str | None = None,
        hidden: bool = False,
        placeholder: bool = False,
    ) -> Account:
        """
        Creates a new Account. The acct_type param must be one of
        ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY').
        """
        logger.debug(f"Creating account '{full_name}' in book_id={book_id}")
        account = Account(
            book_id=book_id,
            acct_type=acct_type,  # If using an Enum, do acct_type.value
            code=code,
            name=name,
            full_name=full_name,
            parent_account_id=parent_account_id,
            description=description,
            hidden=hidden,
            placeholder=placeholder,
        )
        self.session.add(account)
        self.session.commit()
        logger.debug(f"Created account '{full_name}' with id={account.id}")
        return account

    def get_account(self, account_id: str) -> Account | None:
        return self.session.query(Account).filter_by(id=account_id).one_or_none()

    def get_account_by_fullname_for_book(self, book_id: str, acct_fullname: str) -> Account | None:
        account = (
            self.session.query(Account)
            .filter_by(book_id=book_id, full_name=acct_fullname)
            .one_or_none()
        )
        return account

    def get_account_by_name_for_book(
        self, book_id: str, acct_code, acct_name: str
    ) -> Account | None:
        account = (
            self.session.query(Account)
            .filter_by(book_id=book_id, code=acct_code, name=acct_name)
            .one_or_none()
        )
        return account

    def list_accounts_for_book(self, book_id: str) -> list[Account]:
        return self.session.query(Account).filter_by(book_id=book_id).all()

    # --------------------------------------------------------------------------
    # Transactions
    # --------------------------------------------------------------------------
    def insert_transactions(self, transactions: list[Transaction]):
        logger.debug(f"Batch inserting {len(transactions)} transactions")
        try:
            self.session.add_all(transactions)
            self.session.commit()
            logger.debug(f"Batch inserted {len(transactions)} transactions")
        except Exception as e:
            logger.error(f"Failed to insert transactions: {e}")
            self.session.rollback()
            raise e

    def insert_transaction(self, txn: Transaction):
        logger.debug(f"Inserting transaction: '{txn.transaction_description}'")
        try:
            self.session.add(txn)
            self.session.commit()
            logger.debug(f"Inserted transaction id={txn.id}")
        except Exception as e:
            logger.error(f"Failed to insert transaction: {e}")
            self.session.rollback()
            raise e
        return txn.id

    def update_transaction_match_status(self, transaction, match_status='m') -> None:
        try:
            self.session.query(Transaction).filter_by(id=transaction.id).update(
                {"match_status": match_status}
            )
            transaction.match_status = match_status
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise e

    def create_transaction(
        self, book_id: str, transaction_date, transaction_description: str, memo: str = None
    ) -> Transaction:
        txn = Transaction(
            book_id=book_id,
            transaction_date=transaction_date,
            transaction_description=transaction_description,
            memo=memo,
        )
        self.session.add(txn)
        self.session.commit()
        return txn

    def get_transaction(self, txn_id: str) -> Transaction | None:
        return (
            self.session.query(Transaction)
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .filter_by(id=txn_id)
            .one_or_none()
        )

    def list_transactions_for_book(self, book_id: str) -> list[Transaction]:
        return (
            self.session.query(Transaction)
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .filter_by(book_id=book_id)
            .all()
        )

    def query_for_unmatched_transactions_in_range(
        self,
        book_id: int,
        start_date: datetime.date,
        end_date: datetime.date,
        accounts_to_match_for: list[str],
        reconciliation_status: str | None = None,
    ):
        logger.debug(
            f"Querying unmatched transactions: {start_date} to {end_date}, accounts={accounts_to_match_for}"
        )
        query = (
            self.session.query(Transaction)
            .join(Split)
            .join(Account)
            .filter(
                and_(
                    Transaction.book_id == book_id,
                    Transaction.transaction_date >= start_date,
                    Transaction.transaction_date <= end_date,
                    Transaction.match_status == "n",
                    Account.full_name.in_(accounts_to_match_for),
                )
            )
            .options(joinedload(Transaction.splits).joinedload(Split.account))
        )

        if reconciliation_status:
            query = query.filter(Split.reconcile_state == reconciliation_status)

        results = query.all()
        logger.debug(f"Found {len(results)} unmatched transactions")
        return results

    def get_transactions_by_transfer_references(
        self, book_id: int, transfer_references: list[str]
    ) -> list[Transaction]:
        """
        Get all transactions matching any of the given transfer_references.

        Used to efficiently fetch candidates for batch matching during import.
        """
        if not transfer_references:
            return []
        logger.debug(f"Looking up transactions by {len(transfer_references)} transfer_references")
        return (
            self.session.query(Transaction)
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .filter(
                and_(
                    Transaction.book_id == book_id,
                    Transaction.transfer_reference.in_(transfer_references),
                )
            )
            .all()
        )

    def delete_transaction(self, txn_id: str) -> bool:
        logger.debug(f"Deleting transaction id={txn_id}")
        splits = self.session.query(Split).filter_by(transaction_id=txn_id)
        txn = self.session.query(Transaction).filter_by(id=txn_id).one_or_none()
        if not txn:
            logger.warning(f"Transaction id={txn_id} not found for deletion")
            return False
        split_count = splits.count()
        for split in splits:
            self.session.delete(split)
        self.session.delete(txn)
        self.session.commit()
        logger.debug(f"Deleted transaction id={txn_id} with {split_count} splits")
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
        spl = Split(
            transaction_id=transaction_id,
            account_id=account_id,
            amount=amount,
            memo=memo,
            reconcile_state=reconcile_state,
        )
        self.session.add(spl)
        self.session.commit()
        return spl

    # --------------------------------------------------------------------------
    # ImportFile
    # --------------------------------------------------------------------------
    def create_import_file(
        self,
        book_id: int,
        account_id: int,
        filename: str,
        source_type: str,
        file_hash: str,
        source_path: str | None = None,
        archive_path: str | None = None,
        coverage_start=None,
        coverage_end=None,
        row_count: int | None = None,
    ) -> ImportFile:
        """Create a new import file record."""
        logger.debug(f"Creating import file record: '{filename}'")
        import_file = ImportFile(
            book_id=book_id,
            account_id=account_id,
            filename=filename,
            source_path=source_path,
            archive_path=archive_path,
            source_type=source_type,
            file_hash=file_hash,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            row_count=row_count,
        )
        self.session.add(import_file)
        self.session.commit()
        logger.debug(f"Created import file id={import_file.id} for '{filename}'")
        return import_file

    def get_import_file(self, import_file_id: int) -> ImportFile | None:
        """Get an import file by ID."""
        return self.session.query(ImportFile).filter_by(id=import_file_id).one_or_none()

    def get_import_file_by_scope(
        self, book_id: int, account_id: int, filename: str
    ) -> ImportFile | None:
        """Get an import file by its unique scope (book, account, filename)."""
        return (
            self.session.query(ImportFile)
            .filter_by(book_id=book_id, account_id=account_id, filename=filename)
            .one_or_none()
        )

    def list_import_files_for_book(self, book_id: int) -> list[ImportFile]:
        """List all import files for a book."""
        return (
            self.session.query(ImportFile)
            .filter_by(book_id=book_id)
            .order_by(ImportFile.created_at.desc())
            .all()
        )

    # --------------------------------------------------------------------------
    # CategoryCache
    # --------------------------------------------------------------------------
    def get_category_from_cache(self, payee_norm: str) -> CategoryCache | None:
        """Look up a category by normalized payee."""
        return self.session.query(CategoryCache).filter_by(payee_norm=payee_norm).one_or_none()

    def set_category_cache(self, payee_norm: str, account_id: int) -> CategoryCache:
        """Set or update a category cache entry."""
        existing = self.get_category_from_cache(payee_norm)
        if existing:
            existing.account_id = account_id
            existing.hit_count += 1
            existing.last_seen_at = datetime.now()
            self.session.commit()
            return existing
        else:
            cache_entry = CategoryCache(
                payee_norm=payee_norm,
                account_id=account_id,
                hit_count=1,
            )
            self.session.add(cache_entry)
            self.session.commit()
            return cache_entry

    def increment_cache_hit(self, payee_norm: str) -> None:
        """Increment the hit count for a cache entry."""
        entry = self.get_category_from_cache(payee_norm)
        if entry:
            entry.hit_count += 1
            entry.last_seen_at = datetime.now()
            self.session.commit()

    # --------------------------------------------------------------------------
    # AccountStatement
    # --------------------------------------------------------------------------
    def create_account_statement(
        self,
        book_id: int,
        account_id: int,
        start_date,
        end_date,
        start_balance,
        end_balance,
        statement_path: str | None = None,
    ) -> AccountStatement:
        """Create a new account statement record."""
        logger.debug(
            f"Creating account statement for account_id={account_id}, "
            f"period={start_date} to {end_date}"
        )
        statement = AccountStatement(
            book_id=book_id,
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            start_balance=start_balance,
            end_balance=end_balance,
            statement_path=statement_path,
        )
        self.session.add(statement)
        self.session.commit()
        logger.debug(f"Created account statement id={statement.id}")
        return statement

    def get_account_statement(self, statement_id: int) -> AccountStatement | None:
        """Get an account statement by ID."""
        return (
            self.session.query(AccountStatement)
            .options(joinedload(AccountStatement.account))
            .filter_by(id=statement_id)
            .one_or_none()
        )

    def get_account_statement_by_period(
        self, book_id: int, account_id: int, start_date, end_date
    ) -> AccountStatement | None:
        """Get an account statement by its unique period (book, account, dates)."""
        return (
            self.session.query(AccountStatement)
            .options(joinedload(AccountStatement.account))
            .filter_by(
                book_id=book_id, account_id=account_id, start_date=start_date, end_date=end_date
            )
            .one_or_none()
        )

    def list_account_statements_for_book(self, book_id: int) -> list[AccountStatement]:
        """List all account statements for a book."""
        return (
            self.session.query(AccountStatement)
            .options(joinedload(AccountStatement.account))
            .filter_by(book_id=book_id)
            .order_by(AccountStatement.account_id, AccountStatement.start_date.desc())
            .all()
        )

    def list_account_statements_for_account(
        self, book_id: int, account_id: int
    ) -> list[AccountStatement]:
        """List all account statements for a specific account."""
        return (
            self.session.query(AccountStatement)
            .options(joinedload(AccountStatement.account))
            .filter_by(book_id=book_id, account_id=account_id)
            .order_by(AccountStatement.start_date.desc())
            .all()
        )

    def update_account_statement_reconciliation(
        self,
        statement: AccountStatement,
        computed_end_balance,
        discrepancy,
        reconcile_status: str,
    ) -> None:
        """Update the reconciliation fields on an account statement."""
        logger.debug(
            f"Updating reconciliation for statement id={statement.id}: "
            f"computed={computed_end_balance}, discrepancy={discrepancy}, status={reconcile_status}"
        )
        try:
            statement.computed_end_balance = computed_end_balance
            statement.discrepancy = discrepancy
            statement.reconcile_status = reconcile_status
            self.session.commit()
        except Exception as e:
            logger.error(f"Failed to update statement reconciliation: {e}")
            self.session.rollback()
            raise e

    def query_transactions_for_account_in_range(
        self,
        book_id: int,
        account_id: int,
        start_date,
        end_date,
    ) -> list[Transaction]:
        """Query all transactions for an account within a date range."""
        logger.debug(
            f"Querying transactions for account_id={account_id}, "
            f"period={start_date} to {end_date}"
        )
        results = (
            self.session.query(Transaction)
            .join(Split)
            .filter(
                and_(
                    Transaction.book_id == book_id,
                    Transaction.transaction_date >= start_date,
                    Transaction.transaction_date <= end_date,
                    Split.account_id == account_id,
                )
            )
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .all()
        )
        logger.debug(f"Found {len(results)} transactions for account in period")
        return results
