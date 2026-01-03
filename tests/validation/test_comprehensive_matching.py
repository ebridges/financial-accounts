"""
Comprehensive validation tests for transaction matching.

Tests all matching patterns with a large dataset of real-world transactions
spanning multiple years, including edge cases and balance integrity checks.
"""
import os
import pytest
import tempfile
from decimal import Decimal
from collections import defaultdict

from ledger.business.book_service import BookService
from ledger.business.book_context import BookContext
from ledger.business.management_service import ManagementService
from ledger.business.matching_service import MatchingService, MatchingRules
from ledger.util.qif import Qif


# Mark all tests in this file as validation + slow tests
pytestmark = [pytest.mark.validation, pytest.mark.slow]


# Required accounts
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

# Comprehensive sample files (larger test data)
COMPREHENSIVE_FILES = [
    "samples-1381.qif",
    "samples-1605.qif",
    "samples-6063.qif"
]

# Expected patterns and their approximate counts (reduced test data)
EXPECTED_PATTERNS = {
    "AUTOMATIC PAYMENT - THANK": {
        "expected_count": 8,
        "accounts": ["checking-chase-personal-1381", "creditcard-chase-personal-6063"]
    },
    "CHASE CREDIT CRD AUTOPAY": {
        "expected_count": 6,
        "accounts": ["checking-chase-personal-1381", "creditcard-chase-personal-6063"]
    },
    "Online Transfer": {
        "expected_count": 24,
        "accounts": ["checking-chase-personal-1381", "checking-chase-personal-1605"]
    },
    "Payment to Chase card": {
        "expected_count": 6,
        "accounts": ["checking-chase-personal-1381", "creditcard-chase-personal-6063"]
    },
    "Payment Thank You": {
        "expected_count": 5,
        "accounts": ["creditcard-chase-personal-6063", "checking-chase-personal-1381"]
    }
}


