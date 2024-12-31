import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from accounts.db.data_access import DAL, check_for_circular_path
from accounts.db.models import Book, Account, Transactions, Split

@pytest.fixture
def mock_session():
    return MagicMock(spec=Session)

@pytest.fixture
def dal(mock_session):
    return DAL(mock_session)

def test_create_book(dal, mock_session):
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    book = dal.create_book("Test Book")
    assert book.name == "Test Book"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

def test_get_book(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Book(id="1", name="Test Book")

    book = dal.get_book("1")
    assert book.name == "Test Book"

def test_list_books(dal, mock_session):
    mock_session.query().all.return_value = [Book(id="1", name="Test Book")]

    books = dal.list_books()
    assert len(books) == 1
    assert books[0].name == "Test Book"

def test_update_book_name(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Book(id="1", name="Old Name")
    mock_session.commit = MagicMock()

    updated_book = dal.update_book_name("1", "New Name")
    assert updated_book.name == "New Name"
    mock_session.commit.assert_called_once()

def test_delete_book(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Book(id="1", name="Test Book")
    mock_session.delete = MagicMock()
    mock_session.commit = MagicMock()

    result = dal.delete_book("1")
    assert result is True
    mock_session.delete.assert_called_once()
    mock_session.commit.assert_called_once()

def test_check_for_circular_path(mock_session):
    mock_session.query().filter().first.side_effect = [(None,), ("1",), (None,)]
    result = check_for_circular_path(mock_session, "1", "2")
    assert result is False

def test_create_account(dal, mock_session):
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    account = dal.create_account(
        book_id="1",
        acct_type="ASSET",
        code="001",
        name="Test Account"
    )
    assert account.name == "Test Account"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

def test_get_account(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Account(id="1", name="Test Account")

    account = dal.get_account("1")
    assert account.name == "Test Account"

def test_list_accounts_for_book(dal, mock_session):
    mock_session.query().filter_by().all.return_value = [Account(id="1", name="Test Account")]

    accounts = dal.list_accounts_for_book("1")
    assert len(accounts) == 1
    assert accounts[0].name == "Test Account"

# Add similar tests for transactions and splits
