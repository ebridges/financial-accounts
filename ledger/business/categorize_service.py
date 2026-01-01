# categorize_service.py
"""
High-level categorization service for assigning categories to transactions.

Implements tiered categorization:
1. Category cache (exact payee_norm match) - fastest
2. Regex rules from category-payee-lookup.json
3. Fallback to Uncategorized account

Composes lower-level services and utilities to update transaction splits
with the appropriate category (counter-account).
"""
import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from ledger.business.base_service import BaseService
from ledger.config import CATEGORY_RULES_PATH, UNCATEGORIZED_ACCOUNT
from ledger.db.models import Transaction, Split, Account


@dataclass
class CategorizationResult:
    """Result of categorizing a single transaction."""
    transaction_id: int
    payee_norm: str
    category_account: str
    source: str  # 'cache', 'rule', 'fallback'
    confidence: float = 1.0


@dataclass
class CategorizationReport:
    """Summary report of a categorization run."""
    transactions_processed: int = 0
    categorized_from_cache: int = 0
    categorized_from_rules: int = 0
    categorized_fallback: int = 0
    errors: List[str] = field(default_factory=list)
    results: List[CategorizationResult] = field(default_factory=list)
    
    @property
    def total_categorized(self) -> int:
        return self.categorized_from_cache + self.categorized_from_rules
    
    @property
    def success_rate(self) -> float:
        if self.transactions_processed == 0:
            return 0.0
        return (self.total_categorized / self.transactions_processed) * 100


class CategoryRules:
    """
    Loads and applies category rules from JSON file.
    
    The JSON structure maps account full names (categories) to payee patterns:
    {
        "Expenses:Food:Groceries": [
            {"payee": "WHOLE FOODS", "type": "literal"},
            {"payee": "^TRADER JOE", "type": "regex"}
        ],
        ...
    }
    """
    
    def __init__(self, rules_path: str = CATEGORY_RULES_PATH):
        self.rules_path = rules_path
        self.rules: Dict[str, List[dict]] = {}
        self._compiled_patterns: Dict[str, List[Tuple[re.Pattern, str]]] = {}
        self._load_rules()
    
    def _load_rules(self):
        """Load rules from JSON file."""
        try:
            with open(self.rules_path, 'r') as f:
                self.rules = json.load(f)
        except FileNotFoundError:
            self.rules = {}
            return
        
        # Pre-compile regex patterns for performance
        for category, patterns in self.rules.items():
            compiled = []
            for pattern_def in patterns:
                payee = pattern_def.get('payee', '')
                pattern_type = pattern_def.get('type', 'literal')
                
                if pattern_type == 'regex':
                    try:
                        compiled.append((re.compile(payee, re.IGNORECASE), category))
                    except re.error:
                        # Invalid regex, skip
                        continue
                else:
                    # Literal match - escape for regex
                    try:
                        compiled.append((re.compile(re.escape(payee), re.IGNORECASE), category))
                    except re.error:
                        continue
            
            if compiled:
                self._compiled_patterns[category] = compiled
    
    def match(self, payee_norm: str) -> Optional[str]:
        """
        Find a matching category for a normalized payee.
        
        Args:
            payee_norm: Normalized payee string
        
        Returns:
            Category account full name if matched, None otherwise
        """
        if not payee_norm:
            return None
        
        # Check all patterns
        for category, patterns in self._compiled_patterns.items():
            for pattern, cat in patterns:
                if pattern.search(payee_norm):
                    return cat
        
        return None
    
    def get_categories(self) -> List[str]:
        """Get list of all category account names in rules."""
        return list(self.rules.keys())


