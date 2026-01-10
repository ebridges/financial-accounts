"""
Utility for managing account statement file paths.

Convention: {year}/{account_slug}/{from_date}--{to_date}-{account_slug}.{ext}
Example: 2023/creditcard-chase-personal-6063/2022-12-29--2023-01-28-creditcard-chase-personal-6063.pdf
"""

from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
import re


@dataclass(frozen=True)
class AccountUri:
    """
    Immutable dataclass representing an account statement path.

    Parses paths like: 2023/creditcard-chase-personal-6063/2022-12-29--2023-01-28-creditcard-chase-personal-6063
    (stored without file extension)
    """

    path: Path

    def __post_init__(self):
        """Validate the path format during initialization."""
        if not self.is_valid_path():
            raise ValueError(f"Invalid path format: {self.path}")

    def is_valid_path(self) -> bool:
        """Validate that the path matches expected format."""
        try:
            self.parse_components()
            return True
        except (ValueError, IndexError, AttributeError):
            return False

    def parse_components(self) -> tuple[str, str, date, date]:
        """Parse path components and return (year, account_slug, from_date, to_date)."""
        parts = self.path.parts
        if len(parts) < 3:
            raise ValueError("Path must have at least 3 components (year/account/filename)")

        year, account_slug, filename = parts[-3], parts[-2], parts[-1]
        match = re.match(r'^(\d{4}-\d{2}-\d{2})--(\d{4}-\d{2}-\d{2})-(.+)$', filename)
        if not match:
            raise ValueError(f"Filename does not match expected format: {filename}")

        from_date_str, to_date_str, filename_account_slug = match.groups()
        if filename_account_slug != account_slug:
            raise ValueError(f"Account slug mismatch: {filename_account_slug} != {account_slug}")
        if not re.match(r'^\d{4}$', year):
            raise ValueError(f"Invalid year format: {year}")

        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError as e:
            raise ValueError(f"Invalid date format: {e}")

        return year, account_slug, from_date, to_date

    @property
    def year(self) -> int:
        """Get the year component as an integer."""
        return int(self.parse_components()[0])

    @property
    def account_slug(self) -> str:
        """Get the account slug component."""
        return self.parse_components()[1]

    @property
    def from_date(self) -> date:
        """Get the from date as a date object."""
        return self.parse_components()[2]

    @property
    def to_date(self) -> date:
        """Get the to date as a date object."""
        return self.parse_components()[3]

    def pdf(self) -> Path:
        """Get the path to the PDF file."""
        return self.path.with_suffix('.pdf')

    def json(self) -> Path:
        """Get the path to the JSON file."""
        return self.path.with_suffix('.json')

    @classmethod
    def from_path(cls, path: Path) -> 'AccountUri':
        """Create an AccountUri from a Path object, removing any file extension."""
        if path.suffix in ['.pdf', '.json', '.qif']:
            path = path.with_suffix('')
        return cls(path)

    @classmethod
    def from_string(cls, path_str: str) -> 'AccountUri':
        """Create an AccountUri from a path string, removing any file extension."""
        return cls.from_path(Path(path_str))

    @classmethod
    def from_components(
        cls, year: int, account_slug: str, from_date: date, to_date: date
    ) -> 'AccountUri':
        """Create an AccountUri from individual components."""
        if not re.match(r'^\d{4}$', str(year)):
            raise ValueError(f"Invalid year format: {year}")

        path_str = (
            f"{year}/{account_slug}/"
            f"{from_date.isoformat()}--{to_date.isoformat()}-{account_slug}"
        )
        return cls(Path(path_str))

    def __str__(self) -> str:
        """String representation."""
        return f"AccountUri({self.path})"

    def __repr__(self) -> str:
        """Detailed string representation."""
        return (
            f"AccountUri(path={self.path}, "
            f"account={self.account_slug}, from={self.from_date}, to={self.to_date})"
        )
