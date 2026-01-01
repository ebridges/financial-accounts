import json
import re
from datetime import timedelta, date
from typing import List, Tuple, Iterator, Optional
from logging import info

from ledger.config import MATCHING_RULES_PATH
from ledger.business.base_service import BaseService
from ledger.db.models import Transaction, Account
from ledger.util.qif import Qif

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

    def __init__(self, rules_path: str = MATCHING_RULES_PATH):
        with open(rules_path, 'r') as file:
            self.rules = json.load(fp=file)

    def matchable_accounts(self, account: Account) -> set:
        return self.rules["matching_rules"].get(account.full_name, {}).keys()

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
    def __init__(self, matching_rules: MatchingRules):
        self.rules = matching_rules

    def compute_candidate_date_range(
        self, to_import: List[Transaction]
    ) -> Tuple[date, date]:
        """
        Calculate the date range (with buffer) to query potential candidate transactions.
        Caller should use this to fetch candidates efficiently.
        """
        if not to_import:
            return date.today(), date.today()

        min_date = min(txn.transaction_date for txn in to_import)
        max_date = max(txn.transaction_date for txn in to_import)
        
        buffer = timedelta(days=DEFAULT_DATE_OFFSET)
        return min_date - buffer, max_date + buffer

    def get_matchable_accounts(self, import_for: Account) -> List[str]:
        return self.rules.matchable_accounts(import_for)

    def match_transactions(
        self,
        import_for: Account,
        to_import: List[Transaction],
        candidates: List[Transaction],
    ) -> Iterator[Tuple[str, Transaction]]:
        """
        Generator that yields decisions for each imported transaction.
        
        Yields tuples of:
        - ('match', existing_transaction)   → mark this existing tx as matched
        - ('import', new_transaction)       → insert this transaction as new

        Order of yields generally follows order of `to_import`.
        """
        matchable_accounts = self.get_matchable_accounts(import_for)
        if not matchable_accounts:
            for txn in to_import:
                yield ('import', txn)
            return
        
        for txn_import in to_import:
            matched = False

            for txn_candidate in candidates:
                if self.is_match(import_for, txn_import, txn_candidate):
                    yield ('match', txn_candidate)
                    matched = True
                    break

            if not matched:
                yield ('import', txn_import)
    
    
    def is_match(
        self,
        import_for: Account,
        txn_import: Transaction,
        txn_candidate: Transaction
    ) -> bool:
        """
        Core matching logic between one imported transaction and one candidate.
        Returns True if they should be considered a match.
        """
        # 1. Check split equality (accounts + amounts must match exactly)
        if self.compare_splits(txn_import, txn_candidate) is None:
            return False

        # 2. Get the corresponding (counterparty) account from the imported transaction
        #    → this is the key we use to look up account-specific matching rules
        corresponding_account = txn_import.corresponding_account(import_for)

        # 3. Check description against allowed patterns for this counterparty
        patterns = self.rules.matching_patterns(import_for, corresponding_account)
        
        description = txn_candidate.transaction_description or ""
        description_matched = any(re.match(pattern, description) for pattern in patterns)

        if not description_matched:
            return False

        # 3. Check date proximity
        date_offset = self.rules.matching_date_offset(import_for, corresponding_account)
        date_diff = abs((txn_import.transaction_date - txn_candidate.transaction_date).days)

        if date_diff > date_offset:
            return False

        return True

    @staticmethod
    def compare_splits(imported: Transaction, candidate: Transaction) -> Optional[Transaction]:
        """
        Returns the candidate if all its splits match imported transaction splits
        by (account_id, amount), otherwise None.
        """
        if len(candidate.splits) != len(imported.splits):
            return None

        imported_set = {(s.account_id, s.amount) for s in imported.splits}

        for cs in candidate.splits:
            if (cs.account_id, cs.amount) not in imported_set:
                return None

        return candidate
