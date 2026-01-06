# AGENTS.md

This file provides domain-specific guidance for AI agents working on this double-entry accounting system. It supplements [CLAUDE.md](CLAUDE.md) (which covers development commands and architecture) with domain knowledge and common pitfalls learned from development.

## 1. Tiered Service Architecture

The application uses a layered service architecture. **Services should use other services rather than bypassing to the data access layer directly.**

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                       CLI Layer                              │
│  ledger/cli.py - Entry point, argument parsing               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│            High-Level Orchestration Services                 │
│  IngestService, MatchingService, CategorizeService           │
│  - Coordinate complex multi-step workflows                   │
│  - Take BookContext, use mid-level services through it       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Mid-Level Business Services                     │
│  AccountService, TransactionService, StatementService,       │
│  ReconciliationService                                       │
│  - Book-scoped operations                                    │
│  - Receive DAL and Book, exposed via BookContext             │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                  Data Access Layer (DAL)                     │
│  ledger/db/data_access.py - Raw database CRUD operations     │
└─────────────────────────────────────────────────────────────┘
```

### BookContext: The Service Coordinator

[BookContext](ledger/business/book_context.py) is the central coordinator that:
- Creates a shared database session
- Initializes all book-scoped services with that session
- Provides property accessors for services: `ctx.accounts`, `ctx.transactions`, `ctx.statements`, `ctx.reconciliation`
- Handles commit/rollback on context exit

```python
with BookContext("personal", DB_URL) as ctx:
    # Use services through the context
    account = ctx.accounts.lookup_by_name("checking-chase-personal-1381")
    ctx.transactions.enter_transaction(...)
```

### Service Composition Pattern

**Correct**: High-level services use mid-level services via BookContext:

```python
class IngestService:
    def __init__(self, ctx: BookContext):
        self._ctx = ctx
    
    def ingest_qif(self, file_path: str):
        # Use AccountService through context
        account = self._ctx.accounts.lookup_by_name(account_name)
        # Use MatchingService (another high-level service)
        matching_svc = MatchingService(self._ctx)
        matching_svc.find_and_mark_matches(...)
```

**Avoid**: Bypassing services to use DAL directly for operations that services provide:

```python
# DON'T do this - use ctx.accounts.lookup_by_name() instead
account = ctx.dal.get_account_by_fullname_for_book(book_id, name)
```

### When DAL Access is Appropriate

Direct DAL access (`ctx.dal`) is appropriate for:
- Operations not covered by existing services (e.g., `get_import_file_by_scope`)
- Bulk queries for reporting/analysis scripts
- Migration scripts that need low-level database access

## 2. Transaction Matching Rules

Transfer transactions appear in both source and destination QIF files. Matching requires checking description patterns, date offsets, and split amounts.

- **Configuration**: [etc/matching-rules.json](etc/matching-rules.json)
- **Pattern documentation**: [validation/matching-patterns.md](validation/matching-patterns.md)
- **Matching service**: [ledger/business/matching_service.py](ledger/business/matching_service.py) contains the definitive logic for applying matching rules.

### Critical: Checking-to-Checking Transfer Behavior

Transfers between checking accounts (for example: 1381 ↔ 1605, 1381 ↔ 9210) appear as **TWO matching but opposite transactions** - one in each account's QIF file. This does NOT apply to transfers between checking and credit card accounts (only checking-to-checking).

These transactions contain a unique transaction number in the payee description that correlates both sides:

```
POnline Transfer to CHK ...1605 transaction#: 11104475445 02/08
```

The embedded transaction number (`11104475445` in this example) uniquely identifies both sides of the same transfer and should be used for duplicate detection when importing QIF files from both accounts.

### Matching Rule Structure

```json
{
  "matching_rules": {
    "source_account_fullname": {
      "target_account_fullname": {
        "date_offset": 1,
        "description_patterns": ["^regex pattern$"]
      }
    }
  }
}
```

- **date_offset**: Number of days tolerance for date matching
- **description_patterns**: Regex patterns that identify transfer transactions

## 3. Common Reconciliation Issues

Based on [migration-scripts/reconciliation-analysis-report.txt](migration-scripts/reconciliation-analysis-report.txt):

| Root Cause | Description | Resolution |
|------------|-------------|------------|
| MISSING_QIF_DATA | Incomplete exports from banks | Re-export QIF files for affected periods |
| SIGN_CONVENTION | Especially for LIABILITY accounts | Review reconciliation logic for account type |
| DUPLICATE_TRANSACTIONS | Overlapping QIF export date ranges | Remove duplicates from boundary dates |
| CASCADING_ERROR | Incorrect starting balances | Fix first error, re-reconcile subsequent |
| SMALL_DISCREPANCIES | Rounding or fee differences | May require manual adjustment entries |

### Boundary Transaction Duplicates

Chase's QIF export includes transactions based on posting date vs. statement date, causing boundary transactions to appear in multiple exports. When a transaction date falls on a statement boundary (e.g., May 8 is both the end of Statement 1 and might appear in Statement 2's export), the transaction belongs only in the earlier statement's QIF file.

## 4. Data Integrity Constraints

- Every transaction must have exactly **2 splits** (debit + credit)
- Splits must **sum to zero** (double-entry accounting)
- Account names must match between QIF files and database
- Import files are **idempotent** via file hash tracking (same file won't import twice)
- Amounts: **positive for debits, negative for credits**
- Match status: `'n'` (not matched), `'m'` (matched)
- Reconciliation states: `'n'` (not reconciled), `'c'` (cleared), `'r'` (reconciled)

## 5. File Organization Conventions

### Directory Structure

```
test-files/
  {year}/
    {account-type}-{bank}-{purpose}-{last4}/
      {start-date}--{end-date}-{account-name}.pdf
      {start-date}--{end-date}-{account-name}.qif
      {start-date}--{end-date}-{account-name}.json
    RECONCILIATION-NOTES.md
