import unittest
from unittest.mock import MagicMock
from datetime import date
from financial_accounts.business.matching_service import MatchingService
from financial_accounts.business.transaction_service import TransactionService
from financial_accounts.db.models import Transactions, Split

class TestMatchingService(unittest.TestCase):
    def setUp(self):
        # Mock TransactionService
        self.mock_transaction_service = MagicMock(spec=TransactionService)
        self.mock_transaction_service.get_transactions_in_range.return_value = []

        # Create MatchingService instance with mock config and transaction service
        self.matching_service = MatchingService(
            config_path='matching-config.json',
            transaction_service=self.mock_transaction_service
        )

    def test_import_transactions_no_candidates(self):
        # Prepare test data
        book_id = "test_book_id"
        import_for_account = "test_account"
        to_import = [
            Transactions(
                id="txn1",
                book_id=book_id,
                transaction_date=date(2025, 1, 1),
                transaction_description="Test Transaction",
                splits=[
                    Split(account_id="acct1", amount=100),
                    Split(account_id="acct2", amount=-100)
                ]
            )
        ]

        # Call import_transactions
        self.matching_service.import_transactions(book_id, import_for_account, to_import)

        # Assert that enter_transaction was called since there are no candidates
        self.mock_transaction_service.enter_transaction.assert_called_once_with(
            book_name=book_id,
            txn_date="2025-01-01",
            txn_desc="Test Transaction",
            debit_acct="acct1",
            credit_acct="acct2",
            amount=100
        )

if __name__ == '__main__':
    unittest.main()
