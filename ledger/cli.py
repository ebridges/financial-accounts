#!/usr/bin/env python3
import argparse
import sys
import os

from ledger.version import __version__
from ledger.business.transaction_service import TransactionService
from ledger.business.management_service import ManagementService
from ledger.business.account_service import AccountService
from ledger.business.book_service import BookService
from ledger.business.ingest_service import IngestService, IngestResult

DEFAULT_DB_URL = "sqlite:///db/accounting-system.db"
DEFAULT_BOOK = "personal"

'''
CLI program for the `accounts` application.

usage: cli.py [-h] [--db-url DB_URL] COMMAND ...

COMMAND is one of: {
    init-db,init-book,add-account,list-accounts,book-transaction
}

Accounts CLI

positional arguments:
  {init-db,init-book,add-account,list-accounts,book-transaction}
    init-db             Initialize the DB schema (drop/create tables)
    init-book           Create a new Book if it doesn't exist. (Default: 'personal')
    add-account         Add an account to a given book
    list-accounts       List all accounts for a given book
    book-transaction    Create a transaction w/ two splits (debit & credit)

options:
  -h, --help            show this help message and exit
  --db-url, -u DB_URL   Database URL (default: sqlite:///db/accounting-system.db)

Examples:

1) Init a book named 'business' (uses default book name if not given):
    python cli.py init-book -b business

2) Add an account:
    python cli.py add-account -b business -t ASSET -c CASH1 -n "Cash Account"

3) List accounts in book 'business':
    python cli.py list-accounts -b business

4) Book a transaction:
    python cli.py book-transaction -b business -D 2024-01-01 \
      -T "Rent Payment" -x "Rent Expense" -y "Cash on Hand" -a 500

Note: If you do not specify some flags for a particular command, you'll see
an error or a basic usage note. This is a minimal illustrative example.
'''


def main():
    args = parse_arguments()

    # ----------------------------------------------------------------------
    # Make sure subdirectories exist for local SQLite path, if any
    # ----------------------------------------------------------------------
    ensure_subdirs_for_sqlite(args.db_url)

    # ----------------------------------------------------------------------
    # Handle global flags
    # ----------------------------------------------------------------------

    # @todo add verbose flag & logging

    # ----------------------------------------------------------------------
    # Handle each individual command in its own transaction
    # ----------------------------------------------------------------------
    if args.command == 'init-db':
        do_init_db(args.db_url, args.confirm)

    elif args.command == "init-book":
        do_init_book(args.db_url, args.book_name)

    elif args.command == "add-account":
        do_add_account(
            args.db_url,
            args.book_name,
            args.parent_code,
            args.parent_name,
            args.acct_name,
            args.acct_fullname,
            args.acct_code,
            args.acct_type,
            args.description,
            args.hidden,
            args.placeholder,
        )

    elif args.command == "list-accounts":
        do_list_accounts(args.db_url, args.book_name)

    elif args.command == "book-transaction":
        do_book_transaction(
            args.db_url,
            args.book_name,
            args.txn_date,
            args.txn_desc,
            args.debit_acct,
            args.credit_acct,
            args.amount,
        )

    elif args.command == "delete-transaction":
        do_delete_transaction(args.db_url, args.txn_id)

    elif args.command == "ingest":
        do_ingest(args.db_url, args.file_path, args.book_name)

    elif args.command == "list-imports":
        do_list_imports(args.db_url, args.book_name)

    return 0