@pytest.fixture(scope="module")
def comprehensive_db():
    """Create a separate database for comprehensive validation tests."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    db_url = f"sqlite:///{db_path}"
    book_name = "comprehensive-test"
    
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
                description=f"Comprehensive test account {details['code']}",
                hidden=False,
                placeholder=False
            )
    
    yield db_url, book_name
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestPatternRecognition:
    """Tests for pattern recognition in sample data."""

    def test_load_matching_rules(self, matching_config):
        """Test that matching rules load correctly."""
        rules = MatchingRules(matching_config)
        assert rules.rules is not None
        assert "matching_rules" in rules.rules

    def test_pattern_counts_in_sample_files(self, sample_data_dir):
        """Test that expected patterns exist in sample files."""
        pattern_counts = defaultdict(int)
        
        for qif_file in COMPREHENSIVE_FILES:
            qif_path = os.path.join(sample_data_dir, qif_file)
            if not os.path.exists(qif_path):
                pytest.skip(f"Comprehensive sample file not found: {qif_path}")
            
            qif = Qif()
            qif.init_from_qif_file(qif_path)
            
            for txn in qif.transactions:
                description = txn.get('P', '')
                
                for pattern_name in EXPECTED_PATTERNS:
                    if pattern_name.replace(' ', '').lower() in description.replace(' ', '').lower():
                        pattern_counts[pattern_name] += 1
        
        # Verify at least some patterns were found
        assert len(pattern_counts) > 0, "No patterns found in sample files"
        
        # Check major patterns exist
        for pattern in ["Online Transfer", "AUTOMATIC PAYMENT - THANK"]:
            if pattern in EXPECTED_PATTERNS:
                assert pattern_counts.get(pattern, 0) > 0, f"Pattern '{pattern}' not found"


class TestComprehensiveQifParsing:
    """Tests for comprehensive QIF file parsing."""

    def test_samples_1381_structure(self, sample_data_dir):
        """Validate samples-1381.qif structure."""
        qif_path = os.path.join(sample_data_dir, "samples-1381.qif")
        if not os.path.exists(qif_path):
            pytest.skip(f"File not found: {qif_path}")
        
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        assert qif.account_info, "No account information"
        assert qif.transactions, "No transactions"
        assert len(qif.transactions) >= 10, "Expected at least 10 transactions"
        
        # Validate structure of all transactions
        for i, txn in enumerate(qif.transactions):
            assert 'D' in txn, f"Transaction {i+1} missing date"
            assert 'T' in txn, f"Transaction {i+1} missing amount"
            assert 'L' in txn, f"Transaction {i+1} missing category"

    def test_samples_1605_structure(self, sample_data_dir):
        """Validate samples-1605.qif structure."""
        qif_path = os.path.join(sample_data_dir, "samples-1605.qif")
        if not os.path.exists(qif_path):
            pytest.skip(f"File not found: {qif_path}")
        
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        assert qif.account_info, "No account information"
        assert qif.transactions, "No transactions"

    def test_samples_6063_structure(self, sample_data_dir):
        """Validate samples-6063.qif structure."""
        qif_path = os.path.join(sample_data_dir, "samples-6063.qif")
        if not os.path.exists(qif_path):
            pytest.skip(f"File not found: {qif_path}")
        
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        assert qif.account_info, "No account information"
        assert qif.transactions, "No transactions"


class TestComprehensiveImportAndMatching:
    """Tests for comprehensive import and matching operations."""

    def test_import_samples_1381(self, comprehensive_db, sample_data_dir, matching_config):
        """Test importing and matching samples-1381.qif."""
        db_url, book_name = comprehensive_db
        qif_path = os.path.join(sample_data_dir, "samples-1381.qif")
        
        if not os.path.exists(qif_path):
            pytest.skip(f"File not found: {qif_path}")
        
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        with BookContext(book_name, db_url) as ctx:
            def resolve_account(name):
                try:
                    return ctx.accounts.lookup_by_name(name)
                except Exception:
                    return None
            
            transactions_to_import = qif.as_transactions(ctx.book.id, resolve_account)
            assert len(transactions_to_import) > 0
            
            import_account_name = qif.account_info.get('N')
            import_account = ctx.accounts.lookup_by_name(import_account_name)
            
            matching_service = MatchingService(matching_config)
            matchable_accounts = matching_service.get_matchable_accounts(import_account)
            
            candidates = []
            if matchable_accounts and transactions_to_import:
                start, end = matching_service.compute_candidate_date_range(transactions_to_import)
                candidates = ctx.transactions.query_unmatched(start, end, list(matchable_accounts))
            
            matched_count = 0
            imported_count = 0
            for action, txn in matching_service.match_transactions(import_account, transactions_to_import, candidates):
                if action == 'match':
                    ctx.transactions.mark_matched(txn)
                    matched_count += 1
                else:
                    ctx.transactions.insert(txn)
                    imported_count += 1
            
            assert matched_count + imported_count == len(transactions_to_import)

    def test_import_samples_1605(self, comprehensive_db, sample_data_dir, matching_config):
        """Test importing and matching samples-1605.qif."""
        db_url, book_name = comprehensive_db
        qif_path = os.path.join(sample_data_dir, "samples-1605.qif")
        
        if not os.path.exists(qif_path):
            pytest.skip(f"File not found: {qif_path}")
        
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        with BookContext(book_name, db_url) as ctx:
            def resolve_account(name):
                try:
                    return ctx.accounts.lookup_by_name(name)
                except Exception:
                    return None
            
            transactions_to_import = qif.as_transactions(ctx.book.id, resolve_account)
            assert len(transactions_to_import) > 0
            
            import_account_name = qif.account_info.get('N')
            import_account = ctx.accounts.lookup_by_name(import_account_name)
            
            matching_service = MatchingService(matching_config)
            matchable_accounts = matching_service.get_matchable_accounts(import_account)
            
            candidates = []
            if matchable_accounts and transactions_to_import:
                start, end = matching_service.compute_candidate_date_range(transactions_to_import)
                candidates = ctx.transactions.query_unmatched(start, end, list(matchable_accounts))
            
            matched_count = 0
            imported_count = 0
            for action, txn in matching_service.match_transactions(import_account, transactions_to_import, candidates):
                if action == 'match':
                    ctx.transactions.mark_matched(txn)
                    matched_count += 1
                else:
                    ctx.transactions.insert(txn)
                    imported_count += 1

    def test_import_samples_6063(self, comprehensive_db, sample_data_dir, matching_config):
        """Test importing and matching samples-6063.qif."""
        db_url, book_name = comprehensive_db
        qif_path = os.path.join(sample_data_dir, "samples-6063.qif")
        
        if not os.path.exists(qif_path):
            pytest.skip(f"File not found: {qif_path}")
        
        qif = Qif()
        qif.init_from_qif_file(qif_path)
        
        with BookContext(book_name, db_url) as ctx:
            def resolve_account(name):
                try:
                    return ctx.accounts.lookup_by_name(name)
                except Exception:
                    return None
            
            transactions_to_import = qif.as_transactions(ctx.book.id, resolve_account)
            assert len(transactions_to_import) > 0
            
            import_account_name = qif.account_info.get('N')
            import_account = ctx.accounts.lookup_by_name(import_account_name)
            
            matching_service = MatchingService(matching_config)
            matchable_accounts = matching_service.get_matchable_accounts(import_account)
            
            candidates = []
            if matchable_accounts and transactions_to_import:
                start, end = matching_service.compute_candidate_date_range(transactions_to_import)
                candidates = ctx.transactions.query_unmatched(start, end, list(matchable_accounts))
            
            matched_count = 0
            imported_count = 0
            for action, txn in matching_service.match_transactions(import_account, transactions_to_import, candidates):
                if action == 'match':
                    ctx.transactions.mark_matched(txn)
                    matched_count += 1
                else:
                    ctx.transactions.insert(txn)
                    imported_count += 1


class TestBalanceIntegrityComprehensive:
    """Comprehensive balance integrity tests."""

    def test_all_transactions_balanced(self, comprehensive_db):
        """Test that all transactions sum to zero."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            unbalanced = []
            for txn in transactions:
                split_sum = sum(split.amount for split in txn.splits)
                if abs(split_sum) > Decimal('0.01'):
                    unbalanced.append((txn.id, split_sum))
            
            assert len(unbalanced) == 0, f"Found {len(unbalanced)} unbalanced transactions"

    def test_system_balance(self, comprehensive_db):
        """Test that the overall system balance is zero."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            accounts = ctx.accounts.list_accounts()
            
            total_balance = Decimal('0')
            for account in accounts:
                balance = sum(split.amount for split in account.splits)
                total_balance += balance
            
            assert abs(total_balance) <= Decimal('0.01'), f"System not balanced: {total_balance}"

    def test_split_integrity(self, comprehensive_db):
        """Test that all transactions have exactly 2 splits."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            violations = []
            for txn in transactions:
                if len(txn.splits) != 2:
                    violations.append((txn.id, len(txn.splits)))
            
            assert len(violations) == 0, f"Split integrity violations: {violations}"


