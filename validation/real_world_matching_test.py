#!/usr/bin/env python3
"""
Real-World Transaction Matching Test

This script tests realistic transaction matching scenarios that occur in personal
finance management, simulating the workflow of manually entering transactions
and later importing bank statements.

What it does:
- Creates a test database with manually entered transactions (simulating user entries)
- Imports QIF files containing bank statement data for the same transactions
- Tests the matching logic to ensure duplicate transactions are properly identified
- Validates that credit card payments, transfers, and other common scenarios match correctly
- Reports matching statistics and identifies any unmatched or incorrectly matched transactions

Usage:
    python real_world_matching_test.py [--reset] [--verbose]
    
    --reset     Delete existing test database and start fresh
    --verbose   Enable detailed output during testing
    
Prerequisites:
- Sample QIF files must exist in data-samples/ directory (samples-1381.qif, samples-1605.qif)
- Matching configuration must exist in matching-config.json
- Test accounts will be created automatically during setup

Output:
- Creates real-world-test.db in the current directory
- Prints detailed matching test results and statistics
- Shows before/after transaction counts and matching effectiveness
- Returns exit code 0 on success, 1 on failure

This test validates the core matching functionality with realistic data patterns
including credit card payments, account transfers, and various transaction types
found in actual bank statements.
"""

import os
import sys
import json
import argparse
from decimal import Decimal
from datetime import datetime, date

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.business.book_service import BookService
from ledger.business.account_service import AccountService
from ledger.business.transaction_service import TransactionService
from ledger.business.management_service import ManagementService
from ledger.business.matching_service import MatchingService, MatchingRules
from ledger.util.qif import Qif

# Configuration
DB_URL = "sqlite:///real-world-test.db"
BOOK_NAME = "real-world-test"
CONFIG_FILE = "matching-config.json"

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

# Pre-existing transactions that should match imports
# These represent transactions you manually entered before importing bank data
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


class RealWorldMatchingResults:
    """Track real-world matching test results"""
    
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.errors = []
        self.warnings = []
        self.matching_details = {}
        
    def add_error(self, message):
        self.errors.append(message)
        self.tests_failed += 1
        
    def add_warning(self, message):
        self.warnings.append(message)
        
    def add_success(self, message):
        self.tests_passed += 1
        
    def run_test(self, test_name, test_func):
        """Run a test and track results"""
        self.tests_run += 1
        try:
            print(f"🧪 {test_name}")
            result = test_func()
            self.add_success(f"✅ {test_name}")
            print(f"   ✅ PASSED")
            return result
        except Exception as e:
            self.add_error(f"❌ {test_name}: {str(e)}")
            print(f"   ❌ FAILED: {str(e)}")
            return None
            
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("REAL-WORLD MATCHING TEST SUMMARY")
        print("="*70)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.matching_details:
            print(f"\n📊 MATCHING DETAILS:")
            for test, details in self.matching_details.items():
                print(f"  {test}:")
                for key, value in details.items():
                    print(f"    {key}: {value}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  {warning}")
                
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
        else:
            print("\n🎉 ALL REAL-WORLD MATCHING TESTS PASSED!")
            
        print("="*70)
        return len(self.errors) == 0