```

### Account Naming Convention

- `checking-chase-personal-1381` - Personal checking ending in 1381
- `checking-chase-business-9210` - Business checking ending in 9210
- `creditcard-citi-personal-4217` - Personal Citi credit card ending in 4217
- `creditcard-chase-personal-6063` - Personal Chase credit card ending in 6063

### Date Format in Filenames

- Start and end dates: `YYYY-MM-DD`
- Separator between dates: `--` (double dash)
- Example: `2017-02-09--2017-03-08-checking-chase-personal-1381.qif`

## 6. RECONCILIATION-NOTES.md Format

Each year's `test-files/{year}/` directory contains a `RECONCILIATION-NOTES.md` documenting manual corrections made during reconciliation.

There are currently three formats in use, for legacy reasons.  All new entries should be in **Format B**.


### Format A: Detailed Fix Entry (QIF file corrections)

```markdown
## YYYY-MM-DD: Brief description of fix

**File**: `account-name/start-date--end-date-account-name.qif`

**Transaction**:
- Date: MM/DD/YYYY
- Description: TRANSACTION DESCRIPTION
- Amount: $X,XXX.XX

**Change**:
- **Before**: `LCategory:Subcategory`
- **After**: `LAssets:Account Name`

**Reason**: Explanation of why this correction was needed.

**Status**: PENDING FIX (or omit if complete)
```

### Format B: Numbered Note Entry (journal entries and adjustments)

```markdown
### RN-XXX

__Date__: YYYY-MM-DD  
__Account__: account-name  
__Description__: What was wrong or missing.  
__Resolution__: How it was fixed (journal entry, manual add, etc.)

| Date | Transaction | Category | Amount |
|------|-------------|----------|--------|
| MM/DD | PAYEE NAME | Category | $X.XX |
```

### Format C: Migration Script Entry (auto-generated)

```markdown
## YYYY-MM-DD: Fix description

__Date__: YYYY-MM-DD
__Account__: Multiple accounts or specific account
__Files__: Comma separated list of files.
__Description__: What was fixed and why.
__Resolution__: How duplicates/issues were identified and resolved.

