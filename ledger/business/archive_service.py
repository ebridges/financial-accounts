# archive_service.py
"""
Archive service for storing imported financial files.

Handles archiving of CSV, QIF, and PDF files with a consistent path convention:
    {ARCHIVE_BASE_PATH}/{yyyy}/{account-slug}/{stmt-opening-date}--{stmt-closing-date}-{account-slug}.{ext}

Examples:
    - 2024/checking-chase-personal-1381/2024-01-10--2024-02-08-checking-chase-personal-1381.csv
    - 2024/checking-chase-personal-1381/2024-01-10--2024-02-08-checking-chase-personal-1381.qif
    - 2024/checking-chase-personal/2024-01-10--2024-02-08-checking-chase-personal.pdf (combined checking)
    - 2024/creditcard-chase-personal-6063/2024-02-28--2024-03-28-creditcard-chase-personal-6063.pdf
"""
import os
import shutil
from datetime import date
from typing import Optional, Tuple

from ledger.config import ARCHIVE_BASE_PATH


class ArchiveService:
    """
    Service for archiving imported financial files.
    
    This is a stateless utility service that doesn't require database access.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the archive service.
        
        Args:
            base_path: Base path for archives. Defaults to ARCHIVE_BASE_PATH config.
        """
        self.base_path = base_path or ARCHIVE_BASE_PATH
    
    def generate_archive_path(
        self,
        account_slug: str,
        coverage_start: date,
        coverage_end: date,
        extension: str,
    ) -> str:
        """
        Generate the archive path for a file.
        
        Args:
            account_slug: Account identifier (e.g., 'checking-chase-personal-1381')
            coverage_start: Statement/coverage period start date
            coverage_end: Statement/coverage period end date
            extension: File extension without dot (e.g., 'csv', 'qif', 'pdf')
        
        Returns:
            Full archive path relative to base_path
        """
        year = str(coverage_start.year)
        start_str = coverage_start.strftime('%Y-%m-%d')
        end_str = coverage_end.strftime('%Y-%m-%d')
        filename = f"{start_str}--{end_str}-{account_slug}.{extension}"
        
        return os.path.join(self.base_path, year, account_slug, filename)
    
    def generate_pdf_archive_path(
        self,
        account_slug: str,
        coverage_start: date,
        coverage_end: date,
        is_combined_checking: bool = False,
    ) -> str:
        """
        Generate the archive path for a PDF statement.
        
        Chase checking accounts come in a combined statement, while credit cards
        have individual statements.
        
        Args:
            account_slug: Account identifier
            coverage_start: Statement period start date
            coverage_end: Statement period end date
            is_combined_checking: If True, uses 'checking-chase-personal' folder
        
        Returns:
            Full archive path for the PDF
        """
        year = str(coverage_start.year)
        start_str = coverage_start.strftime('%Y-%m-%d')
        end_str = coverage_end.strftime('%Y-%m-%d')
        
        if is_combined_checking:
            # Combined checking statements use generic folder
            folder_slug = self._get_combined_checking_slug(account_slug)
            filename = f"{start_str}--{end_str}-{folder_slug}.pdf"
            folder = folder_slug
        else:
            # Credit card statements are account-specific
            filename = f"{start_str}--{end_str}-{account_slug}.pdf"
            folder = account_slug
        
        return os.path.join(self.base_path, year, folder, filename)
    
    def _get_combined_checking_slug(self, account_slug: str) -> str:
        """
        Extract the combined checking slug from an account slug.
        
        'checking-chase-personal-1381' -> 'checking-chase-personal'
        """
        # Remove trailing account number
        parts = account_slug.rsplit('-', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return account_slug
    
    def archive_file(
        self,
        source_path: str,
        account_slug: str,
        coverage_start: date,
        coverage_end: date,
        extension: Optional[str] = None,
    ) -> str:
        """
        Copy a file to the archive.
        
        Args:
            source_path: Path to the source file
            account_slug: Account identifier
            coverage_start: Coverage period start date
            coverage_end: Coverage period end date
            extension: File extension (inferred from source if not provided)
        
        Returns:
            The archive path where the file was stored
        """
        if extension is None:
            extension = os.path.splitext(source_path)[1].lstrip('.')
        
        archive_path = self.generate_archive_path(
            account_slug, coverage_start, coverage_end, extension
        )
        
        # Create directory structure
        archive_dir = os.path.dirname(archive_path)
        os.makedirs(archive_dir, exist_ok=True)
        
        # Copy file
        shutil.copy2(source_path, archive_path)
        
        return archive_path
    
    def archive_content(
        self,
        content: str,
        account_slug: str,
        coverage_start: date,
        coverage_end: date,
        extension: str,
    ) -> str:
        """
        Write content directly to the archive (e.g., converted QIF).
        
        Args:
            content: String content to write
            account_slug: Account identifier
            coverage_start: Coverage period start date
            coverage_end: Coverage period end date
            extension: File extension
        
        Returns:
            The archive path where the content was stored
        """
        archive_path = self.generate_archive_path(
            account_slug, coverage_start, coverage_end, extension
        )
        
        # Create directory structure
        archive_dir = os.path.dirname(archive_path)
        os.makedirs(archive_dir, exist_ok=True)
        
        # Write content
        with open(archive_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return archive_path
    
    def archive_csv_with_qif(
        self,
        csv_path: str,
        qif_content: str,
        account_slug: str,
        coverage_start: date,
        coverage_end: date,
    ) -> Tuple[str, str]:
        """
        Archive both the source CSV and its converted QIF representation.
        
        Args:
            csv_path: Path to the source CSV file
            qif_content: QIF string content (from ChaseCsvParser.to_qif_string())
            account_slug: Account identifier
            coverage_start: Coverage period start date
            coverage_end: Coverage period end date
        
        Returns:
            Tuple of (csv_archive_path, qif_archive_path)
        """
        csv_archive = self.archive_file(
            csv_path, account_slug, coverage_start, coverage_end, 'csv'
        )
        
        qif_archive = self.archive_content(
            qif_content, account_slug, coverage_start, coverage_end, 'qif'
        )
        
        return csv_archive, qif_archive
    
    def archive_pdf_statement(
        self,
        pdf_path: str,
        account_slug: str,
        coverage_start: date,
        coverage_end: date,
        is_combined_checking: bool = False,
    ) -> str:
        """
        Archive a PDF statement.
        
        Args:
            pdf_path: Path to the source PDF file
            account_slug: Account identifier
            coverage_start: Statement period start date
            coverage_end: Statement period end date
            is_combined_checking: If True, uses combined checking folder
        
        Returns:
            The archive path where the PDF was stored
        """
        archive_path = self.generate_pdf_archive_path(
            account_slug, coverage_start, coverage_end, is_combined_checking
        )
        
        # Create directory structure
        archive_dir = os.path.dirname(archive_path)
        os.makedirs(archive_dir, exist_ok=True)
        
        # Copy file
        shutil.copy2(pdf_path, archive_path)
        
        return archive_path
    
    def get_account_slug_from_full_name(self, account_full_name: str) -> str:
        """
        Extract account slug from full account name.
        
        'Assets:Checking Accounts:checking-chase-personal-1381' -> 'checking-chase-personal-1381'
        'Liabilities:Credit Cards:creditcard-chase-personal-6063' -> 'creditcard-chase-personal-6063'
        """
        return account_full_name.split(':')[-1]
    
    def is_checking_account(self, account_slug: str) -> bool:
        """Check if an account slug represents a checking account."""
        return account_slug.startswith('checking-')
    
    def is_credit_card_account(self, account_slug: str) -> bool:
        """Check if an account slug represents a credit card account."""
        return account_slug.startswith('creditcard-')