def parse_arguments():
    parser = argparse.ArgumentParser(description="Accounts CLI")

    parser.add_argument("--version", action="version", version=__version__, help="Show version.")

    parser.add_argument(
        "--db-url", "-u", default=DEFAULT_DB_URL, help=f"Database URL (default: {DEFAULT_DB_URL})"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-db
    sp_init_db = subparsers.add_parser(
        "init-db", help="Initialize the DB schema (drop/create tables)"
    )
    sp_init_db.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="This flag must be passed to avoid accidental dropping of database.",
    )

    # init-book
    sp_init_book = subparsers.add_parser("init-book", help="Create a new Book if it doesn't exist")
    sp_init_book.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )

    # add-account
    sp_add_account = subparsers.add_parser("add-account", help="Add an account to a given book")
    sp_add_account.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )
    sp_add_account.add_argument(
        "--acct-type",
        "-t",
        required=True,
        help="Acct type (ASSET/LIABILITY/INCOME/EXPENSE/EQUITY/ROOT)",
    )
    sp_add_account.add_argument("--acct-code", "-c", required=True, help="Account code")
    sp_add_account.add_argument("--acct-name", "-n", required=True, help="Account name")
    sp_add_account.add_argument(
        "--acct-fullname", "-f", required=True, help="The hierarchical path name of this account."
    )
    sp_add_account.add_argument("--description", "-d", default="", help="Description (optional)")
    sp_add_account.add_argument(
        "--parent-name",
        "-p",
        help="Parent account name. Optional.",
    )
    sp_add_account.add_argument(
        "--hidden", default=False, action="store_true", help="Mark account as hidden (optional)"
    )
    sp_add_account.add_argument(
        "--placeholder",
        action="store_true",
        default=False,
        help="Mark account as placeholder (optional)",
    )

    # list-accounts
    sp_list_accounts = subparsers.add_parser(
        "list-accounts", help="List all accounts for a given book"
    )
    sp_list_accounts.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )

    # book-transaction
    sp_book_txn = subparsers.add_parser(
        "book-transaction", help="Create a transaction w/ two splits (debit & credit)"
    )
    sp_book_txn.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )
    sp_book_txn.add_argument(
        "--txn-date", "-D", required=True, help="Transaction date (YYYY-MM-DD)"
    )
    sp_book_txn.add_argument("--txn-desc", "-T", required=True, help="Transaction description")
    sp_book_txn.add_argument("--debit-acct", "-x", required=True, help="Debit account name")
    sp_book_txn.add_argument("--credit-acct", "-y", required=True, help="Credit account name")
    sp_book_txn.add_argument("--amount", "-a", required=True, help="Amount")

    # delete-transaction
    sp_delete_txn = subparsers.add_parser("delete-transaction", help="Delete a transaction by ID")
    sp_delete_txn.add_argument("--txn-id", "-T", required=True, help="Transaction ID")

    # ingest
    sp_ingest = subparsers.add_parser(
        "ingest", help="Ingest a QIF file with file-level idempotency"
    )
    sp_ingest.add_argument("file_path", help="Path to QIF file to ingest")
    sp_ingest.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )

    # list-imports
    sp_list_imports = subparsers.add_parser(
        "list-imports", help="List all imported files for a book"
    )
    sp_list_imports.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )

    return parser.parse_args()


def do_init_book(db_url, book_name):
    with BookService().init_with_url(db_url=db_url) as book_service:
        new_book = book_service.create_new_book(book_name=book_name)
        print(f'New book: {new_book.id}')


def do_add_account(
    db_url,
    book_name,
    parent_code,
    parent_name,
    acct_name,
    acct_fullname,
    acct_code,
    acct_type,
    description,
    hidden,
    placeholder,
):
    with AccountService().init_with_url(db_url=db_url) as acct_service:
        new_account = acct_service.add_account(
            book_name,
            parent_code,
            parent_name,
            acct_name,
            acct_fullname,
            acct_code,
            acct_type,
            description,
            hidden,
            placeholder,
        )
        print(f"Created account '{acct_name}' with id={new_account.id} in book='{book_name}'.")


def do_list_accounts(db_url, book_name):
    with AccountService().init_with_url(db_url=db_url) as acct_service:
        accounts = acct_service.list_accounts_in_book(book_name)
        if not accounts:
            print(f"No accounts in book '{book_name}'.")
        else:
            print(f"Accounts in book '{book_name}':")
            for a in accounts:
                parent_account_name = None
                if a.parent_account_id:
                    parent_account = acct_service.lookup_account_by_id(a.parent_account_id)
                    parent_account_name = parent_account.name
                print(
                    f" - [ID={a.id}] Name={a.name}, Code={a.code}, Type={a.acct_type}, "
                    f"Parent={parent_account_name}, Hidden={a.hidden}, Placeholder={a.placeholder}"
                )


