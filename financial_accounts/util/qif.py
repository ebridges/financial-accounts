# from typing import List
from datetime import datetime
from collections import OrderedDict
from financial_accounts.db.models import Transaction, Split

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

    def as_transactions(self, book_id, account_service):
        from_account = self.account_info[AcctName]
        transactions = []
        for txn in self.transactions:
            transaction = Transaction()
            transaction.book_id = book_id
            txn_date = datetime.strptime(txn.get(TxnDate), "%m/%d/%Y").date()
            transaction.transaction_date = txn_date
            transaction.transaction_description = txn.get(TxnPayee)

            transaction.splits = []
            split = Split()
            split.transaction = transaction
            split.account = account_service.lookup_account_by_name(book_id, from_account)
            split.amount = txn.get(TxnAmount)
            transaction.splits.append(split)

            split = Split()
            split.transaction = transaction
            split.account = account_service.lookup_account_by_name(book_id, txn.get(TxnCategory))
            split.amount = txn.get(TxnAmount) * -1
            transaction.splits.append(split)

            transactions.append(transaction)
        return transactions
