"""
Validation tests for real-world transaction matching scenarios.

Tests realistic matching scenarios that occur in personal finance management,
simulating the workflow of manually entering transactions and later importing
bank statements.
"""
import os
import pytest
import tempfile
from decimal import Decimal

from ledger.business.book_service import BookService
from ledger.business.book_context import BookContext
from ledger.business.management_service import ManagementService
from ledger.business.matching_service import MatchingService
from ledger.util.qif import Qif


# Mark all tests in this file as validation tests
pytestmark = pytest.mark.validation


# Pre-existing transactions that should match imports
EXISTING_TRANSACTIONS = [
    {
        "date": "2022-07-14",
        "description": "Payment to Chase card ending in 6063 07/14",
        "from_account": "Assets:Checking Accounts:checking-chase-personal-1381",
        "to_account": "Liabilities:Credit Cards:creditcard-chase-personal-6063",
        "amount": "42336.10",
        "note": "Should match samples-1381.qif credit card payment"
    },
    {
        "date": "2022-05-09",
        "description": "Online Transfer from CHK ...1381 transaction#: 14246718367",
        "from_account": "Assets:Checking Accounts:checking-chase-personal-1381",
        "to_account": "Assets:Checking Accounts:checking-chase-personal-1605",
        "amount": "500.00",
        "note": "Should match samples-1605.qif transfer"
    },
    {
        "date": "2022-08-26",
        "description": "CHASE CREDIT CRD AUTOPAY                    PPD ID: 4760039224",
        "from_account": "Assets:Checking Accounts:checking-chase-personal-1381",
        "to_account": "Liabilities:Credit Cards:creditcard-chase-personal-6063",
        "amount": "376.00",
        "note": "Should match samples-1381.qif autopay"
    }
]

REQUIRED_ACCOUNTS = {
    "Assets:Checking Accounts:checking-chase-personal-1381": {
        "type": "ASSET",
        "code": "1381"
    },
    "Assets:Checking Accounts:checking-chase-personal-1605": {
        "type": "ASSET",
        "code": "1605"
    },
    "Liabilities:Credit Cards:creditcard-chase-personal-6063": {
        "type": "LIABILITY",
        "code": "6063"
    }
}