def do_book_transaction(db_url, book_name, txn_date, txn_desc, debit_acct, credit_acct, amount):
    with TransactionService().init_with_url(db_url=db_url) as txn_service:
        txn_id = txn_service.enter_transaction(
            book_name=book_name,
            txn_date=txn_date,
            txn_desc=txn_desc,
            to_acct=debit_acct,
            from_acct=credit_acct,
            amount=amount,
        )
        print(
            f"Created transaction {txn_id}, debiting '{debit_acct}' / "
            f"crediting '{credit_acct}' for ${amount}"
        )


def do_delete_transaction(db_url, txn_id):
    with TransactionService().init_with_url(db_url=db_url) as txn_service:
        try:
            txn_service.delete_transaction(transaction_id=txn_id)
        except ValueError as e:
            print(f'Transaction ID {txn_id} was not deleted. {e}')
        print(f'Transaction ID {txn_id} successfully deleted.')


def do_init_db(db_url, confirm):
    # DROP and CREATE all tables (optional drop step if you truly want a fresh start)
    if confirm:
        mgmt_service = ManagementService().init_with_url(db_url=db_url)
        mgmt_service.reset_database()
        print(f"Database initialized at ({db_url}).")
    else:
        print('Resetting the database requires the "--confirm" flag.')


def do_ingest(db_url, file_path, book_name):
    """Ingest a QIF file."""
    # Verify file extension
    _, ext = os.path.splitext(file_path)
    if ext.lower() != '.qif':
        print(f"Error: Expected .qif file, got '{ext}'")
        return 1

    with IngestService().init_with_url(db_url=db_url) as ingest_svc:
        try:
            report = ingest_svc.ingest_qif(file_path, book_name)

            # Print result
            if report.result == IngestResult.IMPORTED:
                print(f"✓ {report.message}")
                print(f"  Import ID: {report.import_file_id}")
                print(f"  Transactions imported: {report.transactions_imported}")
                if report.transactions_matched > 0:
                    print(f"  Transactions matched: {report.transactions_matched}")
            elif report.result == IngestResult.SKIPPED_DUPLICATE:
                print(f"⊘ {report.message}")
                print(f"  Existing import ID: {report.import_file_id}")
            elif report.result == IngestResult.HASH_MISMATCH:
                print(f"⚠ {report.message}")
                print(f"  Existing import ID: {report.import_file_id}")
                return 1

        except ValueError as e:
            print(f"Error: {e}")
            return 1

    return 0


def do_list_imports(db_url, book_name):
    """List all imported files for a book."""
    with IngestService().init_with_url(db_url=db_url) as ingest_svc:
        try:
            imports = ingest_svc.list_imports(book_name)

            if not imports:
                print(f"No imports found for book '{book_name}'.")
                return 0

            print(f"Imports for book '{book_name}':")
            print("-" * 80)
            for imp in imports:
                print(f"  ID: {imp.id}")
                print(f"    Filename: {imp.filename}")
                print(f"    Type: {imp.source_type}")
                print(f"    Coverage: {imp.coverage_start} to {imp.coverage_end}")
                print(f"    Transactions: {imp.row_count}")
                print(f"    Imported: {imp.created_at}")
                print()

        except ValueError as e:
            print(f"Error: {e}")
            return 1

    return 0


def ensure_subdirs_for_sqlite(db_url: str):
    if db_url.startswith("sqlite:///"):
        local_path = db_url[len("sqlite:///") :]
        directory = os.path.dirname(local_path)
        if directory:
            os.makedirs(directory, exist_ok=True)


if __name__ == '__main__':
    sys.exit(main())
