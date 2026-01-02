# test_matching_service_integration.py
"""Integration tests for matching service."""
import os
import json
import tempfile
import csv
import pytest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ledger.db.models import Base, Transaction, Split
from ledger.db.data_access import DAL
from ledger.business.transaction_service import TransactionService
from ledger.business.matching_service import MatchingService, MatchingRules

TEST_DB_URL = "sqlite:///:memory:"

A_1381 = 'Asset:Checking Accounts:checking-chase-personal-1381'
A_1605 = 'Asset:Checking Accounts:checking-chase-personal-1605'
A_6063 = 'Liability:Credit Cards:creditcard-chase-personal-6063'
A_1111 = 'Income:Salary-1111'


@pytest.fixture(scope="module")
def test_accounts() -> list[tuple]:
    # returns a 3-tuple of full acct name, acct code (last 4 chars),
    # and acct type (first part of acct name)
    return [
        (A_1111, int(A_1111.split('-')[-1]), A_1111.split(':')[0].upper()),
        (A_1381, int(A_1381.split('-')[-1]), A_1381.split(':')[0].upper()),
        (A_1605, int(A_1605.split('-')[-1]), A_1605.split(':')[0].upper()),
        (A_6063, int(A_6063.split('-')[-1]), A_6063.split(':')[0].upper()),
    ]


@pytest.fixture(scope="module")
def setup_transactions() -> str:
    '''
    These represent transactions that would be pre-existing in the database,
    and would be targets for a match.
    The `row_id` column is for testing purposes to be able to link to a
    transaction that is later imported as being the match for test purposes.
    
    With the corrected enter_transaction() logic:
    - from_acct (account column) = credit account (money leaves, gets -amount)
    - to_acct (corresponding_account column) = debit account (money arrives, gets +amount)
    - amount should be positive (the split signs are determined by from/to semantics)
    '''
    csv_text = f"""row_id,account,date,description,amount,corresponding_account
1,{A_1381},2022-09-26,CHASE CREDIT CRD AUTOPAY PPD ID: 4760039224,620.00,{A_6063}
2,{A_1381},2022-07-18,Online Transfer to CHK ...1605 transaction#: 14782136085 07/18,500.00,{A_1605}
3,{A_1381},2022-06-30,Online Transfer from CHK ...1381 transaction#: 18903209342,500.00,{A_1605}
"""
    return csv_text


@pytest.fixture(scope="module")
def import_transactions() -> str:
    # CSV block as a string
    csv_text = f"""row_id,account,date,description,amount,corresponding_account
A,{A_1605},2022-07-18,Online Transfer from CHK ...1381 transaction#: 14782136085,500.00,{A_1381}
B,{A_6063},2022-09-27,AUTOMATIC PAYMENT - THANK,620.00,{A_1381}
C,{A_1381},2022-10-01,Salary deposit,10000,{A_1111}
"""
    return csv_text


@pytest.fixture(scope="module")
def transaction_match_mappings() -> dict:
    '''
    This provides a mapping to indicate for test transactions are matched or not. The
    key corresponds to the value of `row_id` in the test data, and is stored in the `memo`
    field of the transaction.
    '''
    mapping = {}
    mapping['A'] = 'm'
    mapping['B'] = 'm'
    mapping['C'] = 'n'
    mapping['1'] = 'm'
    mapping['2'] = 'm'
    mapping['3'] = 'n'
    return mapping


@pytest.fixture(scope="module")
def rules_data() -> dict:

    json_data = {
        "matching_rules": {
            A_1381: {
                A_6063: {
                    "date_offset": 1,
                    "description_patterns": [
                        "^AUTOMATIC PAYMENT - THANK(?: YOU)?$",
                        "^Payment Thank You\\s?-\\s?(Web|Mobile)$",
                        "CHASE CREDIT CRD AUTOPAY PPD ID: \\d+",
                    ],
                },
                A_1605: {
                    "date_offset": 1,
                    "description_patterns": [
                        "^Online Transfer\\s+from\\s+CHK\\s*\\.\\.\\.138\\d?(?:\\s+transaction#:\\s*\\S*)?$",
                        "^Online Transfer\\s+to\\s+CHK\\s*\\.\\.\\.138\\d?(?:\\s+transaction#:\\s*\\S+\\s+\\S+)?(?:\\s+t)?$",
                    ],
                },
            },
            A_6063: {
                A_1381: {
                    "date_offset": 3,
                    "description_patterns": [
                        "^CHASE CREDIT CRD AUTOPAY\\s*(?:\\d+)?\\s*PPD ID:\\s*\\d+$",
                        "^Payment to Chase card ending in \\d{4}\\s+\\d{2}/\\d{2}$",
                        "^AUTOMATIC\\s+PAYMENT\\s+-\\s+THANK",
                    ],
                }
            },
            A_1605: {
                A_1381: {
                    "date_offset": 2,
                    "description_patterns": [
                        "^Online Transfer\\s+from\\s+CHK\\s*\\.\\.\\.1605(?:\\s+transaction#:\\s*\\d{2,})?$",
                        "^Online Transfer\\s+to\\s+CHK\\s*\\.\\.\\.1605(?:\\s+transaction#:\\s*(?:\\d{2,}(?:\\s+\\d{2}/\\d{2})?|\\d{2}/\\d{2}))?(?:\\s+t)?$",
                    ],
                }
            },
        }
    }

    return json.dumps(json_data)


