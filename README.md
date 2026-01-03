# Accounting System

## 1. Overview and Objectives
This is a double entry accounting system that provides a robust personal finance tracking and reconciliation application. Users can track transactions across multiple accounts, import data from financial institutions, match preexisting transactions in a configurable way, categorize expenses, and perform periodic reconciliations against bank statements. The design draws on double-entry accounting principles—ensuring data consistency, clarity of debits/credits, and the ability to generate meaningful financial reports.

### Key Objectives
1. **Data Integrity**
    - Use **double-entry** style transactions and splits.
    - Enforce referential integrity using foreign keys.
    - Prevent common data errors (e.g., mis-matched books for transaction vs. account).
2. **Easy Reconciliation**
    - Mark transactions as _cleared_ or _reconciled_ within the system.
    - Provide a mechanism (triggers and foreign keys) to avoid mismatched or duplicated data.
3. **Flexibility and Extensibility**
    - The schema uses **UUID** primary keys, making it easier to merge or migrate data.
    - The system can be adapted to different database backends (e.g., migrating from SQLite to PostgreSQL).
4. **Hierarchical Accounts**
    - Support **parent-child** relationships among accounts (e.g., grouping categories under top-level accounts).
    - Allow organizing expense and income categories in a tree-like structure.
5. **Reporting**
    - The schema supports queries and pivoting on **accounts**, **transactions**, and **splits**, essential for generating income/expense statements or custom reports.

## 2. Transaction matching

### Transaction Matching in an Accounting Ledger

**Transaction matching** is the process of comparing and reconciling individual transactions recorded in a financial ledger against external records (e.g. bank statements, invoices, receipts) to ensure accuracy and completeness.

### How Matching Works

#### Purpose
Matching identifies **transfer transactions** that appear in both accounts (e.g., sending money from checking to savings) to avoid importing duplicates.

#### Matching Rules Structure (`etc/matching-config.json`)

```json
{
  "matching_rules": {
    "Assets:Checking Accounts:checking-chase-personal-1381": {
      "Assets:Checking Accounts:checking-chase-personal-1605": {
        "date_offset": 1,
        "description_patterns": [
          "^Online Transfer\\s+to\\s+CHK\\s*\\.\\.\\.1605"
        ]
      }
    }
  }
}
```

- **Key**: The account being imported
- **Value**: Accounts to check for matching candidates, with patterns and date tolerance

#### Matching Process (per file import)

1. **Find matchable accounts** - Look up which accounts might have matching transfers
2. **Query candidates** - Fetch unmatched transactions from those accounts within the date range
3. **For each imported transaction, check each candidate**:
   - ✓ **Splits match** - Same account IDs and amounts
   - ✓ **Description matches** - Import description matches a defined regex pattern
   - ✓ **Date proximity** - Within `date_offset` days

#### Decision Flow

```
Import Transaction → Found Match?
                         │
              ┌──────────┴──────────┐
              ↓                     ↓
          YES: Mark               NO: Insert
          candidate as            transaction
          "matched"               as new
```

#### Key Points

- Matching happens **during import**, not after
- The **first file** imported has no candidates (0 matches)
- The **second file** finds candidates from the first import
- Matched transactions are **not imported** - only the existing candidate is marked

#### Key Steps:

1. **Import Transactions**
   * Load transactions from external sources (e.g., bank feeds, credit card statements).
   * Standardize date, description, and amount formats.

2. **Identify Matching Criteria**
   * Matching fields include:
     * Date (exact or within a tolerance window)
     * Amount (exact match or net of fees)
     * Payee/description

3. **Match Transactions**
   * This system attempts to match transactions automatically using predefined rules.

4. **Review and Confirm**
   * The system will flag exceptions or mismatches for investigation.

5. **Post and Reconcile**
   * Confirm matches in the ledger.
   * Reconciliation status is updated (e.g., cleared, reconciled).
   * Differences may be logged as adjustments or pending entries.

#### Purpose and Benefits:
* Ensures data integrity between internal ledgers and external financial sources.
* Detects errors (e.g., duplicates, missing entries, fraud).
* Supports month-end close, audit readiness, and regulatory compliance.

