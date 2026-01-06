from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from logging import getLogger

from ledger.db.models import Transaction, Split, Account
from ledger.util.normalize import normalize_payee
from ledger.util.transfer import extract_transfer_reference

logger = getLogger(__name__)

AcctHeader = '!Account'
AcctName = 'N'
AcctType = 'T'
TxnHeader = '!Type'
RecordBegin = 'C'
TxnDate = 'D'
TxnCheckNumber = 'N'
TxnPayee = 'P'
TxnPayeeNorm = 'B' # normalized payee, non-standard field
TxnAmount = 'T'
TxnCategory = 'L'
RecordEnd = '^'

NEG_ONE = Decimal("-1")

DATE_FORMATS = ["%m/%d/%Y", "%m-%d-%Y"]


def parse_qif_date(date_str: str):
    """Parse a QIF date string, trying multiple formats."""
    for fmt in DATE_FORMATS:
        try:
            result = datetime.strptime(date_str, fmt).date()
            logger.debug(f"Parsed date '{date_str}' using format '{fmt}'")
            return result
        except ValueError:
            continue
    logger.warning(f"Date '{date_str}' does not match any supported format: {DATE_FORMATS}")
    raise ValueError(f"Date '{date_str}' does not match any supported format: {DATE_FORMATS}")


class Qif:
    def __init__(self):
        self.account_info = OrderedDict()
        self.transaction_type = None
        self.transactions = []  # list[Transaction]

    def init_from_qif_file(self, qif_file):
        logger.debug(f"Reading QIF file: {qif_file}")
        with open(qif_file, 'r') as file:
            data = file.readlines()
        logger.debug(f"Read {len(data)} lines from file")
        return self.init_from_qif_data(data)

    def init_from_qif_data(self, qif_data):
        logger.debug("Parsing QIF data")
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
                logger.debug(f"Transaction type: {self.transaction_type}")
            elif line == RecordEnd:  # end of section or transaction
                if in_account_section:
                    self.account_info[RecordEnd] = ''
                    in_account_section = False
                    logger.debug(f"Parsed account section: {self.account_info.get(AcctName, 'unknown')}")
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
                    if line_type == TxnPayee:
                        current_transaction[TxnPayeeNorm] = normalize_payee(line_data)
        
        logger.debug(f"Parsed {len(self.transactions)} transactions")
        return self

    def account(self) -> str:
        return self.account_info[AcctName]

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
    def payee(txn: OrderedDict) -> str:
        return txn.get(TxnPayee)

    @staticmethod
    def normalized_payee(txn: OrderedDict) -> str:
        return txn[TxnPayeeNorm]

    def as_transaction_data(self, book_id):
        """Convert QIF data to transaction data with account names (not objects)"""
        from_account = self.account_info[AcctName]
        transaction_data = []
        for txn in self.transactions:
            txn_date = parse_qif_date(txn.get(TxnDate))
            txn_amount = Decimal(txn.get(TxnAmount).strip())
            
            data = {
                'book_id': book_id,
                'transaction_date': txn_date,
                'transaction_description': txn.get(TxnPayee),
                'payee_norm': txn.get(TxnPayeeNorm),
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
        self, book_id: int, resolve_account: Callable[[str], Account]
    ) -> list:
        """
        Convert QIF data to Transaction objects.
        
        Args:
            book_id: Book ID for the transactions
            resolve_account: Callback (account_name) -> Account
        
        Returns:
            List of Transaction objects with resolved accounts
        """
        logger.debug(f"Converting {len(self.transactions)} QIF records to Transaction objects")
        transaction_data = self.as_transaction_data(book_id)
        transactions = []
        
        for data in transaction_data:
            transaction = Transaction()
            transaction.book_id = data['book_id']
            transaction.transaction_date = data['transaction_date']
            transaction.transaction_description = data['transaction_description']
            transaction.payee_norm = data['payee_norm']
            
            # Extract transfer_reference from Chase checking transfer descriptions
            transaction.transfer_reference = extract_transfer_reference(
                data['transaction_description']
            )
            
            transaction.splits = []
            for split_data in data['splits']:
                split = Split()
                account = resolve_account(split_data['account_name'])
                if not account:
                    logger.error(f"Account '{split_data['account_name']}' not found")
                    raise ValueError(f"Account '{split_data['account_name']}' not found")
                # Only set account_id (foreign key), NOT account (relationship)
                # Setting split.account triggers bidirectional relationship which causes
                # SAWarning when Split is not yet in session
                split.account_id = account.id
                # Store account as transient attribute for matching (not persisted)
                split._account_cache = account
                split.amount = split_data['amount']
                transaction.splits.append(split)
            
            transactions.append(transaction)
        
        logger.debug(f"Created {len(transactions)} Transaction objects")
        return transactions
