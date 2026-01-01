import json
import re
from datetime import timedelta
from typing import List, Dict
from logging import info

from ledger.business.base_service import BaseService
from ledger.business.transaction_service import TransactionService
from ledger.db.models import Transaction, Account

DEFAULT_DATE_OFFSET = 1


class MatchingRules:
    '''
    Example matching rules:
    ```json
    {
        "matching_rules": {
            "checking-chase-personal-1381": {
                "creditcard-chase-personal-6063": {
                    "date_offset": 1,
                    "description_patterns": [
                        "^AUTOMATIC PAYMENT - THANK(?: YOU)?$",
                        "^Payment Thank You\\s?-\\s?(Web|Mobile)$"
                    ]
                },
                "checking-chase-personal-1605": {
                    "date_offset": 1,
                    "description_patterns": [
                        "^Online Transfer\\s+from\\s+CHK\\s*\\.\\.\\.1605(?:\\s+transaction#:\\s*\\d{2,})?$",
                        "^Online Transfer\\s+to\\s+CHK\\s*\\.\\.\\.1605(?:\\s+transaction#:\\s*(?:\\d{2,}(?:\\s+\\d{2}/\\d{2})?|\\d{2}/\\d{2}))?(?:\\s+t)?$"
                    ]
                }
            },
            "creditcard-chase-personal-6063": {
                "checking-chase-personal-1381": {
                    "date_offset": 3,
                    "description_patterns": [
                        "^CHASE CREDIT CRD AUTOPAY\\s*(?:\\d+)?\\s*PPD ID:\\s*\\d+$",
                        "^CITI AUTOPAY\\s+PAYMENT\\s+\\d+\\s+WEB ID:\\s+CITICARDAP$",
                        "^Payment to Chase card ending in \\d{4}\\s+\\d{2}/\\d{2}$"
                    ]
                }
            },
            "checking-chase-personal-1605": {
                "checking-chase-personal-1381": {
                    "date_offset": 2,
                    "description_patterns": [
                        "^Online Transfer\\s+from\\s+CHK\\s*\\.\\.\\.138\\d?(?:\\s+transaction#:\\s*\\S*)?$",
                        "^Online Transfer\\s+to\\s+CHK\\s*\\.\\.\\.138\\d?(?:\\s+transaction#:\\s*\\S+\\s+\\S+)?(?:\\s+t)?$"
                    ]
                }
            }
        }
    }
    ```
    '''

    def __init__(self, matching_rules: str):
        with open(matching_rules, 'r') as file:
            self.rules = json.load(fp=file)

    def matchable_accounts(self, account: Account) -> set:
        return self.rules["matching_rules"][account.full_name].keys()

    def matching_patterns(
        self, import_account: Account, corresponding_account: Account
    ) -> list[str]:
        return self.rules["matching_rules"][import_account.full_name][
            corresponding_account.full_name
        ]["description_patterns"]

    def matching_date_offset(self, import_account: Account, corresponding_account: Account) -> int:
        return self.rules["matching_rules"][import_account.full_name][
            corresponding_account.full_name
        ]["date_offset"]


class MatchingService(BaseService):
    def __init__(self, matching_rules: MatchingRules, transaction_service: TransactionService):
        super().__init__()
        # self.config = self._load_config(config_path)
        self.rules = matching_rules
        self.transaction_service = transaction_service

    def import_transactions(
        self, book_id: str, import_for: Account, to_import: List[Transaction]
    ) -> Dict[str, int]:
        '''
        Import a list of transactions into the book identified by `book_id` into the given account.
        
        For each transaction:
        - Check if it matches an existing transaction in the ledger
        - If matched: mark the existing transaction as matched (don't insert duplicate)
        - If not matched: add the transaction to the ledger
        
        Returns:
            Dict with counts: {'imported': N, 'matched': N}
        '''
        result = {'imported': 0, 'matched': 0}
        
        try:
            matchable_accounts = self.rules.matchable_accounts(import_for)
        except KeyError:
            # No matching rules for this account - just insert all
            for txn in to_import:
                self.add_transaction_to_ledger(txn)
                result['imported'] += 1
            return result
        
        candidates = self.batch_query_candidates(book_id, to_import, matchable_accounts)

        for txn_import in to_import:
            for txn_candidate in candidates:
                matched = self.is_match(import_for, txn_import, txn_candidate)
                if matched:
                    self.mark_matched(txn_candidate)
                    info(f'Transaction {txn_candidate} matched.')
                    result['matched'] += 1
                    break
            else:
                self.add_transaction_to_ledger(txn_import)
                result['imported'] += 1
        
        return result

    def is_match(
        self, import_for: Account, txn_import: Transaction, txn_candidate: Transaction
    ) -> bool:
        '''
        For a given `txn_import` to import into `import_for`, check to see if it matches `txn_candidate`
        '''
        split_match = MatchingService.compare_splits(txn_import, txn_candidate)
        if not split_match:
            return False

        corresponding_account = txn_import.corresponding_account(import_for)

        # attempt to match the description on the candidate transaction
        patterns = self.rules.matching_patterns(import_for, corresponding_account)
        description = txn_candidate.transaction_description
        for pattern in patterns:
            if re.match(pattern, description):
                break
        else:  # No match for any pattern
            return False

        # confirm it's within date range
        date_offset = self.rules.matching_date_offset(import_for, corresponding_account)
        date_diff = abs((txn_import.transaction_date - txn_candidate.transaction_date).days)
        if date_diff > date_offset:
            return False

        return True

    def batch_query_candidates(
        self, book_id: str, imported_transactions: List[Transaction], matching_accounts: List[str]
    ) -> Dict[str, List[Transaction]]:
        """
        Query candidate transactions for all imported transactions in batch.
        """
        # Determine global date range for the batch
        min_date = min(txn.transaction_date for txn in imported_transactions)
        max_date = max(txn.transaction_date for txn in imported_transactions)
        buffer_days = DEFAULT_DATE_OFFSET
        min_date -= timedelta(days=buffer_days)
        max_date += timedelta(days=buffer_days)

        # Query candidates from the TransactionService
        c = self.transaction_service.query_matchable_transactions(
            book_id=book_id,
            start_date=min_date,
            end_date=max_date,
            accounts_to_match_for=matching_accounts,
        )

        return c

    @staticmethod
    def compare_splits(imported: Transaction, candidate: Transaction) -> Transaction | None:
        """
        Compare the splits between these two transactions. If all splits in the candidate match
        splits in the transaction being imported (based on `account_id` and `amount` of the splits),
        return the candidate transaction.

        Args:
            imported (Transaction): The transaction being imported.
            candidate (Transaction): The transaction to compare against.

        Returns:
            Transaction | None: Returns the candidate transaction if all of its splits match
            the imported transaction's splits by account_id & amount.
        """
        # sanity check
        if len(candidate.splits) != len(imported.splits):
            return None

        # Create a lookup dictionary of imported splits based on (account_id, amount)
        imported_splits_set = {(split.account_id, split.amount) for split in imported.splits}

        # Iterate through all candidate splits and check if they exist in the imported transaction
        for candidate_split in candidate.splits:
            key = (candidate_split.account_id, candidate_split.amount)
            if key not in imported_splits_set:
                return None  # If any split does not match, return None

        return candidate  # Return candidate only if all splits match

    def mark_matched(self, txn: Transaction):
        """Update transaction to mark it as matched using TransactionService."""
        self.transaction_service.mark_transaction_matched(txn)

    def add_transaction_to_ledger(self, txn: Transaction):
        """Add a new transaction to the ledger using TransactionService."""
        self.transaction_service.insert_transaction(txn)
