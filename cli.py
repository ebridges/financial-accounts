#!/usr/bin/env python3
import argparse
import sys
import os
from decimal import Decimal

from accounts.data_access import DAL

DEFAULT_DB_URL = "sqlite:///db/accounting-system.db"
DEFAULT_BOOK = "personal"

f"""
CLI program for the `accounts` application.

Commands (the only positional arg):
  init-book, add-account, list-accounts, book-transaction

All other arguments are short/long flags, e.g.:
  --book-name/-b, --acct-type/-t, --acct-code/-c, --acct-name/-n,
  --parent-id/-p, --description/-d, --txn-date/-D, --txn-desc/-T,
  --debit-acct/-x, --credit-acct/-y, --amount/-a, etc.

Examples:

1) Init a book named 'business' (defaults to '{DEFAULT_BOOK}' if not given):
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

By default, --book-name = '{DEFAULT_BOOK}'.
"""

# --------------------------------------------------------------------------
# Adjust these imports for your own project structure.
# For example, if you store DB_URL in config, or if you store your models
# and DAL in the `accounts` package, do something like:
#
# from accounts.models import Base, Book, Account
# from accounts.data_access import DAL
#
# We'll show them inline here for clarity.
# --------------------------------------------------------------------------


def ensure_subdirs_for_sqlite(db_url: str):
    if db_url.startswith("sqlite:///"):
        local_path = db_url[len("sqlite:///") :]
        directory = os.path.dirname(local_path)
        if directory:
            os.makedirs(directory, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Accounts CLI (subparser version)")

    parser.add_argument(
        "--db-url", "-u", default=DEFAULT_DB_URL, help=f"Database URL (default: {DEFAULT_DB_URL})"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-db
    sp_init_db = subparsers.add_parser(
        "init-db", help="Initialize the DB schema (drop/create tables)"
    )
    sp_init_db.add_argument(
        "--confirm", help="This flag must be passed to avoid accidental dropping of database."
    )

    # init-book
    sp_init_book = subparsers.add_parser("init-book", help="Create a new Book if it doesn't exist")
    sp_init_book.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default '{DEFAULT_BOOK}')"
    )

    # add-account
    sp_add_account = subparsers.add_parser("add-account", help="Add an account to a given book")
    sp_add_account.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default '{DEFAULT_BOOK}')"
    )
    sp_add_account.add_argument(
        "--acct-type", "-t", required=True, help="Acct type (ASSET/LIABILITY/INCOME/EXPENSE/EQUITY)"
    )
    sp_add_account.add_argument("--acct-code", "-c", required=True, help="Account code")
    sp_add_account.add_argument("--acct-name", "-n", required=True, help="Account name")
    sp_add_account.add_argument("--description", "-d", default="", help="Description (optional)")
    sp_add_account.add_argument(
        "--parent-name", "-p", default=None, help="Parent account name (optional)"
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
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default '{DEFAULT_BOOK}')"
    )

    # book-transaction
    sp_book_txn = subparsers.add_parser(
        "book-transaction", help="Create a transaction w/ two splits (debit & credit)"
    )
    sp_book_txn.add_argument(
        "--book-name", "-b", default=DEFAULT_BOOK, help=f"Book name (default '{DEFAULT_BOOK}')"
    )
    sp_book_txn.add_argument(
        "--txn-date", "-D", required=True, help="Transaction date (YYYY-MM-DD)"
    )
    sp_book_txn.add_argument("--txn-desc", "-T", required=True, help="Transaction description")
    sp_book_txn.add_argument("--debit-acct", "-x", required=True, help="Debit account name")
    sp_book_txn.add_argument("--credit-acct", "-y", required=True, help="Credit account name")
    sp_book_txn.add_argument("--amount", "-a", required=True, help="Amount")

    args = parser.parse_args()

    # ----------------------------------------------------------------------
    # Make sure subdirectories exist for local SQLite path, if any
    # (You likely have a function like ensure_subdirs_for_sqlite(db_url).)
    # For brevity, let's inline a minimal approach:
    # ----------------------------------------------------------------------
    ensure_subdirs_for_sqlite(args.db_url)

    # ----------------------------------------------------------------------
    # Connect to DB
    # ----------------------------------------------------------------------

    with DAL(db_url=args.db_url) as dal:

        # ----------------------------------------------------------------------
        # Now parse the command and run the logic
        # ----------------------------------------------------------------------
        if args.command == 'init-db':
            # DROP and CREATE all tables (optional drop step if you truly want a fresh start)
            dal.reset_database()
            print("Database initialized (accounts.db).")

        elif args.command == "init-book":
            # Create a new Book if it doesn't exist
            existing = dal.get_book_by_name(args.book_name)
            if existing:
                print(f"Book '{args.book_name}' already exists with id={existing.id}")
            else:
                new_book = dal.create_book(args.book_name)
                print(f"Created book '{args.book_name}' with id={new_book.id}")

        elif args.command == "add-account":
            # Look up the book
            book = dal.get_book_by_name(args.book_name)
            if not book:
                print(f"No book found named '{args.book_name}'.")
                return 1

            # If parent-name is provided, do a lookup. (In this example, we do not store parent-child rel by name.)
            parent_id = None
            if args.parent_name:
                parent_acct = dal.get_account_by_name_for_book(book.id, args.parent_name)
                if not parent_acct:
                    print(f"Parent account named '{args.parent_name}' not found.")
                    return 1
                parent_id = parent_acct.id

            new_acct = dal.create_account(
                book_id=book.id,
                name=args.acct_name,
                code=args.acct_code,
                acct_type=args.acct_type,
                description=args.description,
                hidden=args.hidden,
                placeholder=args.placeholder,
                parent_account_id=parent_id,
            )
            print(
                f"Created account '{args.acct_name}' with id={new_acct.id} in book='{book.name}'."
            )

        elif args.command == "list-accounts":
            book = dal.get_book_by_name(args.book_name)
            if not book:
                print(f"No book found named '{args.book_name}'.")
                return 1
            accounts = dal.list_accounts_for_book(book.id)
            if not accounts:
                print(f"No accounts in book '{book.name}'.")
            else:
                print(f"Accounts in book '{book.name}':")
                for a in accounts:
                    print(
                        f" - [ID={a.id}] Name={a.name}, Code={a.code}, Type={a.acct_type}, Hidden={a.hidden}, Placeholder={a.placeholder}"
                    )

        elif args.command == "book-transaction":
            book = dal.get_book_by_name(args.book_name)
            if not book:
                print(f"No book found named '{args.book_name}'.")
                return 1

            # parse amount
            try:
                amt = Decimal(value=args.amount)
            except ValueError:
                print("ERROR: --amount must be numeric.")
                return 1

            debit_acct = dal.get_account_by_name_for_book(book.id, args.debit_acct)
            if not debit_acct:
                print(f"Debit account '{args.debit_acct}' not found in book '{args.book_name}'.")
                return 1

            credit_acct = dal.get_account_by_name_for_book(book.id, args.credit_acct)
            if not credit_acct:
                print(f"Credit account '{args.credit_acct}' not found in book '{args.book_name}'.")
                return 1

            txn = dal.create_transaction(
                book_id=book.id,
                transaction_date=args.txn_date,
                transaction_description=args.txn_desc,
            )
            # debit is +, credit is -
            dal.create_split(transaction_id=txn.id, account_id=debit_acct.id, amount=amt)
            dal.create_split(transaction_id=txn.id, account_id=credit_acct.id, amount=-amt)

            print(
                f"Created transaction {txn.id}, debiting '{debit_acct.name}' / crediting '{credit_acct.name}' for ${amt}"
            )

    return 0


if __name__ == '__main__':
    sys.exit(main())
