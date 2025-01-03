import pytest
import json

from financial_accounts.db.models import Base
from financial_accounts.business.account_service import AccountService
from financial_accounts.business.book_service import BookService
from financial_accounts.business.account_service import AccountService
from financial_accounts.business.management_service import ManagementService


@pytest.fixture
def db_url():
    # Use an in-memory SQLite database for testing
    return "sqlite:///:memory:"


def test_export_account_hierarchy_as_json(db_url):
    # Initialize the management service
    mgmt_service = ManagementService().init_with_url(db_url)
    mgmt_service.reset_database()

    # Create a sample account hierarchy
    with BookService(db_url) as book_service:
        book = book_service.create_new_book("Test Book")
        with AccountService(db_url) as account_service:
            root_account = account_service.add_account(
                book_name=book.name,
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
            child_account = account_service.add_account(
                book_name=book.name,
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

    # Export the account hierarchy as JSON
    json_output = mgmt_service.export_account_hierarchy_as_json()

    # Verify the JSON output
    hierarchy = json.loads(json_output)
    assert len(hierarchy) == 1
    assert hierarchy[0]["name"] == "Root Account"
    assert len(hierarchy[0]["children"]) == 1
    assert hierarchy[0]["children"][0]["name"] == "Child Account"
    test_book_name = 'test_book_name'
    with BookService(db_url) as service:
        Base.metadata.create_all(service.engine)
        service.create_new_book(test_book_name)
        mgmt_service = ManagementService().init_with_engine(service.engine)
        mgmt_service.reset_database()
        assert not service.get_book_by_name(test_book_name)
