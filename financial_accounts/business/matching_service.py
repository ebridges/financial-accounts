import json
import re
from datetime import timedelta
from typing import List, Dict

from financial_accounts.business.base_service import BaseService
from financial_accounts.business.transaction_service import TransactionService
from financial_accounts.db.models import Transaction

DEFAULT_DATE_OFFSET = 2


class MatchingService(BaseService):
    def __init__(self, config_path: str, transaction_service: TransactionService):
        super().__init__()
        self.init_with_session(session_local=transaction_service.SessionLocal)
        self.config = self._load_config(config_path)
        self.transaction_service = transaction_service

    def _load_config(self, config_path: str) -> Dict:
        """Load JSON configuration for matching criteria."""
        with open(config_path, 'r') as file:
            return json.load(file)

    def import_transactions(
        self, book_id: str, import_for_account: str, to_import: List[Transaction]
    ) -> None:
        """
        Match imported transactions against candidates in memory.
        """
        # Batch query all candidates
        candidates = self._batch_query_candidates(book_id, to_import)

        # Cache candidates in a dictionary grouped by account
        candidate_cache = self._group_candidates_by_account(candidates)

        rules_list = self._get_account_rules(import_for_account)
        for txn in to_import:
            matched = False

            # Iterate through all corresponding accounts in the rules
            for rules in rules_list:
                corresponding_account = rules["account"]

                if corresponding_account not in candidate_cache:
                    continue

                potential_matches = candidate_cache[corresponding_account]
                for candidate in potential_matches:
                    if self._is_match(txn, candidate, rules):
                        self._mark_matched(candidate)
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                self._add_transaction_to_ledger(txn)

    def _batch_query_candidates(
        self, book_id: str, imported_transactions: List[Transaction]
    ) -> List[Transaction]:
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
        return self.transaction_service.get_transactions_in_range(
            book_id=book_id,
            start_date=min_date,
            end_date=max_date,
            recon_status=None,  # Only unreconciled transactions
            match_status=None,  # Only unmatched transactions
        )

    def _get_account_rules(self, account: str) -> List[Dict]:
        """Retrieve account-specific matching rules, falling back to defaults."""
        accounts = [a for a in self.config.get("accounts", []) if a["account"] == account]
        return accounts or [self.config.get("fallback", {})]

    def _group_candidates_by_account(
        self, candidates: List[Transaction]
    ) -> Dict[str, List[Transaction]]:
        grouped = {}
        for candidate in candidates:
            for split in candidate.splits:
                account_id = split.account_id
                if account_id not in grouped:
                    grouped[account_id] = []
                grouped[account_id].append(candidate)
        return grouped

    def _is_match(self, imported_txn: Transaction, candidate: Transaction, rules: Dict) -> bool:
        """Check if an imported transaction matches a candidate."""
        # Match amounts (negated) by iterating over all splits
        match_found = False
        for split in candidate.splits:
            if any(
                imported_split.account_id == split.account_id
                and imported_split.amount + split.amount == 0
                for imported_split in imported_txn.splits
            ):
                match_found = True
                break
        if not match_found:
            return False

        # Match description
        patterns = rules.get("description_patterns", [])
        if patterns:
            description = candidate.transaction_description
            for pattern in patterns:
                if re.match(pattern, description):
                    break
            else:  # No match for any pattern
                return False

        # Match date range
        date_offset = rules.get("date_offset", DEFAULT_DATE_OFFSET)
        date_diff = abs((imported_txn.transaction_date - candidate.transaction_date).days)
        if date_diff > date_offset:
            return False

        return True

    def _mark_matched(self, candidate: Transaction):
        """Update candidate to mark it as matched using TransactionService."""
        self.transaction_service.update_transaction(transaction_id=candidate.id, matched_status="m")

    def _add_transaction_to_ledger(self, txn: Transaction):
        """Add a new transaction to the ledger using TransactionService."""
        self.transaction_service.enter_transaction(
            book_name=txn.book_id,
            txn_date=txn.transaction_date.isoformat(),
            txn_desc=txn.transaction_description,
            # todo - should be passing the account name, not id
            # todo - 0th split is not necessarily the debit
            debit_acct=txn.splits[0].account_id,
            credit_acct=txn.splits[1].account_id,
            amount=txn.splits[0].amount,
        )
