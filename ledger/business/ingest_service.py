# ingest_service.py
"""
High-level ingestion service for importing financial data files.

Orchestrates the lower-level services (TransactionService, CategorizeService,
MatchingService) and utilities (ChaseCsvParser, Qif, ArchiveService) to 
provide file-level idempotent import with:
- Automatic categorization for transactions without a category (L field absent)
- Transfer/duplicate matching against existing ledger entries (if matching rules configured)
- Archiving of source files

Note: Categorization only applies when a transaction has NO category.
Existing categories (including 'Expenses:Uncategorized') are preserved as-is.
"""
import hashlib
import os
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple
from enum import Enum
from logging import getLogger

from ledger.business.base_service import BaseService
from ledger.business.transaction_service import TransactionService
from ledger.business.matching_service import MatchingService
from ledger.business.archive_service import ArchiveService
from ledger.business.categorize_service import CategorizeService
from ledger.config import CATEGORY_RULES_PATH
from ledger.util.chase_csv import ChaseCsvParser
from ledger.util.qif import Qif
from ledger.db.models import Transaction, Split, ImportFile, Account

logger = getLogger(__name__)


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
    transactions_matched: int = 0
    transactions_categorized: int = 0
    coverage_start: Optional[date] = None
    coverage_end: Optional[date] = None
    archive_path: Optional[str] = None
    message: str = ""
    errors: List[str] = field(default_factory=list)


