#!/usr/bin/env python3
"""
Transaction Matching Debug Tool

This script provides detailed debugging information about transaction matching
logic to help diagnose matching issues and validate matching rule configurations.

What it does:
- Analyzes account names in the database vs. matching configuration
- Tests transaction query logic with different account name variations
- Steps through matching logic for individual transactions in detail
- Shows which matching patterns succeed/fail for each transaction
- Validates date offset calculations and split comparisons
- Provides comprehensive debugging output for troubleshooting

Usage:
    python debug_matching_logic.py
    
Prerequisites:
- Real-world test database must exist (run real_world_matching_test.py first)
- Sample QIF files must exist in data-samples/ directory
- Matching configuration must exist in matching-config.json

Output:
- Uses existing real-world-test.db database
- Prints detailed step-by-step debugging information
- Shows exact matching rule evaluation for sample transactions
- Identifies specific points where matching logic fails

This tool is primarily for developers debugging matching issues or validating
that matching rules are working correctly with real transaction data.
"""

import os
import sys
from datetime import datetime, timedelta

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.business.book_service import BookService
from ledger.business.account_service import AccountService
from ledger.business.transaction_service import TransactionService
from ledger.business.management_service import ManagementService
from ledger.business.matching_service import MatchingService, MatchingRules
from ledger.util.qif import Qif
from ledger.db.models import Transaction, Split

# Use the real-world test database that has both existing transactions and imports
DB_URL = "sqlite:///real-world-test.db"
BOOK_NAME = "real-world-test"
CONFIG_FILE = "matching-config.json"


def debug_account_names():
    """Debug account names and matching rules"""
    print("🔍 DEBUGGING ACCOUNT NAMES")
    print("="*50)
    
    # Check accounts in database
    with AccountService().init_with_url(DB_URL) as account_service:
        accounts = account_service.list_accounts_in_book(BOOK_NAME)
        
        print("📊 Accounts in database:")
        for account in accounts:
            print(f"  ID: {account.id}")
            print(f"  Name: '{account.name}'")
            print(f"  Full Name: '{account.full_name}'")
            print(f"  Code: '{account.code}'")
            print(f"  Type: {account.acct_type}")
            print()
    
    # Check matching rules
    print("📋 Matching rules:")
    try:
        matching_rules = MatchingRules(CONFIG_FILE)
        for account_name in matching_rules.rules["matching_rules"]:
            print(f"  Rule for: '{account_name}'")
            
            # Try to find corresponding account in database
            matching_account = None
            for account in accounts:
                if (account.full_name == account_name or 
                    account.name == account_name or 
                    account.code in account_name):
                    matching_account = account
                    break
            
            if matching_account:
                print(f"    ✅ Matches DB account: {matching_account.full_name}")
                
                # Check matchable accounts
                try:
                    matchable = matching_rules.matchable_accounts(matching_account)
                    print(f"    Can match with: {list(matchable)}")
                except Exception as e:
                    print(f"    ❌ Error getting matchable accounts: {e}")
            else:
                print(f"    ❌ No matching account found in database")
            print()
            
    except Exception as e:
        print(f"❌ Error loading matching rules: {e}")


def debug_transaction_query():
    """Debug the transaction query logic"""
    print("\n🔍 DEBUGGING TRANSACTION QUERY")
    print("="*50)
    
    with (
        AccountService().init_with_url(DB_URL) as account_service,
        TransactionService().init_with_url(DB_URL) as txn_service
    ):
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        accounts = account_service.list_accounts_in_book(BOOK_NAME)
        all_transactions = txn_service.get_all_transactions_for_book(book.id)
        
        print(f"📊 Total transactions in database: {len(all_transactions)}")
        
        # Show transaction details
        for i, txn in enumerate(all_transactions[:5]):  # Show first 5
            print(f"\nTransaction {i+1} (ID: {txn.id}):")
            print(f"  Date: {txn.transaction_date}")
            print(f"  Description: '{txn.transaction_description}'")
            print(f"  Match Status: '{txn.match_status}'")
            print(f"  Splits:")
            for split in txn.splits:
                account_name = "Unknown"
                for acc in accounts:
                    if acc.id == split.account_id:
                        account_name = acc.full_name
                        break
                print(f"    Account: {account_name} | Amount: {split.amount}")
        
        # Test the query method directly
        print(f"\n🧪 Testing query_for_unmatched_transactions_in_range:")
        
        # Get date range for all transactions
        if all_transactions:
            min_date = min(txn.transaction_date for txn in all_transactions)
            max_date = max(txn.transaction_date for txn in all_transactions)
            
            print(f"  Date range: {min_date} to {max_date}")
            
            # Test with different account name variations
            test_account_names = [
                # Try different variations of account names
                ["checking-chase-personal-1381"],
                ["Assets:Checking Accounts:checking-chase-personal-1381"],
                ["checking-chase-personal-1381", "checking-chase-personal-1605", "creditcard-chase-personal-6063"],
                ["Assets:Checking Accounts:checking-chase-personal-1381", "Assets:Checking Accounts:checking-chase-personal-1605"],
            ]
            
            for i, account_names in enumerate(test_account_names):
                print(f"\n  Test {i+1}: accounts_to_match_for = {account_names}")
                
                try:
                    candidates = txn_service.data_access.query_for_unmatched_transactions_in_range(
                        book_id=book.id,
                        start_date=min_date,
                        end_date=max_date,
                        accounts_to_match_for=account_names
                    )
                    print(f"    Result: {len(candidates)} candidate transactions found")
                    
                    for j, candidate in enumerate(candidates[:3]):  # Show first 3
                        print(f"      Candidate {j+1}: {candidate.transaction_description[:50]}...")
                        
                except Exception as e:
                    print(f"    ❌ Error: {e}")


