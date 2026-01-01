from typing import Callable, Optional
from datetime import datetime
from decimal import Decimal
from collections import OrderedDict
from ledger.db.models import Transaction, Split, Account

AcctHeader = '!Account'
AcctName = 'N'
AcctType = 'T'
TxnHeader = '!Type'
RecordBegin = 'C'
TxnDate = 'D'
TxnCheckNumber = 'N'
TxnPayee = 'P'
TxnAmount = 'T'
TxnCategory = 'L'
RecordEnd = '^'

NEG_ONE = Decimal("-1")


class Qif:
    def __init__(self):
        self.account_info = OrderedDict()
        self.transaction_type = None
        self.transactions = []  # List[Transaction]

    def init_from_qif_file(self, qif_file):
        with open(qif_file, 'r') as file:
            data = file.readlines()
        return self.init_from_qif_data(data)

    def init_from_qif_data(self, qif_data):
        in_account_section = False
        current_transaction = OrderedDict()
        for line in qif_data:
            line = line.strip()
            if not line:
                continue

            if line == AcctHeader:
                in_account_section = True
                self.account_info = OrderedDict()
                self.account_info[line] = ''
            elif line.startswith(TxnHeader):
                self.transaction_type = line.split(':')[1]
            elif line == RecordEnd:  # end of section or transaction
                if in_account_section:
                    self.account_info[RecordEnd] = ''
                    in_account_section = False
                else:
                    current_transaction[RecordEnd] = ''
                    self.transactions.append(current_transaction)
                    current_transaction = OrderedDict()
            else:
                line_type = line[0]
                line_data = line[1:].strip()
                if in_account_section:
                    self.account_info[line_type] = line_data
                else:
                    current_transaction[line_type] = line_data
        return self

    @staticmethod
    def get_category(txn: OrderedDict) -> str:
        if TxnCategory in txn and txn[TxnCategory] and txn[TxnCategory].strip():
            return txn[TxnCategory]
        else:
            return None

    @staticmethod
    def set_category(txn: OrderedDict, category_account: str) -> None:
        if category_account:
            txn[TxnCategory] = category_account

    @staticmethod
    def get_payee(txn: OrderedDict) -> str:
        return txn.get(TxnPayee)

    def as_transaction_data(self, book_id):
        """Convert QIF data to transaction data with account names (not objects)"""
        from_account = self.account_info[AcctName]
        transaction_data = []
        for txn in self.transactions:
            txn_date = datetime.strptime(txn.get(TxnDate), "%m/%d/%Y").date()
            txn_amount = Decimal(txn.get(TxnAmount).strip())
            
            data = {
                'book_id': book_id,
                'transaction_date': txn_date,
                'transaction_description': txn.get(TxnPayee),
                'splits': [
                    {
                        'account_name': from_account,
                        'amount': txn_amount
                    },
                    {
                        'account_name': txn.get(TxnCategory),
                        'amount': txn_amount * NEG_ONE
                    }
                ]
            }
            transaction_data.append(data)
        return transaction_data

    def as_transactions(
        self,
        book_id: int,
        resolve_account: Callable[[int, str], Optional[Account]]
    ) -> list:
        """
        Convert QIF data to Transaction objects.
        
        Args:
            book_id: Book ID for the transactions
            resolve_account: Callback (book_id, account_name) -> Account
                             Should raise or return None if account not found.
        
        Returns:
            List of Transaction objects with resolved accounts
        """
        transaction_data = self.as_transaction_data(book_id)
        transactions = []
        
        for data in transaction_data:
            transaction = Transaction()
            transaction.book_id = data['book_id']
            transaction.transaction_date = data['transaction_date']
            transaction.transaction_description = data['transaction_description']
            
            transaction.splits = []
            for split_data in data['splits']:
                account_name = split_data['account_name']
                account = resolve_account(book_id, account_name)
                if not account:
                    raise ValueError(
                        f"Account '{account_name}' not found for transaction "
                        f"'{data['transaction_description']}'"
                    )
                
                split = Split()
                split.account = account
                split.account_id = account.id
                split.amount = split_data['amount']
                transaction.splits.append(split)
            
            transactions.append(transaction)
        return transactions
