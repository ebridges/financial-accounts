# categorize_service.py
"""
Categorization service for looking up categories based on payee patterns.

Implements tiered categorization lookup:
1. Category cache (exact payee_norm match) - fastest
2. Regex rules from category-payee-lookup.json
3. Returns None (caller handles fallback)

This service is used by IngestService during transaction import to
automatically assign categories to transactions that lack one.

Usage:
    with BookContext("personal", DB_URL) as ctx:
        cat_svc = CategorizeService(ctx)
        result = cat_svc.lookup_category_for_payee("WHOLE FOODS")
        if result:
            category_name, source = result  # ('Expenses:Food:Groceries', 'rule')
"""
import json
import re
from logging import getLogger, warning

from ledger.config import CATEGORY_RULES_PATH

logger = getLogger(__name__)
from ledger.business.book_context import BookContext


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
        self.rules: dict[str, list[dict]] = {}
        self._compiled_patterns: dict[str, list[tuple[re.Pattern, str]]] = {}
        self._load_rules()

    def _load_rules(self):
        """Load rules from JSON file."""
        logger.debug(f"_load_rules: loading from '{self.rules_path}'")
        try:
            with open(self.rules_path, 'r') as f:
                self.rules = json.load(f)
        except FileNotFoundError:
            logger.debug("_load_rules: file not found, no rules loaded")
            self.rules = {}
            return

        # Pre-compile regex patterns for performance
        total_patterns = 0
        for category, patterns in self.rules.items():
            compiled = []
            for pattern_def in patterns:
                payee = pattern_def.get('payee', '')
                pattern_type = pattern_def.get('type', 'literal')

                if pattern_type == 'regex':
                    try:
                        compiled.append((re.compile(payee, re.IGNORECASE), category))
                    except re.error as e:
                        logger.debug(f"_load_rules: invalid regex '{payee}' for {category}: {e}")
                        continue
                else:
                    # Literal match - escape for regex
                    try:
                        compiled.append((re.compile(re.escape(payee), re.IGNORECASE), category))
                    except re.error as e:
                        logger.debug(f"_load_rules: invalid literal '{payee}' for {category}: {e}")
                        continue

            if compiled:
                self._compiled_patterns[category] = compiled
                total_patterns += len(compiled)

        logger.debug(
            f"_load_rules: loaded {len(self._compiled_patterns)} categories with {total_patterns} patterns"
        )

    def match(self, payee_norm: str) -> str | None:
        """
        Find a matching category for a normalized payee.

        Args:
            payee_norm: Normalized payee string

        Returns:
            Category account full name if matched, None otherwise
        """
        if not payee_norm:
            logger.debug("match: empty payee_norm, returning None")
            return None

        logger.debug(
            f"match: searching {len(self._compiled_patterns)} categories for '{payee_norm}'"
        )

        # Check all patterns
        for category, patterns in self._compiled_patterns.items():
            for pattern, cat in patterns:
                if pattern.search(payee_norm):
                    logger.debug(
                        f"match: FOUND - pattern '{pattern.pattern}' matched, category='{cat}'"
                    )
                    return cat

        logger.debug(f"match: no pattern matched for '{payee_norm}'")
        return None

    def get_categories(self) -> list[str]:
        """Get list of all category account names in rules."""
        return list(self.rules.keys())


class CategorizeService:
    """
    Service for looking up categories for transactions based on payee patterns.

    This service operates within a BookContext, using the context's
    AccountService for account lookups.

    Tiered lookup:
    1. Check category cache for exact payee_norm match (fastest)
    2. Apply regex rules from category-payee-lookup.json
    3. Return None (caller handles fallback, e.g., keep existing or use Uncategorized)
    """

    def __init__(self, ctx: 'BookContext', rules_path: str = CATEGORY_RULES_PATH):
        """
        Initialize CategorizeService with a BookContext.

        Args:
            ctx: BookContext providing shared session, book, and services
            rules_path: Path to category rules JSON file
        """
        self._ctx = ctx
        self.rules = CategoryRules(rules_path)

    def lookup_category_for_payee(
        self,
        payee_norm: str,
        update_cache: bool = True,
    ) -> tuple[str, str] | None:
        """
        Look up the category for a normalized payee using tiered approach.

        Tiers:
        1. Category cache (exact payee_norm match)
        2. Regex rules from category-payee-lookup.json
        3. Returns None (caller handles fallback)

        Args:
            payee_norm: Normalized payee string
            update_cache: Whether to update cache on rule match (default True)

        Returns:
            Tuple of (category_account_fullname, source) where source is 'cache' or 'rule',
            or None if no category found
        """
        logger.debug(f"lookup_category_for_payee: starting lookup for '{payee_norm}'")

        if not payee_norm:
            logger.debug("lookup_category_for_payee: empty payee_norm, returning None")
            return None

        # Tier 1: Check category cache (use DAL for cache operations)
        logger.debug(f"lookup_category_for_payee: Tier 1 - checking cache for '{payee_norm}'")
        cache_entry = self._ctx.dal.get_category_from_cache(payee_norm)
        if cache_entry:
            logger.debug(
                f"lookup_category_for_payee: cache HIT - account_id={cache_entry.account_id}"
            )
            # Use AccountService for account lookup
            try:
                category_account = self._ctx.accounts.lookup_by_id(cache_entry.account_id)
                if update_cache:
                    self._ctx.dal.increment_cache_hit(payee_norm)
                logger.debug(
                    f"lookup_category_for_payee: returning cached category '{category_account.full_name}'"
                )
                return (category_account.full_name, 'cache')
            except Exception as e:
                # Account not found, continue to tier 2
                logger.debug(
                    f"lookup_category_for_payee: cache entry invalid (account not found: {e}), continuing to Tier 2"
                )
        else:
            logger.debug("lookup_category_for_payee: cache MISS")

        # Tier 2: Apply regex rules
        logger.debug(f"lookup_category_for_payee: Tier 2 - applying regex rules for '{payee_norm}'")
        matched_category = self.rules.match(payee_norm)
        if matched_category:
            logger.debug(f"lookup_category_for_payee: rule matched category '{matched_category}'")
            # Verify the account exists using AccountService
            try:
                category_account = self._ctx.accounts.lookup_by_name(matched_category)
                if update_cache:
                    # Cache this match for future lookups
                    self._ctx.dal.set_category_cache(payee_norm, category_account.id)
                    logger.debug(
                        f"lookup_category_for_payee: cached mapping '{payee_norm}' -> '{matched_category}'"
                    )
                logger.debug(
                    f"lookup_category_for_payee: returning rule-matched category '{matched_category}'"
                )
                return (matched_category, 'rule')
            except Exception as e:
                warning(
                    f"Category {matched_category} found for payee {payee_norm} but account not found"
                )
                logger.debug(
                    f"lookup_category_for_payee: account '{matched_category}' not found: {e}"
                )

        # Tier 3: No match - return None, let caller handle fallback
        logger.debug(
            f"lookup_category_for_payee: Tier 3 - no match found for '{payee_norm}', returning None"
        )
        return None
