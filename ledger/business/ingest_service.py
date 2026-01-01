# ingest_service.py
"""
High-level ingestion service for importing QIF files.

Orchestrates the Qif parser, CategorizeService, and MatchingService to
provide file-level idempotent import with:
- Automatic categorization for transactions without a category (L field absent)
- Transfer/duplicate matching against existing ledger entries (if matching rules configured)
"""
import hashlib
import os
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
from logging import getLogger

from ledger.business.base_service import BaseService
from ledger.business.matching_service import MatchingService
from ledger.business.categorize_service import CategorizeService
from ledger.config import CATEGORY_RULES_PATH
from ledger.util.qif import Qif
from ledger.util.normalize import normalize_payee
from ledger.db.models import ImportFile

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
    message: str = ""


class IngestService(BaseService):
    """
    Service for ingesting QIF files with file-level idempotency.
    
    Flow:
    1. Parse QIF file
    2. Check for duplicate imports (idempotency)
    3. Categorize transactions where L field is missing
    4. Convert to Transaction objects
    5. Match against existing ledger (if matching rules configured)
    6. Insert non-matched transactions
    7. Record import metadata
    
    Usage:
        # Basic usage (no matching)
        with IngestService().init_with_url(DB_URL) as ingest_svc:
            report = ingest_svc.ingest_qif('statement.qif', 'personal')
        
        # With matching enabled
        from ledger.business.matching_service import MatchingRules
        matching_rules = MatchingRules()
        
        with IngestService(matching_rules=matching_rules).init_with_url(DB_URL) as svc:
            report = svc.ingest_qif('statement.qif', 'personal')
    """
    
    def __init__(
        self,
        session=None,
        matching_rules=None,
        category_rules_path: str = CATEGORY_RULES_PATH,
    ):
        super().__init__(session=session)
        self.matching_rules = matching_rules
        self.category_rules_path = category_rules_path

    def ingest_qif(self, file_path: str, book_name: str) -> IngestReport:
        """
        Ingest a QIF file.
        
        Args:
            file_path: Path to the QIF file
            book_name: Name of the book to import into
        
        Returns:
            IngestReport with details of the operation
        """
        filename = os.path.basename(file_path)
        file_hash = self._compute_file_hash(file_path)
        
        # Validate book
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise ValueError(f"Book '{book_name}' not found")
        
        # Parse QIF
        qif = Qif().init_from_qif_file(file_path)
        account_name = qif.account_info.get('N')
        if not account_name:
            raise ValueError("QIF file does not contain account information")
        
        account = self.data_access.get_account_by_fullname_for_book(book.id, account_name)
        if not account:
            raise ValueError(f"Account '{account_name}' not found in book '{book_name}'")
        
        # Idempotency check
        existing = self.data_access.get_import_file_by_scope(book.id, account.id, filename)
        if existing:
            if existing.file_hash == file_hash:
                return IngestReport(
                    result=IngestResult.SKIPPED_DUPLICATE,
                    import_file_id=existing.id,
                    message=f"File '{filename}' already imported"
                )
            return IngestReport(
                result=IngestResult.HASH_MISMATCH,
                import_file_id=existing.id,
                message=f"File '{filename}' exists with different content"
            )
        
        # Categorize raw QIF transactions where L field is missing
        categorize_svc = CategorizeService(
            session=self.session,
            rules_path=self.category_rules_path
        )
        categorize_svc.data_access = self.data_access
        
        for txn in qif.transactions:
            if not Qif.get_category(txn):
                payee = Qif.get_payee(txn)
                result = categorize_svc.lookup_category_for_payee(
                    normalize_payee(payee), book.id
                )
                if result:
                    category_name, _ = result
                    Qif.set_category(txn, category_name)
        
        # Convert to Transaction objects
        def resolve_account(book_id, name):
            return self.data_access.get_account_by_fullname_for_book(book_id, name)
        
        transactions = qif.as_transactions(book.id, resolve_account)
        
        # Match and insert
        stats = {'imported': 0, 'matched': 0}
        
        if self.matching_rules:
            matching_svc = MatchingService(self.matching_rules)
            accounts_to_query = matching_svc.get_matchable_accounts(account)
            
            if accounts_to_query:
                start, end = matching_svc.compute_candidate_date_range(transactions)
                candidates = self.data_access.query_for_unmatched_transactions_in_range(
                    book.id, start, end, list(accounts_to_query)
                )
                
                for action, txn in matching_svc.match_transactions(
                    account, transactions, candidates
                ):
                    if action == 'match':
                        self.data_access.update_transaction_match_status(txn)
                        stats['matched'] += 1
                    else:
                        self.data_access.insert_transaction(txn)
                        stats['imported'] += 1
            else:
                # No matchable accounts configured, just import all
                for txn in transactions:
                    self.data_access.insert_transaction(txn)
                    stats['imported'] += 1
        else:
            # No matching rules, just import all
            for txn in transactions:
                self.data_access.insert_transaction(txn)
                stats['imported'] += 1
        
        # Record import
        dates = [t.transaction_date for t in transactions]
        import_file = self.data_access.create_import_file(
            book_id=book.id,
            account_id=account.id,
            filename=filename,
            source_type='qif',
            file_hash=file_hash,
            source_path=file_path,
            coverage_start=min(dates) if dates else None,
            coverage_end=max(dates) if dates else None,
            row_count=len(transactions),
        )
        
        return IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=import_file.id,
            transactions_imported=stats['imported'],
            transactions_matched=stats['matched'],
            message=f"Imported {stats['imported']}, matched {stats['matched']}"
        )
    
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
