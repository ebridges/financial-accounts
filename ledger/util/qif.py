# from typing import List
from datetime import datetime
from decimal import Decimal
from collections import OrderedDict
from ledger.db.models import Transaction, Split

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

    def as_transactions(self, book_id, account_service):
        """Legacy method for backward compatibility - creates transactions with account resolution"""
        transaction_data = self.as_transaction_data(book_id)
        transactions = []
        
        for data in transaction_data:
            transaction = Transaction()
            transaction.book_id = data['book_id']
            transaction.transaction_date = data['transaction_date']
            transaction.transaction_description = data['transaction_description']
            
            transaction.splits = []
            for split_data in data['splits']:
                split = Split()
                # Resolve account within the same context as the caller
                split.account = account_service.lookup_account_by_name(book_id, split_data['account_name'])
                split.account_id = split.account.id
                split.amount = split_data['amount']
                # Note: Don't set split.transaction as it auto-appends via SQLAlchemy backref
                transaction.splits.append(split)
            
            transactions.append(transaction)
        return transactions
