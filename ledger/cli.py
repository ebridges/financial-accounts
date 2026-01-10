#!/usr/bin/env python3
import argparse
import sys
import os

from ledger.version import __version__
from ledger.business.book_context import BookContext
from ledger.business.management_service import ManagementService
from ledger.business.book_service import BookService
from ledger.business.ingest_service import IngestService, IngestResult
from ledger.business.statement_service import ImportResult
from ledger.business.reconciliation_service import display_reconciliation_result
from ledger.util.statement_uri import AccountUri

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
        do_delete_transaction(args.db_url, args.book_name, args.txn_id)

    elif args.command == "ingest":
        do_ingest(
            args.db_url,
            args.file_path,
            args.book_name,
        )

    elif args.command == "list-imports":
        do_list_imports(args.db_url, args.book_name)

    elif args.command == "import-statement":
        do_import_statement(args.db_url, args.book_name, args.pdf_path)

    elif args.command == "reconcile":
        do_reconcile(args.db_url, args.book_name, args.statement_id, args.account_slug, args.all)

    elif args.command == "list-statements":
        do_list_statements(args.db_url, args.book_name, args.account_slug)

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
    sp_delete_txn.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )
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

    # import-statement
    sp_import_stmt = subparsers.add_parser(
        "import-statement", help="Import a PDF statement and create AccountStatement record"
    )
    sp_import_stmt.add_argument(
        "pdf_path",
        help="Path to PDF statement file. Must follow convention: "
        "YYYY/account-slug/YYYY-MM-DD--YYYY-MM-DD-account-slug.pdf",
    )
    sp_import_stmt.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )

    # reconcile
    sp_reconcile = subparsers.add_parser(
        "reconcile", help="Reconcile statement(s) against transactions"
    )
    sp_reconcile.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )
    sp_reconcile.add_argument(
        "--statement-id", "-s", type=int, help="Specific statement ID to reconcile"
    )
    sp_reconcile.add_argument(
        "--account-slug", "-a", help="Reconcile all statements for this account"
    )
    sp_reconcile.add_argument(
        "--all", action="store_true", default=False, help="Include already-reconciled statements"
    )

    # list-statements
    sp_list_stmts = subparsers.add_parser("list-statements", help="List account statements")
    sp_list_stmts.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default: '{DEFAULT_BOOK}')"
    )
    sp_list_stmts.add_argument("--account-slug", "-a", help="Filter by account slug")

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
    with BookContext(book_name, db_url) as ctx:
        new_account = ctx.accounts.add_account(
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
    with BookContext(book_name, db_url) as ctx:
        accounts = ctx.accounts.list_accounts()
        if not accounts:
            print(f"No accounts in book '{book_name}'.")
        else:
            print(f"Accounts in book '{book_name}':")
            for a in accounts:
                parent_account_name = None
                if a.parent_account_id:
                    parent_account = ctx.accounts.lookup_by_id(a.parent_account_id)
                    parent_account_name = parent_account.name
                print(
                    f" - [ID={a.id}] Name={a.name}, Code={a.code}, Type={a.acct_type}, "
                    f"Parent={parent_account_name}, Hidden={a.hidden}, Placeholder={a.placeholder}"
                )


def do_book_transaction(db_url, book_name, txn_date, txn_desc, debit_acct, credit_acct, amount):
    with BookContext(book_name, db_url) as ctx:
        txn_id = ctx.transactions.enter_transaction(
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


def do_delete_transaction(db_url, book_name, txn_id):
    with BookContext(book_name, db_url) as ctx:
        try:
            ctx.transactions.delete(transaction_id=int(txn_id))
            print(f'Transaction ID {txn_id} successfully deleted.')
        except ValueError as e:
            print(f'Transaction ID {txn_id} was not deleted. {e}')


def do_init_db(db_url, confirm):
    # DROP and CREATE all tables (optional drop step if you truly want a fresh start)
    if confirm:
        with ManagementService().init_with_url(db_url=db_url) as mgmt_service:
            mgmt_service.reset_database()
        print(f"Database initialized at ({db_url}).")
    else:
        print('Resetting the database requires the "--confirm" flag.')


def do_ingest(db_url, file_path, book_name):
    """Ingest a QIF file."""
    # Verify file type
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext != '.qif':
        print(f"Error: Unsupported file type '{ext}'. Use .qif")
        return 1

    with BookContext(book_name, db_url) as ctx:
        try:
            ingest_svc = IngestService(ctx)
            report = ingest_svc.ingest_qif(file_path=file_path)

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
    with BookContext(book_name, db_url) as ctx:
        try:
            ingest_svc = IngestService(ctx)
            imports = ingest_svc.list_imports()

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


def do_import_statement(db_url, book_name, pdf_path):
    """Import a PDF statement."""
    # Parse path into AccountUri
    try:
        uri = AccountUri.from_string(pdf_path)
    except ValueError as e:
        print(f"Error: Invalid path format. {e}")
        print(
            "Path must follow convention: YYYY/account-slug/YYYY-MM-DD--YYYY-MM-DD-account-slug.pdf"
        )
        return 1

    with BookContext(book_name, db_url) as ctx:
        try:
            report = ctx.statements.import_statement(uri)

            if report.result == ImportResult.IMPORTED:
                print(f"✓ Imported statement: {report.message}")
                print(f"  Statement ID: {report.statement_id}")
            elif report.result == ImportResult.ALREADY_RECONCILED:
                print(f"⊘ {report.message}")
                print(f"  Statement ID: {report.statement_id}")
            elif report.result == ImportResult.NEEDS_RECONCILIATION:
                print(f"⚠ {report.message}")
                print(f"  Statement ID: {report.statement_id}")
                print("  Run 'reconcile' command to reconcile this statement.")

        except Exception as e:
            print(f"Error: {e}")
            return 1

    return 0


def do_reconcile(db_url, book_name, statement_id, account_slug, all_periods):
    """Reconcile statement(s)."""
    with BookContext(book_name, db_url) as ctx:
        try:
            if statement_id:
                # Reconcile specific statement
                result = ctx.reconciliation.reconcile_statement(statement_id)
                display_reconciliation_result(result)
            elif account_slug:
                # Reconcile all statements for account
                results = ctx.reconciliation.reconcile_by_account(
                    account_slug, all_periods=all_periods
                )
                if not results:
                    print(f"No statements to reconcile for account '{account_slug}'.")
                else:
                    for result in results:
                        display_reconciliation_result(result)
            else:
                print("Error: Specify either --statement-id or --account-slug")
                return 1

        except ValueError as e:
            print(f"Error: {e}")
            return 1

    return 0


def do_list_statements(db_url, book_name, account_slug):
    """List account statements."""
    with BookContext(book_name, db_url) as ctx:
        try:
            statements = ctx.statements.list_statements(account_slug)

            if not statements:
                filter_msg = f" for account '{account_slug}'" if account_slug else ""
                print(f"No statements found{filter_msg} in book '{book_name}'.")
                return 0

            print(f"Statements in book '{book_name}':")
            print("-" * 90)
            for stmt in statements:
                account_name = stmt.account.name if stmt.account else f"id={stmt.account_id}"
                status_symbol = {
                    'n': '○',  # not reconciled
                    'r': '✓',  # reconciled
                    'd': '✗',  # discrepancy
                }.get(stmt.reconcile_status, '?')

                print(f"  {status_symbol} ID: {stmt.id}")
                print(f"    Account: {account_name}")
                print(f"    Period: {stmt.start_date} to {stmt.end_date}")
                print(f"    Balance: ${stmt.start_balance:,.2f} → ${stmt.end_balance:,.2f}")
                if stmt.computed_end_balance is not None:
                    print(f"    Computed: ${stmt.computed_end_balance:,.2f}")
                if stmt.discrepancy is not None:
                    print(f"    Discrepancy: ${stmt.discrepancy:,.2f}")
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
