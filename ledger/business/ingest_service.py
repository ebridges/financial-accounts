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
from enum import Enum
from logging import getLogger

from ledger.business.book_context import BookContext

logger = getLogger(__name__)
from ledger.business.matching_service import MatchingService
from ledger.business.categorize_service import CategorizeService
from ledger.config import CATEGORY_RULES_PATH, UNCATEGORIZED_ACCOUNT, MATCHING_RULES_PATH
from ledger.util.qif import Qif
from ledger.db.models import ImportFile


class IngestResult(Enum):
    """Result of an ingest operation."""
    IMPORTED = "imported"
    SKIPPED_DUPLICATE = "skipped"
    HASH_MISMATCH = "mismatch"


@dataclass
class IngestReport:
    """Report from an ingest operation."""
    result: IngestResult
    import_file_id: int | None = None
    transactions_imported: int = 0
    transactions_matched: int = 0
    transactions_categorized: int = 0
    message: str = ""


class IngestService:
    """QIF ingestion with idempotency, categorization, and optional matching."""
    
    def __init__(
        self,
        ctx: BookContext,
        matching_rules: str = MATCHING_RULES_PATH,
        category_rules_path: str = CATEGORY_RULES_PATH,
    ):
        self._ctx = ctx
        self.matching_rules = matching_rules
        self.category_rules_path = category_rules_path

    def ingest_qif(self, file_path: str) -> IngestReport:
        """Ingest a QIF file. Returns IngestReport with operation details."""
        filename = os.path.basename(file_path)
        logger.info(f"Starting ingestion of '{filename}'")
        logger.debug(f"Full path: {file_path}")
        
        file_hash = self._compute_file_hash(file_path)
        logger.debug(f"File hash: {file_hash[:16]}...")
        book = self._ctx.book
        
        # Parse QIF
        logger.debug("Parsing QIF file")
        qif = Qif().init_from_qif_file(file_path)
        account_name = qif.account_info.get('N')
        if not account_name:
            logger.error(f"QIF file '{filename}' missing account information")
            raise ValueError("QIF file does not contain account information")
        logger.debug(f"QIF account: '{account_name}', {len(qif.transactions)} transactions")
        
        # Look up account
        try:
            account = self._ctx.accounts.lookup_by_name(account_name)
            logger.debug(f"Resolved account '{account_name}' to id={account.id}")
        except Exception:
            logger.error(f"Account '{account_name}' not found in book '{book.name}'")
            raise ValueError(f"Account '{account_name}' not found in book '{book.name}'")
        
        # Idempotency check
        logger.debug("Checking for existing import")
        existing = self._ctx.dal.get_import_file_by_scope(book.id, account.id, filename)
        if existing:
            if existing.file_hash == file_hash:
                logger.info(f"Skipping '{filename}' - already imported (id={existing.id})")
                return IngestReport(
                    result=IngestResult.SKIPPED_DUPLICATE,
                    import_file_id=existing.id,
                    message=f"File '{filename}' already imported"
                )
            logger.warning(f"File '{filename}' exists with different hash (id={existing.id})")
            return IngestReport(
                result=IngestResult.HASH_MISMATCH,
                import_file_id=existing.id,
                message=f"File '{filename}' exists with different content"
            )
        
        # Categorize transactions where L field is missing
        logger.debug("Categorizing transactions without L field")
        categorize_svc = CategorizeService(ctx=self._ctx, rules_path=self.category_rules_path)
        categorized_count = 0
        uncategorized_count = 0

        for txn in qif.transactions:
            if not Qif.get_category(txn):
                payee = Qif.normalized_payee(txn)
                result = categorize_svc.lookup_category_for_payee(payee)
                if result:
                    category_name, _ = result
                    Qif.set_category(txn, category_name)
                    categorized_count += 1
                else:
                    # Default to Uncategorized when no category can be determined
                    Qif.set_category(txn, UNCATEGORIZED_ACCOUNT)
                    uncategorized_count += 1
        
        if categorized_count > 0 or uncategorized_count > 0:
            logger.debug(f"Categorization: {categorized_count} auto-categorized, {uncategorized_count} defaulted to Uncategorized")
        
        # Convert to Transaction objects
        def resolve_account(name):
            try:
                return self._ctx.accounts.lookup_by_name(name)
            except Exception:
                logger.warning(f"Could not resolve account '{name}'")
                return None
        
        logger.debug("Converting QIF to Transaction objects")
        transactions = qif.as_transactions(book.id, resolve_account)
        
        # Match and insert
        stats = {'imported': 0, 'matched': 0, 'categorized': categorized_count}
        
        if self.matching_rules:
            logger.debug("Matching enabled - checking for transfer matches")
            matching_svc = MatchingService(self.matching_rules)
            accounts_to_query = matching_svc.get_matchable_accounts(account)
            
            if accounts_to_query:
                start, end = matching_svc.compute_candidate_date_range(transactions)
                logger.debug(f"Querying candidates from {start} to {end} in {len(accounts_to_query)} accounts")
                candidates = self._ctx.transactions.query_unmatched(
                    start, end, list(accounts_to_query)
                )
                logger.debug(f"Found {len(candidates)} candidate transactions for matching")
                
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
                logger.debug("No matchable accounts configured, inserting all")
                for txn in transactions:
                    self._ctx.transactions.insert(txn)
                    stats['imported'] += 1
        else:
            logger.debug("Matching disabled, inserting all transactions")
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
        
        logger.info(f"Imported '{filename}': {stats['imported']} transactions, {stats['matched']} matched, {stats['categorized']} categorized")
        
        return IngestReport(
            result=IngestResult.IMPORTED,
            import_file_id=import_file.id,
            transactions_imported=stats['imported'],
            transactions_matched=stats['matched'],
            transactions_categorized=stats['categorized'],
            message=f"Imported {stats['imported']}, matched {stats['matched']}, categorized {stats['categorized']}"
        )
    
    def list_imports(self) -> list[ImportFile]:
        """List all import files for this book."""
        return self._ctx.dal.list_import_files_for_book(self._ctx.book.id)
    
    def get_import(self, import_file_id: int) -> ImportFile | None:
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