### Transaction Matching in Personal Finance Context

When managing personal finance records, matching typically occurs between:
- Imported bank transactions (from personal & joint checking accounts, credit cards)
- Internal ledger entries (manually entered or auto-generated for transfers and payments)

Key matching scenarios:
- Transfers between personal and joint checking accounts
- Credit card payments made from checking accounts

### Incorrect matching

| Scenario                               | What Can Go Wrong                                                           | Result                                                                        |
| -------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **Mismatched transfer**                | A transfer from Joint to Personal is matched to an unrelated deposit        | Misrepresents income, confuses budgeting, undermines trust in shared finances |
| **Double-matched credit card payment** | Payment is matched both to an expense and to a liability payment            | Double counting: overstates expenses or understates available balance         |
| **One-side-only match**                | Credit card payment shows in checking but not matched to credit card ledger | Liability not reduced; credit card balance appears inflated                   |
| **Wrong account match**                | Transfer to savings matched to investment income                            | Misclassifies transaction, corrupts category reports                          |
| **Partial match**                      | \$1,500 payment matched to \$500 expense                                    | Remaining \$1,000 unaccounted for; reconciliation fails                       |

#### Consequences
- Inaccurate net worth or cash flow reports
- Budgeting errors (e.g., showing more discretionary income than you have)
- Misleading spending insights (e.g., "you spent $4,000 on groceries")
- Duplicate or missing entries confuse audits, taxes, and personal financial planning

#### Best practices
- Match both sides of transfers and payments (from + to)
- Use amount, date, and memo as match criteria
- Avoid categorizing matched transfers as income or expenses
- Reconcile regularly and flag one-sided or unmatched entries


## 3. Architecture & Schema

```
┌──────────────────────────────────────────────────────────┐
│                      CLI Layer                            │
│  (ingest, list-imports, categorize commands)             │
└─────────────────────────┬────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│            High-Level Orchestration Services              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │IngestService│  │CategorizeService│ │MatchingService │ │
│  └──────┬──────┘  └───────┬───────┘  └───────┬─────────┘ │
│         │                 │                   │           │
│  Coordinates:       Coordinates:        Coordinates:      │
│  - CSV/QIF parsing  - Cache lookup      - Transaction    │
│  - File archiving   - Rule matching       matching       │
│  - Idempotency      - Split updates                      │
└─────────┬─────────────────┬───────────────────┬──────────┘
          │                 │                   │
┌─────────▼─────────────────▼───────────────────▼──────────┐
│              Mid-Level Business Services                  │
│  TransactionService, AccountService, BookService          │
└─────────────────────────┬────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│                    Data Access Layer                      │
│  (Book, Account, Transaction, Split, ImportFile,         │
│   CategoryCache CRUD operations)                          │
└──────────────────────────────────────────────────────────┘
```

![](docs/img/schema-diagram.png)

## 4. System design goals

- The application stores data in a relational datamodel identified by a DB URL provided as an argument.
- Implemented with a service based architecture supporting web and CLI user interfaces.
- Ability to scale to hundreds of thousands of transactions per month.
- Support a basic set of accounting reports (balances, expenses, periodic trends) as well as adhoc queries.

## 5. Usage

### Command line usage

```
Usage: accounts-cli [-h] [--db-url DB_URL] {init-db,init-book,add-account,list-accounts,book-transaction} ...

Accounts CLI

positional arguments:
  {init-db,init-book,add-account,list-accounts,book-transaction,delete-transaction}
    init-db             Initialize the DB schema (drop/create tables)
    init-book           Create a new Book if it doesn't exist. (Default: 'personal')
    add-account         Add an account to a given book
    list-accounts       List all accounts for a given book
    book-transaction    Create a transaction w/ two splits (debit & credit)
    delete-transaction  Delete a transaction by ID

options:
  -h, --help            show this help message and exit
  --version             Show version.
  --db-url, -u DB_URL   Database URL (default: sqlite:///db/accounting-system.db)
```

### Web usage

@todo

## A. License

```
Copyright 2025 Edward Bridges

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