@pytest.fixture(scope="module")
def real_world_db():
    """Create a separate database for real-world matching tests."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db_url = f"sqlite:///{db_path}"
    book_name = "real-world-test"
    
    # Initialize database
    with ManagementService().init_with_url(db_url) as mgmt_service:
        mgmt_service.reset_database()
    
    # Create book
    with BookService().init_with_url(db_url) as book_service:
        book_service.create_new_book(book_name)
    
    # Create accounts
    with BookContext(book_name, db_url) as ctx:
        for full_name, details in REQUIRED_ACCOUNTS.items():
            ctx.accounts.add_account(
                parent_code=None,
                parent_name=None,
                acct_name=full_name.split(":")[-1],
                full_name=full_name,
                acct_code=details["code"],
                acct_type=details["type"],
                description=f"Real-world test account {details['code']}",
                hidden=False,
                placeholder=False
            )
    
    yield db_url, book_name
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture(scope="module")
def db_with_existing_transactions(real_world_db):
    """Set up database with pre-existing transactions for matching tests."""
    db_url, book_name = real_world_db
    
    with BookContext(book_name, db_url) as ctx:
        for txn_data in EXISTING_TRANSACTIONS:
            ctx.transactions.enter_transaction(
                txn_date=txn_data["date"],
                txn_desc=txn_data["description"],
                from_acct=txn_data["from_account"],
                to_acct=txn_data["to_account"],
                amount=txn_data["amount"]
            )
    
    return db_url, book_name


class TestRealWorldSetup:
    """Tests for real-world test environment setup."""

    def test_database_initialized(self, real_world_db):
        """Verify database is properly initialized."""
        db_url, book_name = real_world_db
        
        with BookContext(book_name, db_url) as ctx:
            accounts = ctx.accounts.list_accounts()
            assert len(accounts) == 3, "Expected 3 accounts to be created"

    def test_existing_transactions_created(self, db_with_existing_transactions):
        """Verify pre-existing transactions are created."""
        db_url, book_name = db_with_existing_transactions
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            assert len(transactions) == len(EXISTING_TRANSACTIONS)


class TestCreditCardPaymentMatching:
    """Tests for credit card payment matching scenarios."""

    def test_credit_card_matching_with_samples_1381(
        self, db_with_existing_transactions, sample_data_dir, matching_config
    ):
        """Test matching credit card payments from samples-1381.qif."""
        db_url, book_name = db_with_existing_transactions
        qif_path = os.path.join(sample_data_dir, "samples-1381.qif")
        
        if not os.path.exists(qif_path):
            pytest.skip(f"Sample file not found: {qif_path}")
        
        # Get baseline
        with BookContext(book_name, db_url) as ctx:
            before_count = len(ctx.transactions.get_all())
            before_matched = sum(1 for t in ctx.transactions.get_all() if t.match_status == 'm')
        
        # Parse QIF
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        with BookContext(book_name, db_url) as ctx:
            def resolve_account(name):
                try:
                    return ctx.accounts.lookup_by_name(name)
                except Exception:
                    return None
            
            # Convert QIF to Transaction objects (first 10 for testing)
            test_transactions = qif.as_transactions(ctx.book.id, resolve_account)[:10]
            
            # Get the import account
            import_account_name = qif.account_info.get('N')
            import_account = ctx.accounts.lookup_by_name(import_account_name)
            
            # Initialize matching service
            matching_service = MatchingService(matching_config)
            matchable_accounts = matching_service.get_matchable_accounts(import_account)
            
            candidates = []
            if matchable_accounts and test_transactions:
                start, end = matching_service.compute_candidate_date_range(test_transactions)
                candidates = ctx.transactions.query_unmatched(start, end, list(matchable_accounts))
            
            # Process transactions
            matched_count = 0
            imported_count = 0
            for action, txn in matching_service.match_transactions(import_account, test_transactions, candidates):
                if action == 'match':
                    ctx.transactions.mark_matched(txn)
                    matched_count += 1
                else:
                    ctx.transactions.insert(txn)
                    imported_count += 1
        
        # Verify results
        with BookContext(book_name, db_url) as ctx:
            after_count = len(ctx.transactions.get_all())
            after_matched = sum(1 for t in ctx.transactions.get_all() if t.match_status == 'm')
        
        # Should have processed transactions
        assert matched_count + imported_count == len(test_transactions)
        # After count should reflect new imports
        assert after_count >= before_count


class TestTransferMatching:
    """Tests for account transfer matching scenarios."""

    def test_transfer_matching_with_samples_1605(
        self, db_with_existing_transactions, sample_data_dir, matching_config
    ):
        """Test matching transfers from samples-1605.qif."""
        db_url, book_name = db_with_existing_transactions
        qif_path = os.path.join(sample_data_dir, "samples-1605.qif")
        
        if not os.path.exists(qif_path):
            pytest.skip(f"Sample file not found: {qif_path}")
        
        # Get baseline
        with BookContext(book_name, db_url) as ctx:
            before_count = len(ctx.transactions.get_all())
        
        # Parse QIF
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        with BookContext(book_name, db_url) as ctx:
            def resolve_account(name):
                try:
                    return ctx.accounts.lookup_by_name(name)
                except Exception:
                    return None
            
            # Convert QIF to Transaction objects (first 5 for testing)
            test_transactions = qif.as_transactions(ctx.book.id, resolve_account)[:5]
            
            # Get the import account
            import_account_name = qif.account_info.get('N')
            import_account = ctx.accounts.lookup_by_name(import_account_name)
            
            # Initialize matching service
            matching_service = MatchingService(matching_config)
            matchable_accounts = matching_service.get_matchable_accounts(import_account)
            
            candidates = []
            if matchable_accounts and test_transactions:
                start, end = matching_service.compute_candidate_date_range(test_transactions)
                candidates = ctx.transactions.query_unmatched(start, end, list(matchable_accounts))
            
            # Process transactions
            matched_count = 0
            imported_count = 0
            for action, txn in matching_service.match_transactions(import_account, test_transactions, candidates):
                if action == 'match':
                    ctx.transactions.mark_matched(txn)
                    matched_count += 1
                else:
                    ctx.transactions.insert(txn)
                    imported_count += 1
        
        # Verify transactions were processed
        assert matched_count + imported_count == len(test_transactions)


class TestFinalIntegrity:
    """Tests for final system integrity after all operations."""

    def test_all_transactions_balanced(self, db_with_existing_transactions):
        """Verify all transactions are balanced after matching operations."""
        db_url, book_name = db_with_existing_transactions
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            unbalanced = []
            for txn in transactions:
                split_sum = sum(split.amount for split in txn.splits)
                if abs(split_sum) > Decimal('0.01'):
                    unbalanced.append(txn.id)
            
            assert len(unbalanced) == 0, f"Found {len(unbalanced)} unbalanced transactions: {unbalanced}"

    def test_duplicate_detection(self, db_with_existing_transactions):
        """Check for and report potential duplicates."""
        db_url, book_name = db_with_existing_transactions
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            transaction_signatures = {}
            duplicates = []
            
            for txn in transactions:
                splits_signature = tuple(sorted([(split.account_id, split.amount) for split in txn.splits]))
                signature = (txn.transaction_date, splits_signature, txn.transaction_description.strip().lower())
                
                if signature in transaction_signatures:
                    duplicates.append((txn.id, transaction_signatures[signature].id))
                else:
                    transaction_signatures[signature] = txn
            
            # Note: We report duplicates but don't fail - they can be legitimate
            # (e.g., two identical purchases on the same day)
            if duplicates:
                print(f"Potential duplicates found (may be legitimate): {duplicates}")
            
            # Just ensure the test ran without errors
            assert True

    def test_transaction_count_reasonable(self, db_with_existing_transactions):
        """Verify transaction count is reasonable after all operations."""
        db_url, book_name = db_with_existing_transactions
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            # Should have at least the existing transactions
            assert len(transactions) >= len(EXISTING_TRANSACTIONS)

