import re
from datetime import timedelta
from typing import List, Dict

from financial_accounts.business.base_service import BaseService
from financial_accounts.business.transaction_service import TransactionService


class MatchingService(BaseService):
    def __init__(self, config_path: str, transaction_service: TransactionService):
        super().__init__(transaction_service.data_access)
        self.config = self._load_config(config_path)
        self.transaction_service = transaction_service

    def _load_config(self, config_path: str) -> Dict:
        """Load JSON configuration for matching criteria."""
        import json

        with open(config_path, 'r') as file:
            return json.load(file)

    def _get_account_rules(self, account_id: str) -> Dict:
        """Retrieve account-specific matching rules, falling back to defaults."""
        accounts = {a["account_id"]: a for a in self.config.get("accounts", [])}
        return accounts.get(account_id, self.config.get("fallback", {}))

    def batch_query_candidates(self, book_id: str, imported_transactions: List[Dict]) -> List:
        """
        Query candidate transactions for all imported transactions in batch.
        """
        # Determine global date range for the batch
        min_date = min(txn["date"] for txn in imported_transactions)
        max_date = max(txn["date"] for txn in imported_transactions)
        buffer_days = self.config["global_defaults"].get("date_offset", 2)
        min_date -= timedelta(days=buffer_days)
        max_date += timedelta(days=buffer_days)

        # Query candidates from the TransactionService
        return self.transaction_service.get_transactions_in_range(
            book_id=book_id,
            start_date=min_date,
            end_date=max_date,
            recon_status=None,  # Only unmatched transactions
        )

    def match_transactions(self, imported_transactions: List[Dict], book_id: str) -> None:
        """
        Match imported transactions against candidates in memory.
        """
        # Batch query all candidates
        candidates = self.batch_query_candidates(book_id, imported_transactions)

        # Cache candidates in a dictionary grouped by account
        candidate_cache = self._group_candidates_by_account(candidates)

        for txn in imported_transactions:
            account_id = txn["account_id"]
            rules = self._get_account_rules(account_id)
            corresponding_accounts = rules.get("corresponding_accounts", [])
            matched = False

            # Match against candidates for corresponding accounts
            for other_account_id in corresponding_accounts:
                if other_account_id not in candidate_cache:
                    continue
                potential_matches = candidate_cache[other_account_id]
                for candidate in potential_matches:
                    if self._is_match(txn, candidate, rules):
                        self._mark_matched(candidate)
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                self._add_transaction_to_ledger(txn)

    def _group_candidates_by_account(self, candidates: List) -> Dict[str, List]:
        """Group candidates by account for quick access."""
        grouped = {}
        for candidate in candidates:
            account_id = candidate.splits[0].account_id
            if account_id not in grouped:
                grouped[account_id] = []
            grouped[account_id].append(candidate)
        return grouped

    def _is_match(self, imported_txn: Dict, candidate, rules: Dict) -> bool:
        """Check if an imported transaction matches a candidate."""
        # Match amounts (negated)
        if not rules.get("match_by_amount", True):
            return False
        if imported_txn["amount"] + candidate.splits[0].amount != 0:
            return False

        # Match description
        patterns = rules.get("description_patterns", [])
        if patterns:
            description = candidate.transaction_description
            if rules.get("ignore_case", False):
                description = description.lower()
            for pattern in patterns:
                if re.match(pattern, description):
                    return True

        # Match date range
        date_offset = rules.get("date_offset", 2)
        date_diff = abs((imported_txn["date"] - candidate.transaction_date).days)
        if date_diff > date_offset:
            return False

        return True

    def _mark_matched(self, candidate):
        """Update candidate to mark it as matched using TransactionService."""
        self.transaction_service.update_transaction(transaction_id=candidate.id, matched_status="m")

    def _add_transaction_to_ledger(self, txn: Dict):
        """Add a new transaction to the ledger using TransactionService."""
        self.transaction_service.enter_transaction(
            book_name=txn["book_id"],
            txn_date=txn["date"].isoformat(),
            txn_desc=txn["description"],
            debit_acct=txn["debit_account"],
            credit_acct=txn["credit_account"],
            amount=txn["amount"],
        )