def debug_matching_logic_step_by_step():
    """Debug the matching logic step by step"""
    print("\n🔍 DEBUGGING MATCHING LOGIC STEP BY STEP")
    print("="*50)
    
    # Load a small QIF sample
    qif_path = "data-samples/samples-1381.qif"
    qif = Qif()
    qif.init_from_qif_file(qif_path)
    
    print(f"📄 Using QIF: {qif_path}")
    print(f"  Account: {qif.account_info.get('N')}")
    print(f"  First transaction: {qif.transactions[0].get('P', 'No description')}")
    
    with (
        AccountService().init_with_url(DB_URL) as account_service,
        TransactionService().init_with_url(DB_URL) as txn_service
    ):
        book = account_service.data_access.get_book_by_name(BOOK_NAME)
        
        # Convert just the first transaction using new approach
        transaction_data = qif.as_transaction_data(book.id)
        test_transaction_data = transaction_data[0]
        
        # Create transaction object for testing (without persisting)
        test_transaction = Transaction()
        test_transaction.book_id = test_transaction_data['book_id']
        test_transaction.transaction_date = test_transaction_data['transaction_date']
        test_transaction.transaction_description = test_transaction_data['transaction_description']
        
        test_transaction.splits = []
        for split_data in test_transaction_data['splits']:
            split = Split()
            split.transaction = test_transaction
            split.account = account_service.lookup_account_by_name(
                book.id, split_data['account_name']
            )
            split.amount = split_data['amount']
            test_transaction.splits.append(split)
        
        print(f"\n📝 Test transaction:")
        print(f"  Date: {test_transaction.transaction_date}")
        print(f"  Description: '{test_transaction.transaction_description}'")
        print(f"  Splits:")
        for split in test_transaction.splits:
            print(f"    Account ID: {split.account_id} | Amount: {split.amount}")
        
        # Get the import account
        import_account_name = qif.account_info.get('N')
        import_account = account_service.data_access.get_account_by_fullname_for_book(
            book.id, import_account_name
        )
        
        print(f"\n🏦 Import account:")
        print(f"  Name: '{import_account.name}'")
        print(f"  Full Name: '{import_account.full_name}'")
        print(f"  ID: {import_account.id}")
        
        # Test matching rules
        try:
            matching_rules = MatchingRules(CONFIG_FILE)
            
            print(f"\n📋 Testing matching rules:")
            print(f"  Looking for rules for account: '{import_account.full_name}'")
            
            try:
                matchable_accounts = matching_rules.matchable_accounts(import_account)
                print(f"  ✅ Matchable accounts: {list(matchable_accounts)}")
                
                # Test batch query
                print(f"\n🔍 Testing batch query:")
                matching_service = MatchingService(matching_rules, txn_service)
                
                candidates = matching_service.batch_query_candidates(
                    book.id, [test_transaction], matchable_accounts
                )
                
                print(f"  Candidates found: {len(candidates)}")
                
                if candidates:
                    print("  Candidate details:")
                    for i, candidate in enumerate(candidates[:3]):
                        print(f"    {i+1}. {candidate.transaction_description[:50]}...")
                        print(f"       Date: {candidate.transaction_date}")
                        print(f"       Match Status: {candidate.match_status}")
                
                # Test is_match method
                if candidates:
                    print(f"\n🎯 Testing is_match logic:")
                    for i, candidate in enumerate(candidates[:3]):
                        try:
                            is_match = matching_service.is_match(import_account, test_transaction, candidate)
                            print(f"    Candidate {i+1}: {'✅ MATCH' if is_match else '❌ NO MATCH'}")
                            
                            # Debug why it didn't match
                            if not is_match:
                                print(f"      Debug details:")
                                
                                # Test split comparison
                                split_match = MatchingService.compare_splits(test_transaction, candidate)
                                print(f"        Split match: {'✅' if split_match else '❌'}")
                                
                                # Test description patterns
                                try:
                                    corresponding_account = test_transaction.corresponding_account(import_account)
                                    patterns = matching_rules.matching_patterns(import_account, corresponding_account)
                                    description = candidate.transaction_description
                                    
                                    print(f"        Description: '{description}'")
                                    print(f"        Patterns to match:")
                                    
                                    for pattern in patterns:
                                        import re
                                        matches = re.match(pattern, description)
                                        print(f"          '{pattern}': {'✅' if matches else '❌'}")
                                    
                                except Exception as e:
                                    print(f"        Error testing patterns: {e}")
                                
                                # Test date offset
                                try:
                                    corresponding_account = test_transaction.corresponding_account(import_account)
                                    date_offset = matching_rules.matching_date_offset(import_account, corresponding_account)
                                    date_diff = abs((test_transaction.transaction_date - candidate.transaction_date).days)
                                    
                                    print(f"        Date offset allowed: {date_offset} days")
                                    print(f"        Actual date diff: {date_diff} days")
                                    print(f"        Date match: {'✅' if date_diff <= date_offset else '❌'}")
                                    
                                except Exception as e:
                                    print(f"        Error testing date: {e}")
                        
                        except Exception as e:
                            print(f"    Error testing candidate {i+1}: {e}")
                
            except Exception as e:
                print(f"  ❌ Error getting matchable accounts: {e}")
                
        except Exception as e:
            print(f"❌ Error with matching rules: {e}")


def main():
    print("🐛 MATCHING LOGIC DEBUG SESSION")
    print("="*70)
    
    # Check if test database exists
    if not os.path.exists("real-world-test.db"):
        print("❌ Test database not found. Run real_world_matching_test.py first.")
        return 1
    
    debug_account_names()
    debug_transaction_query()
    debug_matching_logic_step_by_step()
    
    print("\n" + "="*70)
    print("🐛 DEBUG SESSION COMPLETE")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
