import os
import json
import tempfile
import csv
import pytest
from datetime import datetime
from decimal import Decimal
from financial_accounts.db.models import Base, Transaction, Split
from financial_accounts.business.transaction_service import TransactionService
from financial_accounts.business.matching_service import MatchingService, MatchingRules

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
    '''
    csv_text = f"""row_id,account,date,description,amount,corresponding_account
1,{A_1381},2022-09-26,CHASE CREDIT CRD AUTOPAY PPD ID: 4760039224,-620.00,{A_6063}
2,{A_1381},2022-07-18,Online Transfer to CHK ...1605 transaction#: 14782136085 07/18,-500.00,{A_1605}
3,{A_1605},2022-06-30,Online Transfer from CHK ...1381 transaction#: 18903209342,500.00,{A_1381}
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
    """Initialize test database and provide TransactionService and MatchingService."""
    # Initialize TransactionService with test database
    ts = TransactionService().init_with_url(TEST_DB_URL)
    ms = MatchingService(matching_rules, transaction_service=ts)

    # Create all tables in the test database
    Base.metadata.create_all(ts.engine)

    # Create a test Book and required Accounts
    with ts as ts_ctx:  # open the session context
        book = ts_ctx.data_access.create_book(name="Test Book")
        # Create accounts referenced in matching rules
        for name, code, acct_type in test_accounts:
            ts_ctx.data_access.create_account(
                book.id, code=code, name=name, full_name=name, acct_type=acct_type
            )
        yield ts_ctx, ms, book  # provide the service instances and book for tests
    # Teardown: drop all tables after the test module
    Base.metadata.drop_all(ts.engine)


@pytest.fixture
def transactions_to_import(services, setup_csv_file, import_csv_file):
    """Parse CSV and prepare transactions for import. Also insert initial ledger transactions for matching."""
    ts, ms, book = services

    # Insert initial ledger transactions (existing in DB) using
    # TransactionService to simulate user-recorded data
    # These will serve as potential match candidates.
    with open(setup_csv_file, newline='') as setupfile:
        reader = csv.DictReader(setupfile)
        for row in reader:
            ts.enter_transaction(
                book_name=book.name,
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

            # Find Account objects by name via TransactionService (or data_access)
            acct = ts.data_access.get_account_by_fullname_for_book(book.id, row["account"])
            corr_acct = ts.data_access.get_account_by_fullname_for_book(
                book.id, row["corresponding_account"]
            )

            # Create two splits for the transaction
            amount = Decimal(row["amount"])
            d = Split(transaction=txn, account_id=acct.id, amount=amount, account=acct)
            c = Split(transaction=txn, account_id=corr_acct.id, amount=-amount, account=corr_acct)
            txn.splits = [d, c]

            transactions_to_import.setdefault(acct, []).append(txn)
    return transactions_to_import


def test_import_transactions_matching_logic(
    services, transactions_to_import, transaction_match_mappings
):
    ts, ms, book = services

    # Execute import for each account in the prepared transactions
    for import_account, txn_list in transactions_to_import.items():
        ms.import_transactions(book.id, import_account, txn_list)

    # Fetch all transactions from the ledger after import
    all_txns = ts.get_all_transactions_for_book(book.id)

    for txn in all_txns:
        row_id = txn.memo
        expected_match = transaction_match_mappings[row_id]
        actual_match = txn.match_status

        assert actual_match == expected_match, f'Failed assertion: {txn} '
        f'expected {expected_match} but was {actual_match} for row_id: {txn.memo}'

    # # Separate transactions by description for easier checking
    # txn_by_desc = {tx.transaction_description: tx for tx in all_txns}

    # # **Verification:**

    # # 1. Matched transactions: they should *not* be duplicated in the ledger, and should be marked as matched.
    # #    - The transfer on 2023-01-15 (1381 vs 1605) and the autopay on 2023-04-04 (1381 vs 6063) exist from setup.
    # #    - They should remain single entries and have match_status 'm' after import (marked as matched).
    # transfer_desc = "Online Transfer from CHK ...1605"
    # autopay_desc = "CHASE CREDIT CRD AUTOPAY 2100 PPD ID: 123456"
    # assert transfer_desc in txn_by_desc, "Initial transfer transaction missing from ledger."
    # assert autopay_desc in txn_by_desc, "Initial autopay transaction missing from ledger."
    # transfer_txn = txn_by_desc[transfer_desc]
    # autopay_txn = txn_by_desc[autopay_desc]
    # assert (
    #     transfer_txn.match_status == 'm'
    # ), "Matched transfer transaction was not marked as matched."
    # assert autopay_txn.match_status == 'm', "Matched autopay transaction was not marked as matched."

    # # 2. Unmatched imported transactions: they should be inserted into the ledger with match_status 'n'.
    # #    (Examples: transactions with non-matching descriptions or date offsets, and completely new transactions.)
    # # Check an import with a description mismatch (duplicate transfer from 1605 side).
    # dup_transfer_desc = "Online Transfer to CHK ...1381"
    # assert dup_transfer_desc in txn_by_desc, "Unmatched transfer (1605->1381) not inserted."
    # assert (
    #     txn_by_desc[dup_transfer_desc].match_status == 'n'
    # ), "Unmatched transfer should remain not matched."
    # # Check an import with a date outside allowed offset (duplicate autopay outside date range).
    # late_autopay_desc = "AUTOMATIC PAYMENT - THANK YOU"
    # assert late_autopay_desc in txn_by_desc, "Unmatched autopay (date offset) not inserted."
    # assert (
    #     txn_by_desc[late_autopay_desc].match_status == 'n'
    # ), "Out-of-range autopay should remain not matched."
    # # Check a completely new transaction (no candidate at all, e.g., salary deposit).
    # salary_desc = "Salary Payment"
    # assert salary_desc in txn_by_desc, "New external transaction (Salary) not inserted."
    # assert txn_by_desc[salary_desc].match_status == 'n', "New transaction should be not matched."

    # # 3. No duplicate entries for matched transactions:
    # #    The originally recorded transactions should not be duplicated. We ensure that the count of transactions remains correct.
    # # Expected: initial 2 transactions + 4 unmatched imports = 6 total transactions in ledger.
    # assert len(all_txns) == 6, f"Ledger should contain 6 transactions (got {len(all_txns)})."
    # # Ensure the matched ones did not get inserted as new:
    # # (Their descriptions already checked to be present once. We confirm they appear only once by count of those descriptions.)
    # descriptions = [tx.transaction_description for tx in all_txns]
    # assert descriptions.count(transfer_desc) == 1, "Matched transfer was duplicated in ledger."
    # assert descriptions.count(autopay_desc) == 1, "Matched autopay was duplicated in ledger."

    # # 4. Matched logic correctness:
    # #    Ensure that matching considered both description patterns and date offsets.
    # #    (If any expected match was missed or a wrong match made, the above assertions would catch it.)
    # # For completeness, verify that the mismatched cases truly failed matching due to pattern or date:
    # # - The transfer from 1605 had a different description than ledger's, causing no match.
    # assert transfer_txn.transaction_date == date(2023, 1, 15)
    # dup_transfer_txn = txn_by_desc[dup_transfer_desc]
    # # Should be a separate transaction on a different date (e.g., 2023-01-16 as in CSV), confirming it didn't match the 1-day offset rule due to description mismatch.
    # assert dup_transfer_txn.transaction_date == date(2023, 1, 16)
    # # - The late autopay had correct description but 5-day difference, beyond the 3-day offset, hence no match.
    # late_autopay_txn = txn_by_desc[late_autopay_desc]
    # assert (
    #     abs((late_autopay_txn.transaction_date - autopay_txn.transaction_date).days) == 5
    # ), "Late autopay date difference is not 5 days as expected."
    # assert autopay_txn.match_status == 'm' and late_autopay_txn.match_status == 'n'
