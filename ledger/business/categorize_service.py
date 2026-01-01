# categorize_service.py
"""
Categorization service for looking up categories based on payee patterns.

Implements tiered categorization lookup:
1. Category cache (exact payee_norm match) - fastest
2. Regex rules from category-payee-lookup.json
3. Returns None (caller handles fallback)

This service is used by IngestService during transaction import to
automatically assign categories to transactions that lack one.
"""
import json
import re
from typing import List, Dict, Optional, Tuple

from ledger.business.base_service import BaseService
from ledger.config import CATEGORY_RULES_PATH


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
    Service for looking up categories for transactions based on payee patterns.
    
    Used by IngestService during import to auto-categorize transactions
    that don't have a category (L field absent in QIF, or CSV imports).
    
    Tiered lookup:
    1. Check category cache for exact payee_norm match (fastest)
    2. Apply regex rules from category-payee-lookup.json
    3. Return None (caller handles fallback, e.g., keep existing or use Uncategorized)
    
    Usage:
        with CategorizeService().init_with_url(DB_URL) as cat_svc:
            result = cat_svc.lookup_category_for_payee("WHOLE FOODS", book_id)
            if result:
                category_name, source = result  # ('Expenses:Food:Groceries', 'rule')
    """
    
    def __init__(self, session=None, rules_path: str = CATEGORY_RULES_PATH):
        super().__init__(session=session)
        self.rules = CategoryRules(rules_path)
    
    def lookup_category_for_payee(
        self,
        payee_norm: str,
        book_id: int,
        update_cache: bool = True,
    ) -> Optional[Tuple[str, str]]:
        """
        Look up the category for a normalized payee using tiered approach.
        
        Tiers:
        1. Category cache (exact payee_norm match)
        2. Regex rules from category-payee-lookup.json
        3. Returns None (caller handles fallback)
        
        Args:
            payee_norm: Normalized payee string
            book_id: Book ID for account lookups
            update_cache: Whether to update cache on rule match (default True)
        
        Returns:
            Tuple of (category_account_fullname, source) where source is 'cache' or 'rule',
            or None if no category found
        """
        if not payee_norm:
            return None
        
        # Tier 1: Check category cache
        cache_entry = self.data_access.get_category_from_cache(payee_norm)
        if cache_entry:
            category_account = self.data_access.get_account(cache_entry.account_id)
            if category_account:
                if update_cache:
                    self.data_access.increment_cache_hit(payee_norm)
                return (category_account.full_name, 'cache')
        
        # Tier 2: Apply regex rules
        matched_category = self.rules.match(payee_norm)
        if matched_category:
            # Verify the account exists
            category_account = self.data_access.get_account_by_fullname_for_book(
                book_id, matched_category
            )
            if category_account:
                if update_cache:
                    # Cache this match for future lookups
                    self.data_access.set_category_cache(payee_norm, category_account.id)
                return (matched_category, 'rule')
        
        # Tier 3: No match - return None, let caller handle fallback
        return None
