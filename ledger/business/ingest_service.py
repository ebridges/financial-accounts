# ingest_service.py
"""
High-level ingestion service for importing financial data files.

Orchestrates the lower-level services (TransactionService, AccountService)
and utilities (ChaseCsvParser, Qif, ArchiveService) to provide file-level
idempotent import with archiving.
"""
import hashlib
import os
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple
from enum import Enum

from ledger.business.base_service import BaseService
from ledger.business.transaction_service import TransactionService
from ledger.business.account_service import AccountService
from ledger.business.archive_service import ArchiveService
from ledger.util.chase_csv import ChaseCsvParser
from ledger.util.qif import Qif
from ledger.db.models import Transaction, Split, ImportFile


class IngestResult(Enum):
    """Result of an ingest operation."""
    IMPORTED = "imported"           # New file imported successfully
    SKIPPED_DUPLICATE = "skipped"   # Same file (by hash) already imported
    HASH_MISMATCH = "mismatch"      # Same filename but different hash - requires action


@dataclass
class IngestReport:
    """Report from an ingest operation."""
    result: IngestResult
    import_file_id: Optional[int] = None
    transactions_imported: int = 0
    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None
    archive_path: Optional[str] = None
    message: str = ""


class IngestService(BaseService):
    """
    High-level service for ingesting financial data files with idempotency.
    
    Composes lower-level services to:
    1. Parse CSV/QIF files
    2. Check for duplicate imports (file-level idempotency)
    3. Archive source files
    4. Import transactions
    5. Track import metadata
    
    Usage:
        with IngestService().init_with_url(DB_URL) as ingest_svc:
            report = ingest_svc.ingest_csv(
                file_path='downloads/chase-checking.csv',
                book_name='personal',
                account_full_name='Assets:Checking Accounts:checking-chase-personal-1381'
            )
    """
    
    def __init__(self, session=None, archive_service: Optional[ArchiveService] = None):
        super().__init__(session=session)
        self.archive_service = archive_service or ArchiveService()
    
    def ingest_csv(
        self,
        file_path: str,
        book_name: str,
        account_full_name: str,
        filename: Optional[str] = None,
        archive: bool = True,
    ) -> IngestReport:
        """
        Ingest a Chase CSV file.
        
        Args:
            file_path: Path to the CSV file
            book_name: Name of the book to import into
            account_full_name: Full account name for the import
            filename: Logical filename for idempotency (defaults to basename)
            archive: Whether to archive the file
        
        Returns:
            IngestReport with details of the operation
        """
        # Resolve filename for idempotency scope
        if filename is None:
            filename = os.path.basename(file_path)
        
        # Compute file hash
        file_hash = self._compute_file_hash(file_path)
        
        # Get book and account
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise ValueError(f"Book '{book_name}' not found")
        
        account = self.data_access.get_account_by_fullname_for_book(book.id, account_full_name)
        if not account:
            raise ValueError(f"Account '{account_full_name}' not found in book '{book_name}'")
        
        # Check for existing import
        existing = self.data_access.get_import_file_by_scope(book.id, account.id, filename)
        if existing:
            if existing.file_hash == file_hash:
                return IngestReport(
                    result=IngestResult.SKIPPED_DUPLICATE,
                    import_file_id=existing.id,
                    message=f"File '{filename}' already imported (hash match)"
                )
            else:
                return IngestReport(
                    result=IngestResult.HASH_MISMATCH,
                    import_file_id=existing.id,
                    message=(
                        f"File '{filename}' exists with different hash. "
                        f"Use a different filename or delete the existing import."
                    )
                )
        
        # Parse CSV
        parser = ChaseCsvParser()
        parser.init_from_csv_file(file_path, account_full_name)
        
        # Get coverage dates
        coverage_start, coverage_end = parser.get_coverage_dates()
        if not coverage_start or not coverage_end:
            raise ValueError("Could not determine date range from CSV file")
        
        # Archive files
        archive_path = None
        if archive:
            account_slug = self.archive_service.get_account_slug_from_full_name(account_full_name)
            csv_archive, qif_archive = self.archive_service.archive_csv_with_qif(
                file_path,
                parser.to_qif_string(),
                account_slug,
                coverage_start,
                coverage_end
            )
            archive_path = csv_archive
        
        # Get transaction data
        transaction_data = parser.as_transaction_data(book.id)
        
        # Create import file record first
        import_file = self.data_access.create_import_file(
            book_id=book.id,
            account_id=account.id,
            filename=filename,
            source_type='chase_csv',
            file_hash=file_hash,
            source_path=file_path,
            archive_path=archive_path,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            row_count=len(transaction_data),
        )
        
        # Import transactions
        transactions_imported = self._import_transaction_data(
            book.id, import_file.id, transaction_data
        )
        
        return IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=import_file.id,
            transactions_imported=transactions_imported,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            archive_path=archive_path,
            message=f"Successfully imported {transactions_imported} transactions"
        )
    
    def ingest_qif(
        self,
        file_path: str,
        book_name: str,
        filename: Optional[str] = None,
        archive: bool = True,
    ) -> IngestReport:
        """
        Ingest a QIF file.
        
        The account is determined from the QIF file's account header.
        
        Args:
            file_path: Path to the QIF file
            book_name: Name of the book to import into
            filename: Logical filename for idempotency (defaults to basename)
            archive: Whether to archive the file
        
        Returns:
            IngestReport with details of the operation
        """
        # Resolve filename for idempotency scope
        if filename is None:
            filename = os.path.basename(file_path)
        
        # Compute file hash
        file_hash = self._compute_file_hash(file_path)
        
        # Get book
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise ValueError(f"Book '{book_name}' not found")
        
        # Parse QIF to get account name
        qif = Qif()
        qif.init_from_qif_file(file_path)
        account_full_name = qif.account_info.get('N')
        if not account_full_name:
            raise ValueError("QIF file does not contain account information")
        
        # Get account
        account = self.data_access.get_account_by_fullname_for_book(book.id, account_full_name)
        if not account:
            raise ValueError(f"Account '{account_full_name}' not found in book '{book_name}'")
        
        # Check for existing import
        existing = self.data_access.get_import_file_by_scope(book.id, account.id, filename)
        if existing:
            if existing.file_hash == file_hash:
                return IngestReport(
                    result=IngestResult.SKIPPED_DUPLICATE,
                    import_file_id=existing.id,
                    message=f"File '{filename}' already imported (hash match)"
                )
            else:
                return IngestReport(
                    result=IngestResult.HASH_MISMATCH,
                    import_file_id=existing.id,
                    message=(
                        f"File '{filename}' exists with different hash. "
                        f"Use a different filename or delete the existing import."
                    )
                )
        
        # Get transaction data and determine coverage
        transaction_data = qif.as_transaction_data(book.id)
        
        if transaction_data:
            dates = [d['transaction_date'] for d in transaction_data]
            coverage_start = min(dates)
            coverage_end = max(dates)
        else:
            coverage_start = coverage_end = None
        
        # Archive file
        archive_path = None
        if archive and coverage_start and coverage_end:
            account_slug = self.archive_service.get_account_slug_from_full_name(account_full_name)
            archive_path = self.archive_service.archive_file(
                file_path, account_slug, coverage_start, coverage_end, 'qif'
            )
        
        # Create import file record
        import_file = self.data_access.create_import_file(
            book_id=book.id,
            account_id=account.id,
            filename=filename,
            source_type='qif',
            file_hash=file_hash,
            source_path=file_path,
            archive_path=archive_path,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            row_count=len(transaction_data),
        )
        
        # Import transactions (QIF already has categories in L line)
        transactions_imported = self._import_transaction_data(
            book.id, import_file.id, transaction_data
        )
        
        return IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=import_file.id,
            transactions_imported=transactions_imported,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            archive_path=archive_path,
            message=f"Successfully imported {transactions_imported} transactions"
        )
    
    def _import_transaction_data(
        self,
        book_id: int,
        import_file_id: int,
        transaction_data: List[dict],
    ) -> int:
        """
        Import transaction data dicts into the database.
        
        Args:
            book_id: Book ID
            import_file_id: Import file ID for provenance tracking
            transaction_data: List of transaction data dicts from parser
        
        Returns:
            Number of transactions imported
        """
        imported_count = 0
        
        for data in transaction_data:
            transaction = Transaction()
            transaction.book_id = book_id
            transaction.import_file_id = import_file_id
            transaction.transaction_date = data['transaction_date']
            transaction.transaction_description = data['transaction_description']
            transaction.payee_norm = data.get('payee_norm')
            
            transaction.splits = []
            for split_data in data['splits']:
                split = Split()
                # Resolve account
                account = self.data_access.get_account_by_fullname_for_book(
                    book_id, split_data['account_name']
                )
                if not account:
                    raise ValueError(
                        f"Account '{split_data['account_name']}' not found for transaction "
                        f"'{data['transaction_description']}'"
                    )
                split.account = account
                split.account_id = account.id
                split.amount = split_data['amount']
                transaction.splits.append(split)
            
            self.data_access.insert_transaction(transaction)
            imported_count += 1
        
        return imported_count
    
    def list_imports(self, book_name: str) -> List[ImportFile]:
        """
        List all import files for a book.
        
        Args:
            book_name: Name of the book
        
        Returns:
            List of ImportFile records
        """
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise ValueError(f"Book '{book_name}' not found")
        
        return self.data_access.list_import_files_for_book(book.id)
    
    def get_import(self, import_file_id: int) -> Optional[ImportFile]:
        """Get an import file by ID."""
        return self.data_access.get_import_file(import_file_id)
    
    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