Transactions affected:
- YYYY-MM-DD: Kept ID X, deleted ID Y (description...)
```

## 7. Validation Workflow

Reference [validation/VALIDATION_TESTS.md](validation/VALIDATION_TESTS.md) for the complete testing hierarchy.

### Test Progression (in order of complexity)

1. **Basic validation** - `validate_sample_data.py`
   - Core import and matching functionality
   - Use after changes to core import logic
   - Runtime: ~30 seconds

2. **Real-world scenarios** - `real_world_matching_test.py`
   - Tests manual entry → bank import workflow
   - Use for typical user workflow verification
   - Runtime: ~2 minutes

3. **Comprehensive testing** - `comprehensive_matching_validation.py`
   - 1,783 real transactions across 8.9 years
   - Use for absolute confidence in matching logic
   - Runtime: ~5 minutes

4. **Debugging** - `debug_matching_logic.py`
   - Step-by-step analysis of matching rule evaluation
   - Use when matching isn't working as expected

### Running Validation

```bash
cd validation
python validate_sample_data.py --reset      # Basic
python real_world_matching_test.py --reset  # Real-world
python comprehensive_matching_validation.py --reset --verbose  # Full
python debug_matching_logic.py              # Debug (after real_world test)
```

## 8. Migration Script Patterns

The migration scripts are for the management of the files in `test-files` so that the changes can be applied on the master files (stored elsewhere).

Based on [migration-scripts/001-fix-duplicate-transfers.py](migration-scripts/001-fix-duplicate-transfers.py):

### Required Features

- **Always support `--dry-run` mode** - Show what would be done without making changes
- **Generate reconciliation notes** - Create audit trail entries for RECONCILIATION-NOTES.md
- **Use complementary description matching** - For simplistic transfer detection, check for "TO" in one description and "FROM" in the other.  Note however, the matching service has the definitive logic for matching transfers.


### Script Template

```python
#!/usr/bin/env python3
"""
Migration Script XXX: Description

Problem:
    What issue this migration fixes.

Solution:
    How the migration identifies and fixes the issue.

Usage:
    poetry run python migration-scripts/XXX-description.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ledger.business.book_context import BookContext

DB_URL = "sqlite:///db/accounting-system.db"
BOOK_NAME = "personal"


def main():
    parser = argparse.ArgumentParser(description='Migration description')
    parser.add_argument('--dry-run', action='store_true', default=False,
                       help='Show what would be done without making changes')
    args = parser.parse_args()
    
    if args.dry_run:
        print("\n*** DRY RUN MODE - No changes will be made ***\n")
    
    with BookContext(BOOK_NAME, DB_URL) as ctx:
        # Migration logic here
        pass
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

### Generating Reconciliation Notes

Migration scripts should append entries to the appropriate year's `RECONCILIATION-NOTES.md`:

```python
def generate_reconciliation_note(changes):
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    
    note = f"""## {today}: Fix description

__Date__: {today}
__Account__: Affected account(s)
__Files__: Affected file(s)
__Description__: What was fixed.
__Resolution__: How it was fixed.

Transactions affected:
"""
    for change in changes:
        note += f"- {change['date']}: {change['description']}\n"
    
    return note
```

## 9. QIF File Structure Reference

QIF files contain account info and transactions:

```
!Account
NAssets:Checking Accounts:checking-chase-personal-1381
TBank
^
!Type:Bank
D01/15/2021
T-150.00
POnline Transfer to CHK ...1605 transaction#: 11104475445 01/15
LAssets:Checking Accounts:checking-chase-personal-1605
^
```

### Key QIF Fields

| Field | Description |
|-------|-------------|
| `N` | Account name (in !Account section) |
| `D` | Transaction date (MM/DD/YYYY or MM/DD/YY) |
| `T` | Transaction amount (negative = outflow) |
| `P` | Payee/description |
| `L` | Category/transfer account |
| `M` | Memo |
| `^` | End of record |

### Category Line Format

The `L` line indicates the contra account:
- `LExpenses:Groceries` - Expense category
- `LAssets:Checking Accounts:checking-chase-personal-1605` - Transfer to another account
- `LIncome:Salary` - Income category