class CategorizeService(BaseService):
    """
    High-level service for categorizing transactions.
    
    Implements tiered categorization:
    1. Check category cache for exact payee_norm match
    2. Apply regex rules from category-payee-lookup.json
    3. Fall back to Uncategorized account
    
    Usage:
        with CategorizeService().init_with_url(DB_URL) as cat_svc:
            report = cat_svc.categorize_transactions(
                book_name='personal',
                account_full_name='Assets:Checking Accounts:checking-chase-personal-1381'
            )
    """
    
    def __init__(self, session=None, rules_path: str = CATEGORY_RULES_PATH):
        super().__init__(session=session)
        self.rules = CategoryRules(rules_path)
        self.uncategorized_account = UNCATEGORIZED_ACCOUNT
    
    def categorize_transactions(
        self,
        book_name: str,
        account_full_name: Optional[str] = None,
        import_file_id: Optional[int] = None,
        dry_run: bool = False,
    ) -> CategorizationReport:
        """
        Categorize uncategorized transactions.
        
        Args:
            book_name: Name of the book
            account_full_name: Optional - limit to transactions for this account
            import_file_id: Optional - limit to transactions from this import
            dry_run: If True, don't actually update transactions
        
        Returns:
            CategorizationReport with results
        """
        report = CategorizationReport()
        
        # Get book
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            report.errors.append(f"Book '{book_name}' not found")
            return report
        
        # Get account ID if specified
        account_id = None
        if account_full_name:
            account = self.data_access.get_account_by_fullname_for_book(book.id, account_full_name)
            if not account:
                report.errors.append(f"Account '{account_full_name}' not found")
                return report
            account_id = account.id
        
        # Get transactions to categorize
        transactions = self._get_transactions_needing_categorization(
            book.id, account_id, import_file_id
        )
        
        for txn in transactions:
            report.transactions_processed += 1
            result = self._categorize_single_transaction(txn, book.id, dry_run)
            
            if result:
                report.results.append(result)
                if result.source == 'cache':
                    report.categorized_from_cache += 1
                elif result.source == 'rule':
                    report.categorized_from_rules += 1
                else:
                    report.categorized_fallback += 1
        
        return report
    
    def _get_transactions_needing_categorization(
        self,
        book_id: int,
        account_id: Optional[int],
        import_file_id: Optional[int],
    ) -> List[Transaction]:
        """
        Get transactions that need categorization.
        
        A transaction needs categorization if:
        - It has a split pointing to Uncategorized account
        - It has a split pointing to a placeholder account
        """
        # Get uncategorized account
        uncategorized = self.data_access.get_account_by_fullname_for_book(
            book_id, self.uncategorized_account
        )
        
        return self.data_access.list_uncategorized_transactions(
            book_id, account_id, import_file_id
        )
    
    def _categorize_single_transaction(
        self,
        txn: Transaction,
        book_id: int,
        dry_run: bool,
    ) -> Optional[CategorizationResult]:
        """
        Categorize a single transaction using tiered approach.
        
        Args:
            txn: Transaction to categorize
            book_id: Book ID
            dry_run: If True, don't update database
        
        Returns:
            CategorizationResult or None if cannot categorize
        """
        # Get the payee_norm from transaction or derive from description
        payee_norm = txn.payee_norm
        if not payee_norm:
            from ledger.util.chase_csv import ChaseCsvParser
            payee_norm = ChaseCsvParser.normalize_payee(txn.transaction_description)
        
        # Find the split that needs categorization (the counter-split)
        counter_split = self._find_counter_split(txn)
        if not counter_split:
            return None
        
        # Tier 1: Check category cache
        cache_entry = self.data_access.get_category_from_cache(payee_norm)
        if cache_entry:
            category_account = self.data_access.get_account(cache_entry.account_id)
            if category_account:
                if not dry_run:
                    self._update_split_category(counter_split, category_account)
                    self.data_access.increment_cache_hit(payee_norm)
                
                return CategorizationResult(
                    transaction_id=txn.id,
                    payee_norm=payee_norm,
                    category_account=category_account.full_name,
                    source='cache',
                    confidence=1.0
                )
        
        # Tier 2: Apply regex rules
        matched_category = self.rules.match(payee_norm)
        if matched_category:
            category_account = self.data_access.get_account_by_fullname_for_book(
                book_id, matched_category
            )
            if category_account:
                if not dry_run:
                    self._update_split_category(counter_split, category_account)
                    # Cache this successful match
                    self.data_access.set_category_cache(payee_norm, category_account.id)
                
                return CategorizationResult(
                    transaction_id=txn.id,
                    payee_norm=payee_norm,
                    category_account=matched_category,
                    source='rule',
                    confidence=0.9
                )
        
        # Tier 3: Fallback - leave as uncategorized but report it
        return CategorizationResult(
            transaction_id=txn.id,
            payee_norm=payee_norm,
            category_account=self.uncategorized_account,
            source='fallback',
            confidence=0.0
        )
    
    def _find_counter_split(self, txn: Transaction) -> Optional[Split]:
        """
        Find the counter-split that needs categorization.
        
        In a two-split transaction, one split is the bank account,
        the other is the category/expense account (counter-split).
        """
        if len(txn.splits) != 2:
            return None
        
        for split in txn.splits:
            # The counter-split is usually the one to placeholder or uncategorized
            if split.account.placeholder or 'uncategorized' in split.account.full_name.lower():
                return split
        
        return None
    
    def _update_split_category(self, split: Split, new_account: Account) -> None:
        """Update a split's account (category)."""
        self.data_access.update_split(split.id, account_id=new_account.id)
    
    def categorize_by_payee(
        self,
        book_name: str,
        payee_norm: str,
        category_full_name: str,
    ) -> int:
        """
        Manually categorize all transactions matching a payee.
        
        Also updates the category cache for future imports.
        
        Args:
            book_name: Book name
            payee_norm: Normalized payee to match
            category_full_name: Category account full name
        
        Returns:
            Number of transactions updated
        """
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise ValueError(f"Book '{book_name}' not found")
        
        category_account = self.data_access.get_account_by_fullname_for_book(
            book.id, category_full_name
        )
        if not category_account:
            raise ValueError(f"Category '{category_full_name}' not found")
        
        # Update category cache
        self.data_access.set_category_cache(payee_norm, category_account.id)
        
        # Find and update matching transactions
        # This is a simplified approach - in production you might want
        # a dedicated DAL method for this
        updated = 0
        all_txns = self.data_access.list_transactions_for_book(book.id)
        
        for txn in all_txns:
            txn_payee = txn.payee_norm
            if not txn_payee:
                from ledger.util.chase_csv import ChaseCsvParser
                txn_payee = ChaseCsvParser.normalize_payee(txn.transaction_description)
            
            if txn_payee == payee_norm:
                counter_split = self._find_counter_split(txn)
                if counter_split:
                    self._update_split_category(counter_split, category_account)
                    updated += 1
        
        return updated
    
    def get_uncategorized_payees(self, book_name: str) -> List[Tuple[str, int]]:
        """
        Get list of uncategorized payees with counts.
        
        Useful for identifying payees that need rules.
        
        Args:
            book_name: Book name
        
        Returns:
            List of (payee_norm, count) tuples sorted by count descending
        """
        book = self.data_access.get_book_by_name(book_name)
        if not book:
            raise ValueError(f"Book '{book_name}' not found")
        
        uncategorized_txns = self.data_access.list_uncategorized_transactions(book.id)
        
        payee_counts: Dict[str, int] = {}
        for txn in uncategorized_txns:
            payee = txn.payee_norm
            if not payee:
                from ledger.util.chase_csv import ChaseCsvParser
                payee = ChaseCsvParser.normalize_payee(txn.transaction_description)
            
            if payee:
                payee_counts[payee] = payee_counts.get(payee, 0) + 1
        
        return sorted(payee_counts.items(), key=lambda x: x[1], reverse=True)

