"""
Fixtures for validation tests.

Provides database setup, sample data paths, and common test utilities
for integration and validation tests.
"""

import os
import pytest
import tempfile

from ledger.business.book_service import BookService
from ledger.business.book_context import BookContext
from ledger.business.management_service import ManagementService


# Paths relative to project root
VALIDATION_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'validation')
SAMPLE_DATA_DIR = os.path.join(VALIDATION_DIR, 'data-samples')
MATCHING_CONFIG = os.path.join(VALIDATION_DIR, 'matching-config.json')

# Required accounts for validation tests
REQUIRED_ACCOUNTS = {
    "Assets:Checking Accounts:checking-chase-personal-1381": {"type": "ASSET", "code": "1381"},
    "Assets:Checking Accounts:checking-chase-personal-1605": {"type": "ASSET", "code": "1605"},
    "Liabilities:Credit Cards:creditcard-chase-personal-6063": {
        "type": "LIABILITY",
        "code": "6063",
    },
}


@pytest.fixture(scope="module")
def validation_db_path():
    """Create temporary database file for validation tests."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup after all tests in module complete
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture(scope="module")
def validation_db_url(validation_db_path):
    """SQLite URL for the validation database."""
    return f"sqlite:///{validation_db_path}"


@pytest.fixture(scope="module")
def validation_book_name():
    """Book name used for validation tests."""
    return "validation-test"


@pytest.fixture(scope="module")
def initialized_db(validation_db_url, validation_book_name):
    """
    Initialize database with schema and book.
    Returns the db_url for use in other fixtures.
    """
    # Initialize database schema
    with ManagementService().init_with_url(validation_db_url) as mgmt_service:
        mgmt_service.reset_database()

    # Create book
    with BookService().init_with_url(validation_db_url) as book_service:
        book_service.create_new_book(validation_book_name)

    return validation_db_url


@pytest.fixture(scope="module")
def initialized_db_with_accounts(initialized_db, validation_book_name):
    """
    Initialize database with schema, book, and required accounts.
    Returns the db_url for use in other fixtures.
    """
    # Create required accounts
    with BookContext(validation_book_name, initialized_db) as ctx:
        for full_name, details in REQUIRED_ACCOUNTS.items():
            ctx.accounts.add_account(
                parent_code=None,
                parent_name=None,
                acct_name=full_name.split(":")[-1],
                full_name=full_name,
                acct_code=details["code"],
                acct_type=details["type"],
                description=f"Validation test account {details['code']}",
                hidden=False,
                placeholder=False,
            )

    return initialized_db


@pytest.fixture
def sample_data_dir():
    """Path to sample QIF data files."""
    return SAMPLE_DATA_DIR


@pytest.fixture
def matching_config():
    """Path to matching configuration JSON file."""
    return MATCHING_CONFIG


@pytest.fixture
def sample_qif_files():
    """List of basic sample QIF files (small test data)."""
    return ["sample-1381.qif", "sample-1605.qif", "sample-6063.qif"]


@pytest.fixture
def comprehensive_qif_files():
    """List of comprehensive QIF files (large test data)."""
    return ["samples-1381.qif", "samples-1605.qif", "samples-6063.qif"]


@pytest.fixture
def book_context(initialized_db_with_accounts, validation_book_name):
    """
    Provide a BookContext for tests that need database access.
    Creates a new context for each test.
    """
    with BookContext(validation_book_name, initialized_db_with_accounts) as ctx:
        yield ctx
