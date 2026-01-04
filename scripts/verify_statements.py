#!/usr/bin/env python3
"""
Verification script for statement parsing and reconciliation.

Processes all PDF files under a test-files directory, attempting to:
1. Parse each PDF (extract dates/balances)
2. Import AccountStatement records
3. Run reconciliation against transactions

Generates a summary report to stdout and detailed JSON output.
"""
import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from sqlalchemy import create_engine

from ledger.business.book_context import BookContext
from ledger.business.statement_service import ImportResult
from ledger.db.models import Base
from ledger.util.statement_uri import AccountUri
from ledger.util.pdf_parser import StatementParseError, STATEMENT_PATTERNS


class ResultStatus(str, Enum):
    RECONCILED = "reconciled"
    DISCREPANCY = "discrepancy"
    PARSE_ERROR = "parse_error"
    IMPORT_ERROR = "import_error"
    SKIPPED = "skipped"


@dataclass
class VerificationResult:
    file_path: str
    status: ResultStatus
    account_slug: str = ""
    start_date: str = ""
    end_date: str = ""
    start_balance: str = ""
    end_balance: str = ""
    computed_end_balance: str = ""
    discrepancy: str = ""
    error_message: str = ""


@dataclass
class VerificationReport:
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    test_files_dir: str = ""
    book_name: str = ""
    total_pdfs: int = 0
    skipped: int = 0
    processed: int = 0
    reconciled: int = 0
    discrepancy: int = 0
    parse_error: int = 0
    import_error: int = 0
    results: list = field(default_factory=list)


def get_supported_account_prefixes() -> set[str]:
    """Get account type prefixes that have parser patterns."""
    return set(STATEMENT_PATTERNS.keys())


def is_supported_account(account_slug: str, supported_prefixes: set[str]) -> bool:
    """Check if account slug matches a supported parser pattern."""
    for prefix in supported_prefixes:
        if account_slug.startswith(prefix):
            return True
    return False


def find_pdf_files(test_files_dir: Path) -> list[Path]:
    """Find all PDF files under the test files directory."""
    return sorted(test_files_dir.rglob("*.pdf"))


def process_pdf(ctx: BookContext, pdf_path: Path, supported_prefixes: set[str]) -> VerificationResult:
    """Process a single PDF file through parsing, import, and reconciliation."""
    result = VerificationResult(file_path=str(pdf_path), status=ResultStatus.SKIPPED)

    try:
        uri = AccountUri.from_path(pdf_path)
        result.account_slug = uri.account_slug
    except ValueError as e:
        result.status = ResultStatus.PARSE_ERROR
        result.error_message = f"Invalid path format: {e}"
        return result

    if not is_supported_account(uri.account_slug, supported_prefixes):
        result.status = ResultStatus.SKIPPED
        result.error_message = f"No parser pattern for account type"
        return result

    try:
        import_report = ctx.statements.import_statement(uri)
        result.start_date = str(import_report.statement.start_date) if import_report.statement else ""
        result.end_date = str(import_report.statement.end_date) if import_report.statement else ""
        result.start_balance = str(import_report.statement.start_balance) if import_report.statement else ""
        result.end_balance = str(import_report.statement.end_balance) if import_report.statement else ""
    except StatementParseError as e:
        result.status = ResultStatus.PARSE_ERROR
        result.error_message = str(e)
        return result
    except ValueError as e:
        result.status = ResultStatus.IMPORT_ERROR
        result.error_message = str(e)
        return result
    except Exception as e:
        result.status = ResultStatus.IMPORT_ERROR
        result.error_message = f"Unexpected error: {e}"
        return result

    if import_report.result == ImportResult.ALREADY_RECONCILED:
        result.status = ResultStatus.RECONCILED
        result.computed_end_balance = str(import_report.statement.computed_end_balance or "")
        result.discrepancy = str(import_report.statement.discrepancy or "0")
        return result

    try:
        recon_result = ctx.reconciliation.reconcile_statement(import_report.statement_id)
        result.computed_end_balance = str(recon_result.computed_end_balance)
        result.discrepancy = str(recon_result.discrepancy)

        if recon_result.matches:
            result.status = ResultStatus.RECONCILED
        else:
            result.status = ResultStatus.DISCREPANCY
    except Exception as e:
        result.status = ResultStatus.IMPORT_ERROR
        result.error_message = f"Reconciliation error: {e}"

    return result


