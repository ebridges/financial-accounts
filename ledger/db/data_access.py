# data_access.py
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import joinedload
from sqlalchemy import and_, text

from ledger.db.models import Book, Account, Transaction, Split, ImportFile, CategoryCache


# def check_for_circular_path(
#     session: Session, account_id: str, parent_account_id: Optional[str]
# ) -> bool:
#     """
#     Returns True if a cycle is found, False otherwise.
#     We'll do a simple upward traversal from parent_account_id until we either
#     reach None or the 'account_id' itself.
#     """
#     if not parent_account_id:
#         return False  # no parent => no cycle

#     current_id = parent_account_id
#     while current_id is not None:
#         if current_id == account_id:
#             return True
#         parent = session.query(Account.parent_account_id).filter(Account.id == current_id).first()
#         if parent is None or parent[0] is None:
#             return False
#         current_id = parent[0]
#     return False


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

    def get_book(self, book_id: str) -> Optional[Book]:
        return self.session.query(Book).filter_by(id=book_id).one_or_none()

    def get_book_by_name(self, name: str) -> Optional[Book]:
        return self.session.query(Book).filter_by(name=name).one_or_none()

    def list_books(self) -> List[Book]:
        return self.session.query(Book).all()

    def update_book_name(self, book_id: str, new_name: str) -> Optional[Book]:
        book = self.session.query(Book).filter_by(id=book_id).one_or_none()
        if not book:
            return None
        book.name = new_name
        self.session.commit()
        return book

    def delete_book(self, book_id: str) -> bool:
        book = self.session.query(Book).filter_by(id=book_id).one_or_none()
        if not book:
            return False
        self.session.delete(book)
        self.session.commit()
        return True

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
        parent_account_id: Optional[str] = None,
        description: Optional[str] = None,
        hidden: bool = False,
        placeholder: bool = False,
    ) -> Account:
        """
        Creates a new Account. The acct_type param must be one of
        ('ASSET','LIABILITY','INCOME','EXPENSE','EQUITY').
        """
        # Check for circular references
        # if parent_account_id:
        #     if check_for_circular_path(self.session, str(new_id), parent_account_id):
        #         raise ValueError("Circular parent reference detected.")

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

    def get_account(self, account_id: str) -> Optional[Account]:
        return (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(id=account_id)
            .one_or_none()
        )

    def get_account_by_fullname_for_book(
        self, book_id: str, acct_fullname: str
    ) -> Optional[Account]:
        account = (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(book_id=book_id, full_name=acct_fullname)
            .one_or_none()
        )
        return account

    def get_account_by_name_for_book(
        self, book_id: str, acct_code, acct_name: str
    ) -> Optional[Account]:
        account = (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(book_id=book_id, code=acct_code, name=acct_name)
            .one_or_none()
        )
        return account

    def update_account(self, account_id: str, **kwargs) -> Optional[Account]:
        """
        Updates an account. If parent_account_id changes, verify no circular references.
        """
        account = self.session.query(Account).filter_by(id=account_id).one_or_none()
        if not account:
            return None

        # new_parent_id = kwargs.get("parent_account_id", account.parent_account_id)
        # if new_parent_id != account.parent_account_id:
        #     # check for cycle
        #     if check_for_circular_path(self.session, account_id, new_parent_id):
        #         raise ValueError("Circular parent reference detected.")

        # updatable fields
        for field in [
            "book_id",
            "acct_type",
            "code",
            "name",
            "description",
            "hidden",
            "placeholder",
            "parent_account_id",
        ]:
            if field in kwargs:
                setattr(account, field, kwargs[field])

        self.session.commit()
        return account

    def delete_account(self, account_id: str) -> bool:
        account = self.session.query(Account).filter_by(id=account_id).one_or_none()
        if not account:
            return False
        self.session.delete(account)
        self.session.commit()
        return True

    def list_accounts_for_book(self, book_id: str) -> List[Account]:
        return (
            self.session.query(Account)
            .options(joinedload(Account.splits))
            .filter_by(book_id=book_id)
            .all()
        )

    # --------------------------------------------------------------------------
    # Transactions
    # --------------------------------------------------------------------------
    def insert_transactions(self, transactions: List[Transaction]):
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

    def get_transaction(self, txn_id: str) -> Optional[Transaction]:
        return (
            self.session.query(Transaction)
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .filter_by(id=txn_id)
            .one_or_none()
        )

    def list_transactions_for_book(self, book_id: str) -> List[Transaction]:
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
        accounts_to_match_for: List[str],
        reconciliation_status: Optional[str] = None,
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

    def update_transaction(self, txn_id: str, **kwargs) -> Optional[Transaction]:
        txn = self.session.query(Transaction).filter_by(id=txn_id).one_or_none()
        if not txn:
            return None

        for field in ["transaction_date", "transaction_description", "book_id"]:
            if field in kwargs:
                setattr(txn, field, kwargs[field])

        self.session.commit()
        return txn

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

    def update_split(self, split_id: str, **kwargs) -> Optional[Split]:
        spl = self.session.query(Split).filter_by(id=split_id).one_or_none()
        if not spl:
            return None

        for field in [
            "transaction_id",
            "account_id",
            "amount",
            "memo",
            "reconcile_date",
            "reconcile_state",
        ]:
            if field in kwargs:
                setattr(spl, field, kwargs[field])

        self.session.commit()
        return spl

    def delete_split(self, split_id: str) -> bool:
        spl = self.session.query(Split).filter_by(id=split_id).one_or_none()
        if not spl:
            return False
        self.session.delete(spl)
        self.session.commit()
        return True

    def list_splits_for_transaction(self, txn_id: str) -> List[Split]:
        return self.session.query(Split).filter_by(transaction_id=txn_id).all()

    def list_splits_for_account(self, account_id: str) -> List[Split]:
        return self.session.query(Split).filter_by(account_id=account_id).all()

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
        source_path: Optional[str] = None,
        archive_path: Optional[str] = None,
        coverage_start=None,
        coverage_end=None,
        row_count: Optional[int] = None,
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

    def get_import_file(self, import_file_id: int) -> Optional[ImportFile]:
        """Get an import file by ID."""
        return self.session.query(ImportFile).filter_by(id=import_file_id).one_or_none()

    def get_import_file_by_scope(
        self, book_id: int, account_id: int, filename: str
    ) -> Optional[ImportFile]:
        """Get an import file by its unique scope (book, account, filename)."""
        return (
            self.session.query(ImportFile)
            .filter_by(book_id=book_id, account_id=account_id, filename=filename)
            .one_or_none()
        )

    def list_import_files_for_book(self, book_id: int) -> List[ImportFile]:
        """List all import files for a book."""
        return (
            self.session.query(ImportFile)
            .filter_by(book_id=book_id)
            .order_by(ImportFile.created_at.desc())
            .all()
        )

    def list_import_files_for_account(self, account_id: int) -> List[ImportFile]:
        """List all import files for an account."""
        return (
            self.session.query(ImportFile)
            .filter_by(account_id=account_id)
            .order_by(ImportFile.created_at.desc())
            .all()
        )

    def update_import_file(self, import_file_id: int, **kwargs) -> Optional[ImportFile]:
        """Update an import file record."""
        import_file = self.session.query(ImportFile).filter_by(id=import_file_id).one_or_none()
        if not import_file:
            return None

        for field in [
            "filename", "source_path", "archive_path", "source_type",
            "file_hash", "coverage_start", "coverage_end", "row_count"
        ]:
            if field in kwargs:
                setattr(import_file, field, kwargs[field])

        self.session.commit()
        return import_file

    # --------------------------------------------------------------------------
    # CategoryCache
    # --------------------------------------------------------------------------
    def get_category_from_cache(self, payee_norm: str) -> Optional[CategoryCache]:
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

    def list_category_cache(self) -> List[CategoryCache]:
        """List all category cache entries ordered by hit count."""
        return (
            self.session.query(CategoryCache)
            .order_by(CategoryCache.hit_count.desc())
            .all()
        )

    # --------------------------------------------------------------------------
    # Transaction queries for categorization
    # --------------------------------------------------------------------------
    def list_uncategorized_transactions(
        self,
        book_id: int,
        account_id: Optional[int] = None,
        import_file_id: Optional[int] = None,
    ) -> List[Transaction]:
        """
        List transactions that need categorization.
        
        A transaction needs categorization if its counter-split points to an
        'Uncategorized' account or a placeholder account.
        """
        query = (
            self.session.query(Transaction)
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .filter(Transaction.book_id == book_id)
        )
        
        if import_file_id:
            query = query.filter(Transaction.import_file_id == import_file_id)
        
        transactions = query.all()
        
        # Filter for uncategorized (where counter-split is to placeholder or 'Uncategorized')
        uncategorized = []
        for txn in transactions:
            if account_id:
                # Check if this transaction involves the specified account
                account_ids = [s.account_id for s in txn.splits]
                if account_id not in account_ids:
                    continue
            
            # Check if any split is to a placeholder account or 'Uncategorized'
            for split in txn.splits:
                if split.account.placeholder or 'uncategorized' in split.account.full_name.lower():
                    uncategorized.append(txn)
                    break
        
        return uncategorized

    def list_transactions_for_import_file(self, import_file_id: int) -> List[Transaction]:
        """List all transactions from a specific import file."""
        return (
            self.session.query(Transaction)
            .options(joinedload(Transaction.splits).joinedload(Split.account))
            .filter(Transaction.import_file_id == import_file_id)
            .all()
        )

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