@pytest.fixture(scope="module")
def config_file(rules_data):
    with tempfile.NamedTemporaryFile(
        delete=False, mode='w', newline='', encoding='utf-8'
    ) as temp_file:
        temp_file.write(rules_data)
        temp_file_path = temp_file.name

    yield temp_file_path

    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)


@pytest.fixture(scope="module")
def setup_csv_file(setup_transactions):
    with tempfile.NamedTemporaryFile(
        delete=False, mode='w', newline='', encoding='utf-8'
    ) as temp_file:
        temp_file.write(setup_transactions)
        temp_file_path = temp_file.name

    yield temp_file_path

    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)


@pytest.fixture(scope="module")
def import_csv_file(import_transactions):
    with tempfile.NamedTemporaryFile(
        delete=False, mode='w', newline='', encoding='utf-8'
    ) as temp_file:
        temp_file.write(import_transactions)
        temp_file_path = temp_file.name

    yield temp_file_path

    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)


@pytest.fixture(scope="module")
def matching_rules(config_file):
    """Load matching rules from JSON file."""
    return MatchingRules(config_file)


@pytest.fixture(scope="module")
def services(matching_rules, test_accounts):
    """Initialize test database and provide DAL, TransactionService and MatchingService."""
    # Create engine and session
    engine = create_engine(TEST_DB_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    
    # Create all tables in the test database
    Base.metadata.create_all(engine)
    
    # Create session and DAL
    session = SessionLocal()
    dal = DAL(session=session)
    
    # Create a test Book and required Accounts
    book = dal.create_book(name="Test Book")
    
    # Create accounts referenced in matching rules
    for name, code, acct_type in test_accounts:
        dal.create_account(
            book.id, code=code, name=name, full_name=name, acct_type=acct_type
        )
    
    session.commit()
    
    # Create TransactionService with DAL and book
    ts = TransactionService(dal, book)
    ms = MatchingService(matching_rules)
    
    yield ts, ms, book, dal
    
    # Teardown: close session and drop all tables
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def transactions_to_import(services, setup_csv_file, import_csv_file):
    """Parse CSV and prepare transactions for import. Also insert initial ledger transactions for matching."""
    ts, ms, book, dal = services

    # Insert initial ledger transactions (existing in DB) using
    # TransactionService to simulate user-recorded data
    # These will serve as potential match candidates.
    with open(setup_csv_file, newline='') as setupfile:
        reader = csv.DictReader(setupfile)
        for row in reader:
            ts.enter_transaction(
                txn_date=row["date"],
                txn_desc=row["description"],
                to_acct=row["corresponding_account"],
                from_acct=row["account"],
                amount=row["amount"],
                memo=row["row_id"],
            )

    # At this point, the ledger has some transactions (with match_status 'n' by default).

    # Parse the CSV file to get transactions to import
    transactions_to_import = {}  # dict to group transactions by account
    with open(import_csv_file, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Create Transaction object (not yet added to DB)
            txn = Transaction(
                book_id=book.id,
                transaction_date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
                transaction_description=row["description"],
                memo=row["row_id"],
                match_status="n",
            )

            # Find Account objects by name via DAL
            acct = dal.get_account_by_fullname_for_book(book.id, row["account"])
            corr_acct = dal.get_account_by_fullname_for_book(
                book.id, row["corresponding_account"]
            )

            amount = Decimal(row["amount"])
            d = Split(account_id=acct.id, amount=amount)
            c = Split(account_id=corr_acct.id, amount=-amount)
            # Set account directly via __dict__ to avoid SQLAlchemy's relationship machinery,
            # which would warn about adding splits to a session-managed Account.splits collection.
            d.__dict__["account"] = acct
            c.__dict__["account"] = corr_acct
            txn.splits = [d, c]

            transactions_to_import.setdefault(acct, []).append(txn)
    return transactions_to_import

@pytest.mark.filterwarnings("ignore::ResourceWarning")
def test_import_transactions_matching_logic(
    services, transactions_to_import, transaction_match_mappings
):
    ts, ms, book, dal = services

    # Execute import for each account in the prepared transactions
    for import_account, txn_list in transactions_to_import.items():
        # Get matchable accounts and query candidates
        matchable_accounts = ms.get_matchable_accounts(import_account)
        
        if matchable_accounts and txn_list:
            start, end = ms.compute_candidate_date_range(txn_list)
            candidates = ts.query_unmatched(start, end, list(matchable_accounts))
        else:
            candidates = []
        
        # Process each transaction through match_transactions generator
        for action, txn in ms.match_transactions(import_account, txn_list, candidates):
            if action == 'match':
                ts.mark_matched(txn)
            else:  # action == 'import'
                ts.insert(txn)

    # Fetch all transactions from the ledger after import
    all_txns = ts.get_all()

    for txn in all_txns:
        row_id = txn.memo
        expected_match = transaction_match_mappings[row_id]
        actual_match = txn.match_status

        assert actual_match == expected_match, (
            f'Failed assertion: {txn} '
            f'expected {expected_match} but was {actual_match} for row_id: {txn.memo}'
        )
