# test_management_service.py
"""Tests for ManagementService."""
import pytest
import json
import tempfile
import os

from ledger.db.models import Base
from ledger.business.book_context import BookContext
from ledger.business.book_service import BookService
from ledger.business.management_service import ManagementService


@pytest.fixture
def db_url():
    """
    Create a temporary SQLite database file and return its URL.
    The file is removed once the test completes.
    """
    # mkstemp() returns a tuple of (file_descriptor, path)
    fd, path = tempfile.mkstemp(suffix=".db")
    # We don't need to keep the file descriptor open
    os.close(fd)

    url = f"sqlite:///{path}?mode=rw&uri=true"

    try:
        yield url
    finally:
        # Remove the file after the test is done
        os.remove(path)


def test_export_account_hierarchy_as_json(db_url):
    # First, initialize database and create book
    with ManagementService().init_with_url(db_url) as management_service:
        management_service.reset_database()

    with BookService().init_with_url(db_url) as book_service:
        book_service.create_new_book("Test Book")

    # Use BookContext for account operations
    with BookContext("Test Book", db_url) as ctx:
        root_account = ctx.accounts.add_account(
            parent_code=None,
            parent_name=None,
            acct_name="Root Account",
            full_name="Root Account",
            acct_code="000",
            acct_type="ROOT",
            description="Root account",
            hidden=False,
            placeholder=False,
        )
        print(f'Created root account: {root_account.id}')

        child_account = ctx.accounts.add_account(
            parent_code=root_account.code,
            parent_name=root_account.name,
            acct_name="Child Account",
            full_name="Root Account:Child Account",
            acct_code="001",
            acct_type="ASSET",
            description="Child account",
            hidden=False,
            placeholder=False,
        )
        print(f'Created child account: {child_account.id}')

    # Export hierarchy using ManagementService
    with ManagementService().init_with_url(db_url) as management_service:
        json_output = management_service.export_account_hierarchy_as_json()

    # Verify the JSON output
    hierarchy = json.loads(json_output)
    assert len(hierarchy) == 1
    assert hierarchy[0]["name"] == "Root Account"
    assert len(hierarchy[0]["children"]) == 1
    assert hierarchy[0]["children"][0]["name"] == "Child Account"


def test_reset_database(db_url):
    test_book_name = 'test_book_name'
    with (
        ManagementService().init_with_url(db_url) as management_service,
        BookService().init_with_url(db_url) as book_service,
    ):

        Base.metadata.create_all(book_service.engine)
        book_service.create_new_book(test_book_name)
        management_service.reset_database()
        assert not book_service.get_book_by_name(test_book_name)
