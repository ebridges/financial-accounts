# data_access.py
from datetime import datetime

from sqlalchemy.orm import joinedload
from sqlalchemy import and_, text

from ledger.db.models import Book, Account, Transaction, Split, ImportFile, CategoryCache


class DAL:
    def __init__(self, session):
        self.session = session

    def close(self):
        self.session.close()

    # --------------------------------------------------------------------------
    # Book
    # --------------------------------------------------------------------------
    def create_book(self, name: str) -> Book:
        book = Book(name=name)
        self.session.add(book)
        self.session.commit()
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
        return account

    def get_account(self, account_id: str) -> Account | None:
        return (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(id=account_id)
            .one_or_none()
        )

    def get_account_by_fullname_for_book(
        self, book_id: str, acct_fullname: str
    ) -> Account | None:
        account = (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(book_id=book_id, full_name=acct_fullname)
            .one_or_none()
        )
        return account

    def get_account_by_name_for_book(
        self, book_id: str, acct_code, acct_name: str
    ) -> Account | None:
        account = (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(book_id=book_id, code=acct_code, name=acct_name)
            .one_or_none()
        )
        return account

    def list_accounts_for_book(self, book_id: str) -> list[Account]:
        return (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(book_id=book_id)
            .all()
        )

    # --------------------------------------------------------------------------
    # Transactions
    # --------------------------------------------------------------------------
    def insert_transactions(self, transactions: list[Transaction]):
        try:
            self.session.add_all(transactions)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            raise e

    def insert_transaction(self, txn: Transaction):
        try:
            self.session.add(txn)
            self.session.commit()
        except Exception as e:
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

        return query.all()

    def delete_transaction(self, txn_id: str) -> bool:
        splits = self.session.query(Split).filter_by(transaction_id=txn_id)
        txn = self.session.query(Transaction).filter_by(id=txn_id).one_or_none()
        if not txn:
            return False
        for split in splits:
            self.session.delete(split)
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
    # Management
    # --------------------------------------------------------------------------
    def list_account_hierarchy(self):
        # Step 1: Run a recursive CTE query to get each account, its parent, and depth
        recursive_cte_query = text(
            """
            WITH RECURSIVE account_hierarchy AS (
                -- Anchor: all root accounts (no parent)
                SELECT
                    id,
                    parent_account_id,
                    code,
                    name,
                    0 AS depth
                FROM account
                WHERE parent_account_id IS NULL

                UNION ALL

                -- Recursive: join children to their parent in this CTE
                SELECT
                    c.id,
                    c.parent_account_id,
                    c.code,
                    c.name,
                    ah.depth + 1 AS depth
                FROM account c
                JOIN account_hierarchy ah
                ON c.parent_account_id = ah.id
            )
            SELECT
                id,
                parent_account_id,
                code,
                name,
                depth
            FROM account_hierarchy
            -- You can choose your own ORDER BY column(s)
            ORDER BY code
        """
        )

        result = self.session.execute(recursive_cte_query)
        return result.fetchall()
