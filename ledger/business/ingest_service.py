# ingest_service.py
"""
Ingestion service for importing QIF files with file-level idempotency.

Usage:
    with BookContext("personal", DB_URL) as ctx:
        report = IngestService(ctx).ingest_qif('statement.qif')
"""
import hashlib
import os
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

from ledger.business.matching_service import MatchingService
from ledger.business.categorize_service import CategorizeService
from ledger.config import CATEGORY_RULES_PATH
from ledger.util.qif import Qif
from ledger.db.models import ImportFile

from ledger.business.book_context import BookContext


class IngestResult(Enum):
    """Result of an ingest operation."""
    IMPORTED = "imported"
    SKIPPED_DUPLICATE = "skipped"
    HASH_MISMATCH = "mismatch"


@dataclass
class IngestReport:
    """Report from an ingest operation."""
    result: IngestResult
    import_file_id: Optional[int] = None
    transactions_imported: int = 0
    transactions_matched: int = 0
    message: str = ""


class IngestService:
    """QIF ingestion with idempotency, categorization, and optional matching."""
    
    def __init__(
        self,
        ctx: BookContext,
        matching_rules=None,
        category_rules_path: str = CATEGORY_RULES_PATH,
    ):
        self._ctx = ctx
        self.matching_rules = matching_rules
        self.category_rules_path = category_rules_path

    def ingest_qif(self, file_path: str) -> IngestReport:
        """Ingest a QIF file. Returns IngestReport with operation details."""
        filename = os.path.basename(file_path)
        file_hash = self._compute_file_hash(file_path)
        book = self._ctx.book
        
        # Parse QIF
        qif = Qif().init_from_qif_file(file_path)
        account_name = qif.account_info.get('N')
        if not account_name:
            raise ValueError("QIF file does not contain account information")
        
        # Look up account
        try:
            account = self._ctx.accounts.lookup_by_name(account_name)
        except Exception:
            raise ValueError(f"Account '{account_name}' not found in book '{book.name}'")
        
        # Idempotency check
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
        
        # Categorize transactions where L field is missing
        categorize_svc = CategorizeService(ctx=self._ctx, rules_path=self.category_rules_path)
        
        for txn in qif.transactions:
            if not Qif.get_category(txn):
                payee = Qif.normalized_payee(txn)
                result = categorize_svc.lookup_category_for_payee(payee)
                if result:
                    category_name, _ = result
                    Qif.set_category(txn, category_name)
        
        # Convert to Transaction objects
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
                candidates = self._ctx.transactions.query_unmatched(
                    start, end, list(accounts_to_query)
                )
                
                for action, txn in matching_svc.match_transactions(
                    account, transactions, candidates
                ):
                    if action == 'match':
                        self._ctx.transactions.mark_matched(txn)
                        stats['matched'] += 1
                    else:
                        self._ctx.transactions.insert(txn)
                        stats['imported'] += 1
            else:
                for txn in transactions:
                    self._ctx.transactions.insert(txn)
                    stats['imported'] += 1
        else:
            for txn in transactions:
                self._ctx.transactions.insert(txn)
                stats['imported'] += 1
        
        # Record import
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
        """List all import files for this book."""
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