class IngestService(BaseService):
    """
    High-level service for ingesting financial data files with idempotency.
    
    Composes lower-level services to:
    1. Parse CSV/QIF files
    2. Check for duplicate imports (file-level idempotency)
    3. Apply categorization rules for uncategorized transactions
    4. Detect and mark matching/transfer transactions in existing ledger
    5. Archive source files
    6. Track import metadata
    
    Usage:
        # Basic usage (categorization only, no matching)
        with IngestService().init_with_url(DB_URL) as ingest_svc:
            report = ingest_svc.ingest_qif(
                file_path='downloads/statement.qif',
                book_name='personal'
            )
        
        # With matching enabled (requires matching rules)
        from ledger.business.matching_service import MatchingRules
        matching_rules = MatchingRules('matching-config.json')
        
        with IngestService(matching_rules=matching_rules).init_with_url(DB_URL) as ingest_svc:
            report = ingest_svc.ingest_qif(...)
    """
    
    def __init__(
        self,
        session=None,
        archive_service: Optional[ArchiveService] = None,
        matching_rules=None,  # Optional[MatchingRules]
        category_rules_path: str = CATEGORY_RULES_PATH,
    ):
        super().__init__(session=session)
        self.archive_service = archive_service or ArchiveService()
        self.matching_rules = matching_rules
        self.category_rules_path = category_rules_path
        self._categorize_service = None  # Lazy init to share session
    
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
        
        # Import transactions with categorization and matching
        result = self._import_with_categorization_and_matching(
            book_id=book.id,
            import_account=account,
            import_file_id=import_file.id,
            transaction_data=transaction_data,
        )
        
        return IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=import_file.id,
            transactions_imported=result['imported'],
            transactions_matched=result['matched'],
            transactions_categorized=result['categorized'],
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            archive_path=archive_path,
            message=f"Imported {result['imported']}, matched {result['matched']}, categorized {result['categorized']}",
            errors=result.get('errors', [])
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
        
        Flow:
        1. Parse QIF file
        2. Check for duplicate imports (idempotency)
        3. Apply categorization for any uncategorized transactions
        4. Check for matching transfers in existing ledger
        5. Insert non-matched transactions
        6. Archive source file
        
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
        
        # Import transactions with categorization and matching
        result = self._import_with_categorization_and_matching(
            book_id=book.id,
            import_account=account,
            import_file_id=import_file.id,
            transaction_data=transaction_data,
        )
        
        return IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=import_file.id,
            transactions_imported=result['imported'],
            transactions_matched=result['matched'],
            transactions_categorized=result['categorized'],
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            archive_path=archive_path,
            message=f"Imported {result['imported']}, matched {result['matched']}, categorized {result['categorized']}",
            errors=result.get('errors', [])
        )
    
    def _import_with_categorization_and_matching(
        self,
        book_id: int,
        import_account: Account,
        import_file_id: int,
        transaction_data: List[dict],
    ) -> dict:
        """
        Import transaction data with categorization and matching.
        
        Flow for each transaction:
        1. Check if category is Uncategorized -> apply categorization rules
        2. Build Transaction object
        3. Check for matching existing transaction (if matching rules configured)
        4. Either mark existing as matched OR insert new transaction
        
        Args:
            book_id: Book ID
            import_account: The account being imported into
            import_file_id: Import file ID for provenance tracking
            transaction_data: List of transaction data dicts from parser
        
        Returns:
            Dict with counts: {'imported': N, 'matched': N, 'categorized': N, 'errors': [...]}
        """
        result = {
            'imported': 0,
            'matched': 0,
            'categorized': 0,
            'errors': [],
        }
        
        # Step 1: Apply categorization to transaction data where needed
        categorized_data = self._apply_categorization(book_id, transaction_data)
        result['categorized'] = categorized_data['categorized_count']
        
        # Step 2: Build Transaction objects
        transactions = self._build_transaction_objects(
            book_id, import_file_id, categorized_data['transaction_data']
        )
        
        # Step 3 & 4: Use MatchingService for smart import with duplicate detection
        if self.matching_rules:
            txn_service = TransactionService(session=self.session)
            txn_service.data_access = self.data_access  # Share session
            
            matching_service = MatchingService(
                matching_rules=self.matching_rules,
                transaction_service=txn_service
            )
            matching_service.data_access = self.data_access  # Share session
            
            # Use import_transactions which handles matching and insertion
            import_result = matching_service.import_transactions(
                book_id=book_id,
                import_for=import_account,
                to_import=transactions
            )
            result['imported'] = import_result['imported']
            result['matched'] = import_result['matched']
        else:
            # Direct insert (no matching rules configured)
            for txn in transactions:
                try:
                    self.data_access.insert_transaction(txn)
                    result['imported'] += 1
                except Exception as e:
                    result['errors'].append(f"Failed to import '{txn.transaction_description}': {e}")
        
        return result
    
    def _get_categorize_service(self) -> CategorizeService:
        """Get or create CategorizeService with shared session."""
        if self._categorize_service is None:
            self._categorize_service = CategorizeService(
                session=self.session,
                rules_path=self.category_rules_path
            )
            self._categorize_service.data_access = self.data_access  # Share session
        return self._categorize_service
    
    def _apply_categorization(
        self,
        book_id: int,
        transaction_data: List[dict],
    ) -> dict:
        """
        Apply categorization rules to uncategorized transactions.
        
        Uses CategorizeService.lookup_category_for_payee() for tiered lookup.
        Modifies transaction_data in place to update category account names.
        
        Args:
            book_id: Book ID for looking up accounts
            transaction_data: List of transaction data dicts
        
        Returns:
            Dict with categorized_count and updated transaction_data
        """
        categorized_count = 0
        categorize_svc = self._get_categorize_service()
        
        for data in transaction_data:
            # Find the counter-split (not the import account split)
            for split_data in data['splits']:
                account_name = split_data['account_name']
                
                # Check if this split needs categorization
                if not account_name:  # Only categorize if L field was absent
                    # Get payee_norm for categorization lookup
                    payee_norm = data.get('payee_norm')
                    if not payee_norm:
                        payee_norm = ChaseCsvParser.normalize_payee(
                            data['transaction_description']
                        )
                        data['payee_norm'] = payee_norm
                    
                    # Use CategorizeService for tiered lookup (cache -> rules -> None)
                    result = categorize_svc.lookup_category_for_payee(payee_norm, book_id)
                    
                    if result:
                        category_name, source = result
                        split_data['account_name'] = category_name
                        categorized_count += 1
                        logger.debug(f"Categorized '{payee_norm}' from {source} -> {category_name}")
                    else:
                        # Tier 3: Fallback - keep existing category (may already be Uncategorized)
                        logger.debug(f"No category found for '{payee_norm}', keeping as {account_name}")
        
        return {
            'categorized_count': categorized_count,
            'transaction_data': transaction_data,
        }
    
    
    def _build_transaction_objects(
        self,
        book_id: int,
        import_file_id: int,
        transaction_data: List[dict],
    ) -> List[Transaction]:
        """
        Convert transaction data dicts to Transaction objects.
        
        Args:
            book_id: Book ID
            import_file_id: Import file ID for provenance
            transaction_data: List of transaction data dicts
        
        Returns:
            List of Transaction objects with resolved accounts
        """
        transactions = []
        
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
            
            transactions.append(transaction)
        
        return transactions
    
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
