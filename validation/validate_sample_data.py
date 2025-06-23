#!/usr/bin/env python3
"""
Sample Data Validation Script

This script validates the basic transaction import and matching functionality using
sample QIF files. It performs comprehensive testing to ensure data integrity and
proper transaction handling.

What it does:
- Imports transactions from sample QIF files (sample-1381.qif, sample-1605.qif, sample-6063.qif)
- Validates that transactions are imported correctly without errors
- Tests matching rule configuration and account resolution
- Ensures double-entry bookkeeping balance integrity (all transactions sum to zero)
- Detects duplicate transactions that might indicate import issues
- Reports comprehensive statistics and any errors found

Usage:
    python validate_sample_data.py [--reset] [--verbose]
    
    --reset     Delete existing test database and start fresh
    --verbose   Enable detailed output during validation
    
Prerequisites:
- Sample QIF files must exist in data-samples/ directory
- Matching configuration must exist in matching-config.json
- Required accounts will be created automatically during setup

Output:
- Creates validation-test.db in the current directory
- Prints detailed validation results and statistics
- Returns exit code 0 on success, 1 on failure
"""

import os
import sys
import json
import argparse
from decimal import Decimal
from datetime import datetime
from collections import defaultdict

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from financial_accounts.business.book_service import BookService
from financial_accounts.business.account_service import AccountService
from financial_accounts.business.transaction_service import TransactionService
from financial_accounts.business.management_service import ManagementService
from financial_accounts.business.matching_service import MatchingService, MatchingRules
from financial_accounts.util.qif import Qif

# Configuration
DB_URL = "sqlite:///validation-test.db"
BOOK_NAME = "validation-test"
SAMPLE_DIR = "data-samples"
CONFIG_FILE = "matching-config.json"

# Sample files to test
SAMPLE_FILES = [
    "sample-1381.qif",
    "sample-1605.qif", 
    "sample-6063.qif"
]

