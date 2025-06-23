# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Dependencies and Environment
- **Package manager**: Poetry (`poetry install` to install dependencies)
- **Python version**: 3.13+ (specified in pyproject.toml)
- **Database**: SQLite (default) at `db/accounting-system.db`

### Testing
- **Run tests**: `poetry run pytest`
- **Run tests with coverage**: `poetry run pytest --cov=financial_accounts --cov-report=term`
- **Test configuration**: Tests are configured in pyproject.toml with coverage exclusions for CLI, version, and __init__ files

### Code Quality
- **Linting**: Uses flake8 (configured in pyproject.toml)
- **Formatting**: Uses black with 100-character line length
- **Run linting**: `poetry run flake8`
- **Run formatting**: `poetry run black .`

### CLI Application
- **Main CLI**: `poetry run accounts-cli` or `python financial_accounts/cli.py`
- **Default database**: `sqlite:///db/accounting-system.db`
- **Default book**: "personal"

### Key CLI Commands
```bash
# Initialize database schema
accounts-cli init-db --confirm

# Create a book
accounts-cli init-book -b personal

# Add an account
accounts-cli add-account -b personal -t ASSET -c CHECKING -n "Checking Account" -f "Assets:Checking Account"

# List accounts
accounts-cli list-accounts -b personal

# Book a transaction
accounts-cli book-transaction -b personal -D 2024-01-01 -T "Rent Payment" -x "Rent Expense" -y "Checking Account" -a 1500.00

# Delete a transaction
accounts-cli delete-transaction -T <transaction-id>
```

## Architecture Overview

### Service-Based Architecture
The application follows a layered service-based architecture:

1. **CLI Layer** (`financial_accounts/cli.py`): Command-line interface and argument parsing
2. **Business Services** (`financial_accounts/business/`): Core business logic
3. **Data Access Layer** (`financial_accounts/db/`): Database models and data access
4. **Utilities** (`financial_accounts/util/`): Helper functions (QIF parsing, etc.)

### Core Business Services
- **BaseService**: Context manager pattern for database sessions
- **BookService**: Manages accounting books (collections of accounts)
- **AccountService**: Handles account creation, hierarchy, and management
- **TransactionService**: Manages double-entry transactions and splits
- **ManagementService**: Database initialization and schema management
- **MatchingService**: Transaction matching and reconciliation logic

### Database Schema
- **Double-entry accounting system** with Books, Accounts, Transactions, and Splits
- **Hierarchical accounts** with parent-child relationships
- **Account types**: ASSET, LIABILITY, INCOME, EXPENSE, EQUITY, ROOT
- **Transaction matching** with configurable rules
- **UUID support** for future extensibility (currently using integer IDs)

### Key Design Patterns
- **Context managers**: All services use `with` statement for session management
- **Shared sessions**: Services can share database sessions within a context
- **Foreign key constraints**: Maintains referential integrity
- **Cascade operations**: Proper cleanup of related records

### Transaction Processing
- Each transaction must have exactly 2 splits (debit and credit)
- Amounts: positive for debits, negative for credits
- Match status tracking: 'n' (not matched), 'm' (matched)
- Reconciliation states: 'n' (not reconciled), 'c' (cleared), 'r' (reconciled)

### Testing Structure
- Tests mirror the source structure in `tests/` directory
- Fixtures defined in `tests/conftest.py`
- Integration tests for matching service
- Coverage excludes CLI and version modules

### Configuration Files
- **pyproject.toml**: Poetry configuration, test settings, code quality tools
- **matching-config.json**: Transaction matching rules configuration
- **matching-patterns.md**: Documentation for matching patterns