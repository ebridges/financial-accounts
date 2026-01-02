# ingest_service.py
"""
High-level ingestion service for importing QIF files.

Orchestrates the Qif parser, CategorizeService, and MatchingService to
provide file-level idempotent import with:
- Automatic categorization for transactions without a category (L field absent)
- Transfer/duplicate matching against existing ledger entries (if matching rules configured)

Usage:
    with BookContext("personal", DB_URL) as ctx:
        ingest_svc = IngestService(ctx)
        report = ingest_svc.ingest_qif('statement.qif')
        
    # With matching enabled
    with BookContext("personal", DB_URL) as ctx:
        ingest_svc = IngestService(ctx, matching_rules=MatchingRules())
        report = ingest_svc.ingest_qif('statement.qif')
"""
import hashlib
import os
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING
from enum import Enum
from logging import getLogger

from ledger.business.matching_service import MatchingService
from ledger.business.categorize_service import CategorizeService
from ledger.config import CATEGORY_RULES_PATH
from ledger.util.qif import Qif
from ledger.db.models import ImportFile

if TYPE_CHECKING:
    from ledger.business.book_context import BookContext

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


class IngestService:
    """
    Service for ingesting QIF files with file-level idempotency.
    
    This service operates within a BookContext, using the context's
    AccountService and TransactionService for account/transaction operations.
    
    Flow:
    1. Parse QIF file
    2. Check for duplicate imports (idempotency)
    3. Categorize transactions where L field is missing
    4. Convert to Transaction objects
    5. Match against existing ledger (if matching rules configured)
    6. Insert non-matched transactions
    7. Record import metadata
    """
    
    def __init__(
        self,
        ctx: 'BookContext',
        matching_rules=None,
        category_rules_path: str = CATEGORY_RULES_PATH,
    ):
        """
        Initialize IngestService with a BookContext.
        
        Args:
            ctx: BookContext providing shared session, book, and services
            matching_rules: Optional MatchingRules for transfer/duplicate matching
            category_rules_path: Path to category rules JSON file
        """
        self._ctx = ctx
        self.matching_rules = matching_rules
        self.category_rules_path = category_rules_path

    def ingest_qif(self, file_path: str) -> IngestReport:
        """
        Ingest a QIF file into the book.
        
        Args:
            file_path: Path to the QIF file
        
        Returns:
            IngestReport with details of the operation
        """
        filename = os.path.basename(file_path)
        file_hash = self._compute_file_hash(file_path)
        book = self._ctx.book
        
        # Parse QIF
        qif = Qif().init_from_qif_file(file_path)
        account_name = qif.account_info.get('N')
        if not account_name:
            raise ValueError("QIF file does not contain account information")
        
        # Look up account via AccountService
        try:
            account = self._ctx.accounts.lookup_by_name(account_name)
        except Exception:
            raise ValueError(f"Account '{account_name}' not found in book '{book.name}'")
        
        # Idempotency check (use DAL for import file tracking)
        existing = self._ctx.dal.get_import_file_by_scope(book.id, account.id, filename)
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
            ctx=self._ctx,
            rules_path=self.category_rules_path
        )
        
        for txn in qif.transactions:
            if not Qif.get_category(txn):
                payee = Qif.normalized_payee(txn)
                result = categorize_svc.lookup_category_for_payee(payee)
                if result:
                    category_name, _ = result
                    Qif.set_category(txn, category_name)
        
        # Convert to Transaction objects using AccountService for lookups
        def resolve_account(name):
            try:
                return self._ctx.accounts.lookup_by_name(name)
            except Exception:
                return None
        
        transactions = qif.as_transactions(book.id, resolve_account)
        
        # Match and insert
        stats = {'imported': 0, 'matched': 0}
        
        if self.matching_rules:
            matching_svc = MatchingService(self.matching_rules)
            accounts_to_query = matching_svc.get_matchable_accounts(account)
            
            if accounts_to_query:
                start, end = matching_svc.compute_candidate_date_range(transactions)
                # Use TransactionService for querying
                candidates = self._ctx.transactions.query_unmatched(
                    start, end, list(accounts_to_query)
                )
                
                for action, txn in matching_svc.match_transactions(
                    account, transactions, candidates
                ):
                    if action == 'match':
                        # Use TransactionService to mark matched
                        self._ctx.transactions.mark_matched(txn)
                        stats['matched'] += 1
                    else:
                        # Use TransactionService to insert
                        self._ctx.transactions.insert(txn)
                        stats['imported'] += 1
            else:
                # No matchable accounts configured, just import all
                for txn in transactions:
                    self._ctx.transactions.insert(txn)
                    stats['imported'] += 1
        else:
            # No matching rules, just import all
            for txn in transactions:
                self._ctx.transactions.insert(txn)
                stats['imported'] += 1
        
        # Record import (use DAL for import file tracking)
        dates = [t.transaction_date for t in transactions]
        import_file = self._ctx.dal.create_import_file(
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
    
    def list_imports(self) -> List[ImportFile]:
        """
        List all import files for this book.
        
        Returns:
            List of ImportFile records
        """
        return self._ctx.dal.list_import_files_for_book(self._ctx.book.id)
    
    def get_import(self, import_file_id: int) -> Optional[ImportFile]:
        """Get an import file by ID."""
        return self._ctx.dal.get_import_file(import_file_id)
    
    @staticmethod
    def _compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
