# chase_csv.py
"""
Chase CSV parser for checking and credit card account exports.

Chase CSV formats differ by account type:
- Checking: Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #
- Credit Card: Transaction Date,Post Date,Description,Category,Type,Amount,Memo

This module parses both formats and converts them to the same transaction data
structure used by the QIF parser for compatibility with existing import logic.
"""
import csv
import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional
from collections import OrderedDict

from ledger.config import UNCATEGORIZED_ACCOUNT


class ChaseCsvParser:
    """
    Parser for Chase CSV exports.
    
    Mirrors the Qif class interface for compatibility with existing import flow.
    """
    
    # Chase CSV column names by account type
    CHECKING_COLUMNS = ['Details', 'Posting Date', 'Description', 'Amount', 'Type', 'Balance', 'Check or Slip #']
    CREDIT_COLUMNS = ['Transaction Date', 'Post Date', 'Description', 'Category', 'Type', 'Amount', 'Memo']
    
    def __init__(self):
        self.account_info = OrderedDict()
        self.account_type = None  # 'checking' or 'credit'
        self.transactions = []  # List of raw transaction dicts
        self.source_path = None
    
    def init_from_csv_file(self, csv_file: str, account_full_name: str):
        """
        Parse a Chase CSV file.
        
        Args:
            csv_file: Path to the CSV file
            account_full_name: Full account name (e.g., 'Assets:Checking Accounts:checking-chase-personal-1381')
        """
        self.source_path = csv_file
        self.account_info['N'] = account_full_name
        
        with open(csv_file, 'r', encoding='utf-8-sig') as file:
            # Read header to detect account type
            reader = csv.reader(file)
            header = next(reader)
            
            # Detect account type from header
            if 'Posting Date' in header:
                self.account_type = 'checking'
                self._parse_checking_csv(header, reader)
            elif 'Post Date' in header:
                self.account_type = 'credit'
                self._parse_credit_csv(header, reader)
            else:
                raise ValueError(f"Unrecognized Chase CSV format. Header: {header}")
        
        # Set account type in account_info for QIF compatibility
        self.account_info['T'] = 'Bank' if self.account_type == 'checking' else 'CCard'
        
        return self
    
    def _parse_checking_csv(self, header: List[str], reader):
        """Parse Chase checking account CSV format."""
        col_idx = {col: i for i, col in enumerate(header)}
        
        for row in reader:
            if not row or len(row) < len(header):
                continue
            
            # Parse date (MM/DD/YYYY format)
            date_str = row[col_idx['Posting Date']]
            description = row[col_idx['Description']]
            amount_str = row[col_idx['Amount']]
            txn_type = row[col_idx.get('Type', '')] if 'Type' in col_idx else ''
            
            self.transactions.append({
                'date': date_str,
                'description': description,
                'amount': amount_str,
                'type': txn_type,
                'payee_raw': description,
            })
    
    def _parse_credit_csv(self, header: List[str], reader):
        """Parse Chase credit card CSV format."""
        col_idx = {col: i for i, col in enumerate(header)}
        
        for row in reader:
            if not row or len(row) < len(header):
                continue
            
            # Use Post Date for consistency with checking
            date_str = row[col_idx['Post Date']]
            description = row[col_idx['Description']]
            amount_str = row[col_idx['Amount']]
            category = row[col_idx.get('Category', '')] if 'Category' in col_idx else ''
            txn_type = row[col_idx.get('Type', '')] if 'Type' in col_idx else ''
            memo = row[col_idx.get('Memo', '')] if 'Memo' in col_idx else ''
            
            self.transactions.append({
                'date': date_str,
                'description': description,
                'amount': amount_str,
                'type': txn_type,
                'category': category,
                'memo': memo,
                'payee_raw': description,
            })
    
    def as_transaction_data(self, book_id: int, category_account: Optional[str] = None) -> List[Dict]:
        """
        Convert CSV data to transaction data dicts compatible with QIF import.
        
        Args:
            book_id: The book ID for transactions
            category_account: Default category account for counter-splits.
                              If None, uses UNCATEGORIZED_ACCOUNT.
        
        Returns:
            List of transaction data dicts with structure:
            {
                'book_id': int,
                'transaction_date': date,
                'transaction_description': str,
                'payee_norm': str,  # normalized payee for categorization
                'splits': [
                    {'account_name': str, 'amount': Decimal},
                    {'account_name': str, 'amount': Decimal},
                ]
            }
        """
        from_account = self.account_info['N']
        default_category = category_account or UNCATEGORIZED_ACCOUNT
        transaction_data = []
        
        for txn in self.transactions:
            # Parse date - Chase uses MM/DD/YYYY
            try:
                txn_date = datetime.strptime(txn['date'], "%m/%d/%Y").date()
            except ValueError:
                # Try alternate format
                txn_date = datetime.strptime(txn['date'], "%Y-%m-%d").date()
            
            # Parse amount - Chase credit card amounts are negative for purchases
            amount_str = txn['amount'].replace(',', '').strip()
            txn_amount = Decimal(amount_str)
            
            # For credit cards, Chase uses negative for purchases, positive for payments/credits
            # This matches the double-entry convention where:
            # - Purchases: Debit Expense, Credit Liability (payment to vendor)
            # - Payments: Debit Liability, Credit Asset (paying off card)
            
            # Normalize payee for categorization cache
            payee_norm = self.normalize_payee(txn['description'])
            
            # Use category from CSV if available (credit cards only), otherwise default
            counter_account = default_category
            if txn.get('category') and txn['category'].strip():
                # Chase categories are rough hints, not our account hierarchy
                # We'll use the categorization service to map these properly
                pass
            
            data = {
                'book_id': book_id,
                'transaction_date': txn_date,
                'transaction_description': txn['description'],
                'payee_norm': payee_norm,
                'splits': [
                    {
                        'account_name': from_account,
                        'amount': txn_amount
                    },
                    {
                        'account_name': counter_account,
                        'amount': txn_amount * Decimal("-1")
                    }
                ]
            }
            transaction_data.append(data)
        
        return transaction_data
    
    def get_coverage_dates(self):
        """
        Get the date range covered by transactions in this file.
        
        Returns:
            Tuple of (start_date, end_date) or (None, None) if no transactions
        """
        if not self.transactions:
            return None, None
        
        dates = []
        for txn in self.transactions:
            try:
                d = datetime.strptime(txn['date'], "%m/%d/%Y").date()
                dates.append(d)
            except ValueError:
                try:
                    d = datetime.strptime(txn['date'], "%Y-%m-%d").date()
                    dates.append(d)
                except ValueError:
                    continue
        
        if not dates:
            return None, None
        
        return min(dates), max(dates)
    
    @staticmethod
    def normalize_payee(description: str) -> str:
        """
        Normalize a payee description for categorization matching.
        
        Normalization steps:
        - Uppercase
        - Collapse whitespace
        - Strip trailing transaction IDs, card numbers, dates
        - Remove common suffixes (city/state abbreviations often appended)
        
        Args:
            description: Raw payee/description string
            
        Returns:
            Normalized payee string
        """
        if not description:
            return ""
        
        payee = description.upper().strip()
        
        # Collapse multiple whitespace to single space
        payee = re.sub(r'\s+', ' ', payee)
        
        # Remove trailing transaction numbers (e.g., "PPD ID: 1234567890")
        payee = re.sub(r'\s+PPD ID:\s*\d+$', '', payee)
        
        # Remove trailing transaction# references (must be before card number strip)
        payee = re.sub(r'\s+TRANSACTION#:\s*\d+.*$', '', payee, flags=re.IGNORECASE)
        
        # Remove trailing reference numbers (generic alphanumeric)
        payee = re.sub(r'\s+#?\d{6,}$', '', payee)
        
        # Remove trailing card numbers (e.g., "XXXX1234" or "...1234")
        payee = re.sub(r'\s+(?:XXXX|\.\.\.)?\d{4}$', '', payee)
        
        # Remove trailing dates (e.g., "07/14" or "07/14/2024")
        payee = re.sub(r'\s+\d{2}/\d{2}(?:/\d{2,4})?$', '', payee)
        
        # Strip again after removals
        payee = payee.strip()
        
        return payee
    
    def to_qif_string(self) -> str:
        """
        Convert the parsed CSV data to QIF format string.
        
        This is used for archiving the converted QIF alongside the source CSV.
        
        Returns:
            QIF formatted string
        """
        lines = []
        
        # Account header
        lines.append('!Account')
        lines.append(f"N{self.account_info['N']}")
        lines.append(f"T{self.account_info.get('T', 'Bank')}")
        lines.append('^')
        
        # Transaction type header
        txn_type = 'Bank' if self.account_type == 'checking' else 'CCard'
        lines.append(f'!Type:{txn_type}')
        
        # Transactions
        for txn in self.transactions:
            lines.append('C')  # Cleared status placeholder
            
            # Date - convert to MM/DD/YYYY if needed
            date_str = txn['date']
            try:
                d = datetime.strptime(date_str, "%m/%d/%Y")
                lines.append(f"D{date_str}")
            except ValueError:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                lines.append(f"D{d.strftime('%m/%d/%Y')}")
            
            lines.append('NN/A')  # Check number placeholder
            lines.append(f"P{txn['description']}")
            lines.append(f"T{txn['amount']}")
            lines.append('^')
        
        return '\n'.join(lines)