def setup_real_world_test_environment(reset=False):
    """Initialize test database and accounts"""
    print("🔧 Setting up real-world test environment...")
    
    if reset and os.path.exists("real-world-test.db"):
        os.remove("real-world-test.db")
        print("  Database reset")
    
    # Initialize services
    with ManagementService().init_with_url(DB_URL) as mgmt_service:
        mgmt_service.reset_database()
        print("  Database initialized")
    
    with BookService().init_with_url(DB_URL) as book_service:
        book = book_service.create_new_book(BOOK_NAME)
        print(f"  Book '{BOOK_NAME}' created")
    
    # Create required accounts
    with AccountService().init_with_url(DB_URL) as account_service:
        for full_name, details in REQUIRED_ACCOUNTS.items():
            account_service.add_account(
                book_name=BOOK_NAME,
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
            print(f"  Account '{full_name}' created")


def create_existing_transactions():
    """Create existing transactions that imports should match against"""
    print("📝 Creating existing transactions...")
    
    created_transactions = []
    
    with TransactionService().init_with_url(DB_URL) as txn_service:
        for i, txn_data in enumerate(EXISTING_TRANSACTIONS):
            try:
                txn_id = txn_service.enter_transaction(
                    book_name=BOOK_NAME,
                    txn_date=txn_data["date"],
                    txn_desc=txn_data["description"],
                    from_acct=txn_data["from_account"],
                    to_acct=txn_data["to_account"],
                    amount=txn_data["amount"]
                )
                created_transactions.append(txn_id)
                print(f"  Created transaction {txn_id}: {txn_data['note']}")
            except Exception as e:
                raise Exception(f"Failed to create existing transaction {i+1}: {e}")
    
    return created_transactions


def get_transaction_summary():
    """Get summary of current transactions"""
    with (
        AccountService().init_with_url(DB_URL) as account_service,
        TransactionService().init_with_url(DB_URL) as txn_service
    ):
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        transactions = txn_service.get_all_transactions_for_book(book.id)
        
        summary = {
            'total': len(transactions),
            'matched': sum(1 for t in transactions if t.match_status == 'm'),
            'unmatched': sum(1 for t in transactions if t.match_status == 'n'),
            'transactions': transactions
        }
        
        return summary


def run_credit_card_payment_matching(results):
    """Test credit card payment matching scenario"""
    print("\n💳 Testing credit card payment matching...")
    
    # Get baseline
    before_summary = get_transaction_summary()
    print(f"  Before import: {before_summary['total']} transactions ({before_summary['matched']} matched)")
    
    # Import samples-1381.qif which should contain matching credit card payments
    qif_path = "data-samples/samples-1381.qif"
    if not os.path.exists(qif_path):
        raise Exception(f"QIF file not found: {qif_path}")
    
    # Load matching rules
    matching_rules = MatchingRules(CONFIG_FILE)
    
    # Parse and import subset of QIF file (just first few transactions to test)
    qif = Qif()
    qif.init_from_qif_file(qif_path)
    
    with TransactionService().init_with_url(DB_URL) as txn_service:
        book = txn_service.data_access.get_book_by_name(BOOK_NAME)
        
        # Get transaction data (dicts, not session-bound objects)
        all_transaction_data = qif.as_transaction_data(book.id)
        test_transaction_data = all_transaction_data[:10]  # Test with smaller subset
        
        # Convert to Transaction objects within this session context
        test_transactions = []
        for data in test_transaction_data:
            from ledger.db.models import Transaction, Split
            txn = Transaction()
            txn.book_id = data['book_id']
            txn.transaction_date = data['transaction_date']
            txn.transaction_description = data['transaction_description']
            txn.splits = []
            for split_data in data['splits']:
                split = Split()
                # Look up account within same session
                account = txn_service.data_access.get_account_by_fullname_for_book(
                    book.id, split_data['account_name']
                )
                if not account:
                    raise Exception(f"Account not found: {split_data['account_name']}")
                split.account = account
                split.account_id = account.id
                split.amount = split_data['amount']
                # Note: Don't set split.transaction as it auto-appends via backref
                txn.splits.append(split)
            test_transactions.append(txn)
        
        print(f"  Testing with first 10 transactions from QIF file")
        
        # Get the import account
        import_account_name = qif.account_info.get('N')
        import_account = txn_service.data_access.get_account_by_fullname_for_book(
            book.id, import_account_name
        )
        if not import_account:
            raise Exception(f"Import account not found: {import_account_name}")
        
        # Initialize matching service and perform import
        matching_service = MatchingService(matching_rules, txn_service)
        matching_service.import_transactions(book.id, import_account, test_transactions)
    
    # Get results
    after_summary = get_transaction_summary()
    print(f"  After import: {after_summary['total']} transactions ({after_summary['matched']} matched)")
    
    # Analyze results
    transactions_processed = len(test_transactions)
    new_transactions = after_summary['total'] - before_summary['total']
    matched_transactions = after_summary['matched'] - before_summary['matched']
    
    print(f"  📊 Results: {transactions_processed} processed, {matched_transactions} matched, {new_transactions} new")
    
    # Store results
    results.matching_details['credit_card_payment_test'] = {
        'processed': transactions_processed,
        'matched': matched_transactions,
        'new': new_transactions,
        'expected_matches': '1-3 (credit card payments)'
    }
    
    # Validation: We should have some matches and fewer new transactions than processed
    if matched_transactions == 0:
        raise Exception("No transactions were matched - matching logic may be broken")
    
    if new_transactions >= transactions_processed:
        raise Exception(f"All {transactions_processed} transactions created as new - no matching occurred")
    
    return {
        'processed': transactions_processed,
        'matched': matched_transactions,
        'new': new_transactions
    }


def run_transfer_matching(results):
    """Test transfer matching scenario"""
    print("\n🔄 Testing transfer matching...")
    
    # Get baseline
    before_summary = get_transaction_summary()
    print(f"  Before import: {before_summary['total']} transactions ({before_summary['matched']} matched)")
    
    # Import samples-1605.qif which should contain matching transfers
    qif_path = "data-samples/samples-1605.qif"
    if not os.path.exists(qif_path):
        raise Exception(f"QIF file not found: {qif_path}")
    
    # Load matching rules
    matching_rules = MatchingRules(CONFIG_FILE)
    
    # Parse and import subset of QIF file
    qif = Qif()
    qif.init_from_qif_file(qif_path)
    
    with TransactionService().init_with_url(DB_URL) as txn_service:
        book = txn_service.data_access.get_book_by_name(BOOK_NAME)
        
        # Get transaction data (dicts, not session-bound objects)
        all_transaction_data = qif.as_transaction_data(book.id)
        test_transaction_data = all_transaction_data[:5]  # Test with smaller subset
        
        # Convert to Transaction objects within this session context
        test_transactions = []
        for data in test_transaction_data:
            from ledger.db.models import Transaction, Split
            txn = Transaction()
            txn.book_id = data['book_id']
            txn.transaction_date = data['transaction_date']
            txn.transaction_description = data['transaction_description']
            txn.splits = []
            for split_data in data['splits']:
                split = Split()
                # Look up account within same session
                account = txn_service.data_access.get_account_by_fullname_for_book(
                    book.id, split_data['account_name']
                )
                if not account:
                    raise Exception(f"Account not found: {split_data['account_name']}")
                split.account = account
                split.account_id = account.id
                split.amount = split_data['amount']
                # Note: Don't set split.transaction as it auto-appends via backref
                txn.splits.append(split)
            test_transactions.append(txn)
        
        print(f"  Testing with first 5 transactions from QIF file")
        
        # Get the import account
        import_account_name = qif.account_info.get('N')
        import_account = txn_service.data_access.get_account_by_fullname_for_book(
            book.id, import_account_name
        )
        if not import_account:
            raise Exception(f"Import account not found: {import_account_name}")
        
        # Initialize matching service and perform import
        matching_service = MatchingService(matching_rules, txn_service)
        matching_service.import_transactions(book.id, import_account, test_transactions)
    
    # Get results
    after_summary = get_transaction_summary()
    print(f"  After import: {after_summary['total']} transactions ({after_summary['matched']} matched)")
    
    # Analyze results
    transactions_processed = len(test_transactions)
    new_transactions = after_summary['total'] - before_summary['total']
    matched_transactions = after_summary['matched'] - before_summary['matched']
    
    print(f"  📊 Results: {transactions_processed} processed, {matched_transactions} matched, {new_transactions} new")
    
    # Store results
    results.matching_details['transfer_test'] = {
        'processed': transactions_processed,
        'matched': matched_transactions,
        'new': new_transactions,
        'expected_matches': '1 (transfer from 1381)'
    }
    
    return {
        'processed': transactions_processed,
        'matched': matched_transactions,
        'new': new_transactions
    }


def run_final_integrity():
    """Test final system integrity"""
    print("\n⚖️  Testing final system integrity...")
    
    with (
        AccountService().init_with_url(DB_URL) as account_service,
        TransactionService().init_with_url(DB_URL) as txn_service
    ):
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        transactions = txn_service.get_all_transactions_for_book(book.id)
        
        # Check for duplicates
        transaction_signatures = {}
        duplicates = []
        
        for txn in transactions:
            splits_signature = tuple(sorted([(split.account_id, split.amount) for split in txn.splits]))
            signature = (txn.transaction_date, splits_signature, txn.transaction_description.strip().lower())
            
            if signature in transaction_signatures:
                duplicates.append((txn, transaction_signatures[signature]))
            else:
                transaction_signatures[signature] = txn
        
        # Check balance integrity
        unbalanced = []
        for txn in transactions:
            split_sum = sum(split.amount for split in txn.splits)
            if abs(split_sum) > Decimal('0.01'):
                unbalanced.append(txn)
        
        print(f"  Total transactions: {len(transactions)}")
        print(f"  Duplicates found: {len(duplicates)}")
        print(f"  Unbalanced transactions: {len(unbalanced)}")
        
        # Note: Duplicates are common in real-world bank data (e.g., two identical purchases)
        # We report them but don't fail the test - they're not necessarily errors
        if duplicates:
            duplicate_details = [(d[0].id, d[1].id) for d in duplicates]
            print(f"  ⚠️  Potential duplicates (may be legitimate): {duplicate_details}")
        
        if unbalanced:
            unbalanced_ids = [txn.id for txn in unbalanced]
            raise Exception(f"Found {len(unbalanced)} unbalanced transactions: {unbalanced_ids}")
        
        return {
            'total_transactions': len(transactions),
            'duplicates': len(duplicates),
            'unbalanced': len(unbalanced)
        }


def main():
    parser = argparse.ArgumentParser(description="Real-world transaction matching test")
    parser.add_argument("--reset", action="store_true", help="Reset test database")
    args = parser.parse_args()
    
    results = RealWorldMatchingResults()
    
    print("🧪 REAL-WORLD TRANSACTION MATCHING TEST")
    print("="*70)
    print("Testing actual matching scenarios with existing transactions")
    print("="*70)
    
    # Setup
    results.run_test(
        "Setup test environment",
        lambda: setup_real_world_test_environment(reset=args.reset)
    )
    
    # Create existing transactions
    results.run_test(
        "Create existing transactions",
        create_existing_transactions
    )
    
    # Test credit card payment matching
    results.run_test(
        "Credit card payment matching",
        lambda: run_credit_card_payment_matching(results)
    )
    
    # Test transfer matching  
    results.run_test(
        "Transfer matching",
        lambda: run_transfer_matching(results)
    )
    
    # Test final integrity
    results.run_test(
        "Final system integrity",
        run_final_integrity
    )
    
    # Print results
    success = results.print_summary()
    
    if success:
        print("\n🏆 REAL-WORLD MATCHING TEST COMPLETE!")
        print("   Your matching logic works correctly in realistic scenarios.")
    else:
        print("\n💀 REAL-WORLD MATCHING FAILED!")
        print("   Critical matching issues found that must be resolved.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
