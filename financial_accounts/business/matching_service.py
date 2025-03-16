import json
import re
from datetime import timedelta
from typing import List, Dict
from logging import info

from financial_accounts.business.base_service import BaseService
from financial_accounts.business.transaction_service import TransactionService
from financial_accounts.db.models import Transaction, Account

DEFAULT_DATE_OFFSET = 0


class MatchingRules:
    def __init__(self, matching_rules: str):
        with open(matching_rules, 'r') as file:
            self.rules = json.load(fp=file)

    def matchable_accounts(self, account):
        return self.rules["matching_rules"][account].keys()

    def matching_patterns(self, import_account, corresponding_account) -> list[str]:
        return self.rules["matching_rules"][import_account][corresponding_account][
            "description_patterns"
        ]

    def matching_date_offset(self, import_account, corresponding_account) -> int:
        return self.rules["matching_rules"][import_account][corresponding_account]["date_offset"]


class MatchingService(BaseService):
    def __init__(self, config_path: str, transaction_service: TransactionService):
        super().__init__()
        # self.config = self._load_config(config_path)
        self.rules = MatchingRules(config_path)
        self.transaction_service = transaction_service

    def import_transactions(
        self, book_id: str, import_for: Account, to_import: List[Transaction]
    ) -> None:
        matchable_accounts = self.rules.matchable_accounts(import_for)
        candidates = self.batch_query_candidates(book_id, to_import, matchable_accounts)

        for txn_import in to_import:
            for txn_candidate in candidates:
                matched = self.is_match(import_for, txn_import, txn_candidate)
                if matched:
                    self.mark_matched(txn_import)
                    info(f'Transaction {txn_import} matched.')
                    break
            else:
                self.add_transaction_to_ledger(txn_import)

    def is_match(
        self, import_for: Account, txn_import: Transaction, txn_candidate: Transaction
    ) -> bool:
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
        buffer_days = self.config["global_defaults"].get("date_offset", DEFAULT_DATE_OFFSET)
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
        # Create a lookup dictionary of imported splits based on (account_id, amount)
        imported_splits_lookup = {
            (split.account_id, split.amount): split for split in imported.splits
        }

        # Iterate through all candidate splits and check if they exist in the imported transaction
        for candidate_split in candidate.splits:
            key = (candidate_split.account_id, candidate_split.amount)
            if key not in imported_splits_lookup:
                return None  # If any split does not match, return None

        return candidate  # Return candidate only if all splits match

    def mark_matched(self, txn: Transaction):
        """Update transaction to mark it as matched using TransactionService."""
        self.transaction_service.mark_transaction_matched(txn)

    def add_transaction_to_ledger(self, txn: Transaction):
        """Add a new transaction to the ledger using TransactionService."""
        self.transaction_service.insert_transaction(txn)