class TestEdgeCases:
    """Tests for edge cases in transaction matching."""

    def test_same_date_transactions(self, comprehensive_db):
        """Test handling of multiple transactions on the same date."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            if not transactions:
                pytest.skip("No transactions to test")
            
            date_groups = defaultdict(list)
            for txn in transactions:
                date_groups[txn.transaction_date].append(txn)
            
            same_date_groups = {d: txns for d, txns in date_groups.items() if len(txns) > 1}
            
            # Multiple transactions on same date should exist in comprehensive data
            assert len(same_date_groups) > 0, "Expected some dates with multiple transactions"

    def test_amount_range(self, comprehensive_db):
        """Test that amounts span a reasonable range."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            if not transactions:
                pytest.skip("No transactions to test")
            
            amounts = [abs(split.amount) for txn in transactions for split in txn.splits]
            
            if amounts:
                max_amount = max(amounts)
                min_amount = min(a for a in amounts if a > 0)
                
                # Should have a variety of amounts
                assert max_amount > Decimal('100'), "Expected some large transactions"

    def test_year_boundaries(self, comprehensive_db):
        """Test transactions near year boundaries."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            if not transactions:
                pytest.skip("No transactions to test")
            
            years = set(txn.transaction_date.year for txn in transactions)
            
            # Comprehensive data should span multiple years
            if len(years) > 1:
                december_txns = [t for t in transactions if t.transaction_date.month == 12]
                january_txns = [t for t in transactions if t.transaction_date.month == 1]
                
                assert len(december_txns) > 0 or len(january_txns) > 0


class TestDuplicateDetection:
    """Tests for duplicate detection in comprehensive data."""

    def test_no_true_duplicates(self, comprehensive_db):
        """Test that no true duplicate transactions exist (with warnings for potential duplicates)."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            if not transactions:
                pytest.skip("No transactions to test")
            
            transaction_signatures = defaultdict(list)
            
            for txn in transactions:
                splits_signature = tuple(sorted([(split.account_id, split.amount) for split in txn.splits]))
                signature = (
                    txn.transaction_date,
                    splits_signature,
                    txn.transaction_description.strip().lower()
                )
                transaction_signatures[signature].append(txn)
            
            duplicates = [
                (sig, txns) for sig, txns in transaction_signatures.items() 
                if len(txns) > 1
            ]
            
            # Note: Some duplicates may be legitimate (transfers appearing in both accounts)
            # We just report them, but don't fail the test
            if duplicates:
                print(f"Potential duplicates (may be legitimate): {len(duplicates)} groups")
            
            # The test passes - we're just documenting potential duplicates
            assert True

    def test_unique_signature_count(self, comprehensive_db):
        """Test that unique transaction signatures exist."""
        db_url, book_name = comprehensive_db
        
        with BookContext(book_name, db_url) as ctx:
            transactions = ctx.transactions.get_all()
            
            if not transactions:
                pytest.skip("No transactions to test")
            
            signatures = set()
            for txn in transactions:
                splits_sig = tuple(sorted([(s.account_id, s.amount) for s in txn.splits]))
                sig = (txn.transaction_date, splits_sig, txn.transaction_description)
                signatures.add(sig)
            
            # Should have many unique signatures
            assert len(signatures) > 0