# Expected account structure based on QIF files
EXPECTED_ACCOUNTS = {
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


class ValidationResults:
    """Track validation results and statistics"""
    
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.errors = []
        self.warnings = []
        self.balances_before = {}
        self.balances_after = {}
        self.transactions_imported = {}
        self.transactions_matched = {}
        
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
            test_func()
            self.add_success(f"✅ {test_name}")
            return True
        except Exception as e:
            self.add_error(f"❌ {test_name}: {str(e)}")
            return False
            
    def print_summary(self):
        """Print validation summary"""
        print("\n" + "="*60)
        print("VALIDATION SUMMARY")
        print("="*60)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_failed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  {warning}")
                
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  {error}")
        else:
            print("\n🎉 ALL TESTS PASSED!")
            
        print("\n" + "="*60)


def setup_test_environment(reset=False):
    """Initialize test database and accounts"""
    print("🔧 Setting up test environment...")
    
    if reset and os.path.exists("validation-test.db"):
        os.remove("validation-test.db")
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
        for full_name, details in EXPECTED_ACCOUNTS.items():
            try:
                account_service.add_account(
                    book_name=BOOK_NAME,
                    parent_code=None,
                    parent_name=None,
                    acct_name=full_name.split(":")[-1],
                    full_name=full_name,
                    acct_code=details["code"],
                    acct_type=details["type"],
                    description=f"Test account {details['code']}",
                    hidden=False,
                    placeholder=False
                )
                print(f"  Account '{full_name}' created")
            except Exception as e:
                print(f"  ⚠️  Account '{full_name}' creation failed: {e}")


def get_account_balances(account_service, book_name):
    """Calculate current account balances"""
    balances = {}
    accounts = account_service.list_accounts_in_book(book_name)
    
    with TransactionService().init_with_url(DB_URL) as txn_service:
        for account in accounts:
            # Get all splits for this account
            splits = txn_service.data_access.list_splits_for_account(account.id)
            balance = sum(split.amount for split in splits)
            balances[account.full_name] = balance
            
    return balances


def validate_qif_file_structure(qif_file):
    """Validate QIF file can be parsed correctly"""
    print(f"📄 Validating QIF file structure: {qif_file}")
    
    qif = Qif()
    qif.init_from_qif_file(qif_file)
    
    # Basic validation
    if not qif.account_info:
        raise Exception("No account information found in QIF file")
        
    if not qif.transactions:
        raise Exception("No transactions found in QIF file")
        
    print(f"  Account: {qif.account_info.get('N', 'Unknown')}")
    print(f"  Transactions: {len(qif.transactions)}")
    
    # Validate transaction structure
    for i, txn in enumerate(qif.transactions):
        if 'D' not in txn:
            raise Exception(f"Transaction {i+1} missing date")
        if 'T' not in txn:
            raise Exception(f"Transaction {i+1} missing amount")
        if 'L' not in txn:
            raise Exception(f"Transaction {i+1} missing category")
            
    return qif


def test_individual_qif_import(qif_file, results):
    """Test importing a single QIF file"""
    print(f"\n📥 Testing import of {qif_file}")
    
    qif_path = os.path.join(SAMPLE_DIR, qif_file)
    if not os.path.exists(qif_path):
        results.add_error(f"QIF file not found: {qif_path}")
        return
        
    # Validate file structure
    try:
        qif = validate_qif_file_structure(qif_path)
    except Exception as e:
        results.add_error(f"QIF structure validation failed: {e}")
        return
        
    # Get account balances before import
    with AccountService().init_with_url(DB_URL) as account_service:
        balances_before = get_account_balances(account_service, BOOK_NAME)
        
    # Import transactions using session-safe approach
    with TransactionService().init_with_url(DB_URL) as txn_service:
        # Create account service that shares the same session
        account_service = AccountService()
        account_service.session = txn_service.session
        account_service.data_access = txn_service.data_access
        
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        transaction_data = qif.as_transaction_data(book.id)
        
        try:
            imported_ids = txn_service.import_transactions_from_qif_data(transaction_data, account_service)
            imported_count = len(imported_ids)
        except Exception as e:
            results.add_error(f"Failed to import transactions: {e}")
            imported_count = 0
                
        print(f"  Imported {imported_count} transactions")
        results.transactions_imported[qif_file] = imported_count
        
    # Get balances after import
    with AccountService().init_with_url(DB_URL) as account_service:
        balances_after = get_account_balances(account_service, BOOK_NAME)
        
    # Validate balance changes
    for account_name in balances_before:
        change = balances_after[account_name] - balances_before[account_name]
        if change != 0:
            print(f"  {account_name}: {balances_before[account_name]} → {balances_after[account_name]} (Δ{change})")


def test_matching_logic(results):
    """Test the matching logic with sample data"""
    print(f"\n🔍 Testing matching logic")
    
    # Load matching rules
    if not os.path.exists(CONFIG_FILE):
        results.add_error(f"Matching config file not found: {CONFIG_FILE}")
        return
        
    try:
        matching_rules = MatchingRules(CONFIG_FILE)
    except Exception as e:
        results.add_error(f"Failed to load matching rules: {e}")
        return
        
    # Test each account's matching rules
    with AccountService().init_with_url(DB_URL) as account_service:
        accounts = account_service.list_accounts_in_book(BOOK_NAME)
        
        for account in accounts:
            try:
                matchable = matching_rules.matchable_accounts(account)
                print(f"  {account.full_name} can match with: {list(matchable)}")
            except KeyError:
                print(f"  {account.full_name}: No matching rules defined")


def test_balance_integrity(results):
    """Test that the books remain balanced"""
    print(f"\n⚖️  Testing balance integrity")
    
    with (
        AccountService().init_with_url(DB_URL) as account_service,
        TransactionService().init_with_url(DB_URL) as txn_service
    ):
        # Get all transactions
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        transactions = txn_service.get_all_transactions_for_book(book.id)
        
        unbalanced_transactions = []
        for txn in transactions:
            split_sum = sum(split.amount for split in txn.splits)
            if abs(split_sum) > Decimal('0.01'):  # Allow for minor rounding
                unbalanced_transactions.append((txn.id, split_sum))
                
        if unbalanced_transactions:
            for txn_id, imbalance in unbalanced_transactions:
                results.add_error(f"Unbalanced transaction {txn_id}: imbalance = {imbalance}")
        else:
            print("  ✅ All transactions are balanced")
            results.add_success("Balance integrity check")


def test_no_duplicate_transactions(results):
    """Test that no duplicate transactions were created"""
    print(f"\n🔍 Testing for duplicate transactions")
    
    with (
        AccountService().init_with_url(DB_URL) as account_service,
        TransactionService().init_with_url(DB_URL) as txn_service
    ):
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        transactions = txn_service.get_all_transactions_for_book(book.id)
        
        # Group by date and description
        transaction_groups = defaultdict(list)
        for txn in transactions:
            key = (txn.transaction_date, txn.transaction_description)
            transaction_groups[key].append(txn)
            
        duplicates = []
        for key, txns in transaction_groups.items():
            if len(txns) > 1:
                # Check if they have identical splits
                for i, txn1 in enumerate(txns):
                    for txn2 in txns[i+1:]:
                        if len(txn1.splits) == len(txn2.splits):
                            splits1 = sorted([(s.account_id, s.amount) for s in txn1.splits])
                            splits2 = sorted([(s.account_id, s.amount) for s in txn2.splits])
                            if splits1 == splits2:
                                duplicates.append((txn1.id, txn2.id, key))
                                
        if duplicates:
            for txn1_id, txn2_id, key in duplicates:
                results.add_error(f"Duplicate transactions found: {txn1_id} and {txn2_id} ({key})")
        else:
            print("  ✅ No duplicate transactions found")
            results.add_success("Duplicate transaction check")


def main():
    parser = argparse.ArgumentParser(description="Validate sample QIF data imports")
    parser.add_argument("--reset", action="store_true", help="Reset test database")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    results = ValidationResults()
    
    print("🧪 SAMPLE DATA VALIDATION")
    print("="*50)
    
    # Setup test environment
    try:
        setup_test_environment(reset=args.reset)
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return 1
        
    # Test each sample file
    for qif_file in SAMPLE_FILES:
        results.run_test(
            f"Import {qif_file}",
            lambda f=qif_file: test_individual_qif_import(f, results)
        )
        
    # Test matching logic
    results.run_test(
        "Matching logic validation",
        lambda: test_matching_logic(results)
    )
    
    # Test balance integrity
    results.run_test(
        "Balance integrity",
        lambda: test_balance_integrity(results)
    )
    
    # Test for duplicates
    results.run_test(
        "No duplicate transactions",
        lambda: test_no_duplicate_transactions(results)
    )
    
    # Print results
    results.print_summary()
    
    # Return exit code
    return 0 if results.tests_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