def run_verification(test_files_dir: Path, book_name: str, db_url: str) -> VerificationReport:
    """Run verification on all PDFs in the test files directory."""
    report = VerificationReport(test_files_dir=str(test_files_dir), book_name=book_name)
    supported_prefixes = get_supported_account_prefixes()

    pdf_files = find_pdf_files(test_files_dir)
    report.total_pdfs = len(pdf_files)

    print(f"Found {report.total_pdfs} PDF files")
    print(f"Supported account patterns: {', '.join(sorted(supported_prefixes))}")
    print()

    with BookContext(book_name, db_url) as ctx:
        for i, pdf_path in enumerate(pdf_files, 1):
            if i % 50 == 0 or i == report.total_pdfs:
                print(f"Processing {i}/{report.total_pdfs}...")

            result = process_pdf(ctx, pdf_path, supported_prefixes)
            report.results.append(asdict(result))

            if result.status == ResultStatus.RECONCILED:
                report.reconciled += 1
                report.processed += 1
            elif result.status == ResultStatus.DISCREPANCY:
                report.discrepancy += 1
                report.processed += 1
            elif result.status == ResultStatus.PARSE_ERROR:
                report.parse_error += 1
                report.processed += 1
            elif result.status == ResultStatus.IMPORT_ERROR:
                report.import_error += 1
                report.processed += 1
            elif result.status == ResultStatus.SKIPPED:
                report.skipped += 1

    return report


def print_summary(report: VerificationReport):
    """Print summary to stdout."""
    print()
    print("=" * 50)
    print("STATEMENT VERIFICATION RESULTS")
    print("=" * 50)
    print(f"Test files dir: {report.test_files_dir}")
    print(f"Book: {report.book_name}")
    print(f"Timestamp: {report.timestamp}")
    print()
    print(f"Total PDFs found: {report.total_pdfs}")
    print(f"Skipped (unsupported): {report.skipped}")
    print(f"Processed: {report.processed}")
    print(f"  - Reconciled: {report.reconciled}")
    print(f"  - Discrepancy: {report.discrepancy}")
    print(f"  - Parse error: {report.parse_error}")
    print(f"  - Import error: {report.import_error}")
    print()

    if report.discrepancy > 0:
        print("DISCREPANCIES:")
        print("-" * 50)
        for r in report.results:
            if r["status"] == ResultStatus.DISCREPANCY:
                print(f"  {r['file_path']}")
                print(f"    Expected: {r['end_balance']}, Computed: {r['computed_end_balance']}, Diff: {r['discrepancy']}")
        print()

    if report.parse_error > 0:
        print("PARSE ERRORS:")
        print("-" * 50)
        for r in report.results:
            if r["status"] == ResultStatus.PARSE_ERROR:
                print(f"  {r['file_path']}: {r['error_message']}")
        print()

    if report.import_error > 0:
        print("IMPORT ERRORS:")
        print("-" * 50)
        for r in report.results:
            if r["status"] == ResultStatus.IMPORT_ERROR:
                print(f"  {r['file_path']}: {r['error_message']}")
        print()


def ensure_tables_exist(db_url: str):
    """Create any missing database tables."""
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Verify statement parsing and reconciliation")
    parser.add_argument("--test-files-dir", type=Path, default=Path("test-files"),
                        help="Directory containing test PDF files")
    parser.add_argument("--book-name", "-b", default="personal",
                        help="Book name in database")
    parser.add_argument("--db-url", default="sqlite:///db/accounting-system.db",
                        help="Database URL")
    parser.add_argument("--output", "-o", type=Path,
                        help="Output JSON file for detailed results")
    parser.add_argument("--year", type=int,
                        help="Only process files from this year (for testing)")
    parser.add_argument("--create-tables", action="store_true",
                        help="Create any missing database tables before running")

    args = parser.parse_args()

    if not args.test_files_dir.exists():
        print(f"Error: Test files directory not found: {args.test_files_dir}", file=sys.stderr)
        sys.exit(1)

    if args.create_tables:
        print("Ensuring database tables exist...")
        ensure_tables_exist(args.db_url)

    test_dir = args.test_files_dir
    if args.year:
        test_dir = args.test_files_dir / str(args.year)
        if not test_dir.exists():
            print(f"Error: Year directory not found: {test_dir}", file=sys.stderr)
            sys.exit(1)
        print(f"Filtering to year: {args.year}")

    report = run_verification(test_dir, args.book_name, args.db_url)
    print_summary(report)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(asdict(report), f, indent=2)
        print(f"Detailed results written to: {args.output}")

    sys.exit(0 if report.parse_error == 0 and report.import_error == 0 else 1)


if __name__ == "__main__":
    main()

