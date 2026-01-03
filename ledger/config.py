# config.py
"""
Configuration constants for the ledger application.

These can be overridden via environment variables.
"""
import os


# Archive path for storing imported files
# Default: 'archive/' relative to current working directory
ARCHIVE_BASE_PATH = os.environ.get('LEDGER_ARCHIVE_PATH', 'archive')

# Path to category-payee lookup rules JSON file
CATEGORY_RULES_PATH = os.environ.get(
    'LEDGER_CATEGORY_RULES_PATH',
    'etc/category-payee-lookup.json'
)

# Default account name for uncategorized transactions
UNCATEGORIZED_ACCOUNT = os.environ.get(
    'LEDGER_UNCATEGORIZED_ACCOUNT',
    'Expenses:Uncategorized'
)

# Path to matching rules JSON file
MATCHING_RULES_PATH = os.environ.get(
    'LEDGER_MATCHING_RULES_PATH',
    'etc/matching-rules.json'
)
