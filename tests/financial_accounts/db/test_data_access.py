from datetime import date, datetime
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Session
from financial_accounts.db.data_access import DAL
from financial_accounts.db.models import Base, Book, Account, Transaction, Split


@pytest.fixture
def mock_session():
    return MagicMock(spec=Session)


@pytest.fixture
def dal(mock_session):
    return DAL(mock_session)


@pytest.fixture(scope='module')
def mem_session():
    # Create an in-memory SQLite database
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def mem_dal(mem_session):
    return DAL(mem_session)


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


# def test_check_for_circular_path(mock_session):
#     mock_session.query().filter().first.side_effect = [(None,), ("1",), (None,)]
#     result = check_for_circular_path(mock_session, "1", "2")
#     assert result is False


def test_create_account(dal, mock_session):
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    account = dal.create_account(
        book_id="1", acct_type="ASSET", code="001", name="Test Account", full_name="Test Account"
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


def test_create_transaction(dal, mock_session):
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    transaction = dal.create_transaction(
        book_id="1", transaction_date="2023-10-01", transaction_description="Test Transaction"
    )
    assert transaction.transaction_description == "Test Transaction"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_get_transaction(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Transaction(
        id="1", transaction_description="Test Transaction"
    )

    transaction = dal.get_transaction("1")
    assert transaction.transaction_description == "Test Transaction"


def test_list_transactions_for_book(dal, mock_session):
    mock_session.query().filter_by().all.return_value = [
        Transaction(id="1", transaction_description="Test Transaction")
    ]

    transactions = dal.list_transactions_for_book("1")
    assert len(transactions) == 1
    assert transactions[0].transaction_description == "Test Transaction"


def test_update_transaction(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Transaction(
        id="1", transaction_description="Old Description"
    )
    mock_session.commit = MagicMock()

    updated_transaction = dal.update_transaction("1", transaction_description="New Description")
    assert updated_transaction.transaction_description == "New Description"
    mock_session.commit.assert_called_once()


def test_delete_transaction(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Transaction(
        id="1", transaction_description="Test Transaction"
    )
    mock_session.delete = MagicMock()
    mock_session.commit = MagicMock()

    result = dal.delete_transaction("1")
    assert result is True
    mock_session.delete.assert_called_once()
    mock_session.commit.assert_called_once()


def test_create_split(dal, mock_session):
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()

    split = dal.create_split(transaction_id="1", account_id="1", amount=100.0, memo="Test Split")
    assert split.memo == "Test Split"
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


def test_list_splits_for_transaction(dal, mock_session):
    mock_session.query().filter_by().all.return_value = [Split(id="1", memo="Test Split")]

    splits = dal.list_splits_for_transaction("1")
    assert len(splits) == 1
    assert splits[0].memo == "Test Split"


def test_list_splits_for_account(dal, mock_session):
    mock_session.query().filter_by().all.return_value = [Split(id="1", memo="Test Split")]

    splits = dal.list_splits_for_account("1")
    assert len(splits) == 1
    assert splits[0].memo == "Test Split"


def test_update_split(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Split(id="1", memo="Old Memo")
    mock_session.commit = MagicMock()

    updated_split = dal.update_split("1", memo="New Memo")
    assert updated_split.memo == "New Memo"
    mock_session.commit.assert_called_once()


def d(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def test_query_for_unmatched_transactions_in_range(mem_dal):
    book = mem_dal.create_book("Test Book")

    account = mem_dal.create_account(
        book_id=book.id, acct_type="ASSET", code="001", name="Cash", full_name="Assets:Cash"
    )

    txn1 = mem_dal.create_transaction(
        book_id=book.id, transaction_date=d("2023-10-01"), transaction_description="Transaction 1"
    )
    txn2 = mem_dal.create_transaction(
        book_id=book.id, transaction_date=d("2023-10-03"), transaction_description="Transaction 2"
    )
    txn3 = mem_dal.create_transaction(
        book_id=book.id, transaction_date=d("2023-10-05"), transaction_description="Transaction 3"
    )
    txn4 = mem_dal.create_transaction(
        book_id=book.id, transaction_date=d("2023-10-10"), transaction_description="Transaction 4"
    )

    mem_dal.create_split(
        transaction_id=txn1.id, account_id=account.id, amount=100.0, reconcile_state='n'
    )
    mem_dal.create_split(
        transaction_id=txn2.id, account_id=account.id, amount=150.0, reconcile_state='c'
    )
    mem_dal.create_split(
        transaction_id=txn3.id, account_id=account.id, amount=200.0, reconcile_state='c'
    )
    mem_dal.create_split(
        transaction_id=txn4.id, account_id=account.id, amount=300.0, reconcile_state='r'
    )

    # Test date range filtering
    transactions = mem_dal.query_for_unmatched_transactions_in_range(
        book_id=book.id,
        start_date=date(2023, 10, 1),
        end_date=date(2023, 10, 5),
        accounts_to_match_for=[account.name],
    )
    # transactions = mem_dal.get_transactions_in_range(date(2023, 10, 1), date(2023, 10, 5))
    assert len(transactions) == 3
    assert transactions[0].transaction_description == "Transaction 1"
    assert transactions[1].transaction_description == "Transaction 2"
    assert transactions[2].transaction_description == "Transaction 3"

    # Test date range with reconciliation status filtering
    transactions_with_recon = mem_dal.query_for_unmatched_transactions_in_range(
        book_id=book.id,
        start_date=date(2023, 10, 1),
        end_date=date(2023, 10, 10),
        accounts_to_match_for=[account.name],
        reconciliation_status='c',
    )

    assert len(transactions_with_recon) == 2
    assert transactions_with_recon[0].transaction_description == "Transaction 2"
    assert transactions_with_recon[1].transaction_description == "Transaction 3"


def test_delete_split(dal, mock_session):
    mock_session.query().filter_by().one_or_none.return_value = Split(id="1", memo="Test Split")
    mock_session.delete = MagicMock()
    mock_session.commit = MagicMock()

    result = dal.delete_split("1")
    assert result is True
    mock_session.delete.assert_called_once()
    mock_session.commit.assert_called_once()
