# Accounting System

## 1. Overview and Objectives
The goal of this system is to provide a robust personal finance tracking and reconciliation application. Users can track transactions across multiple accounts, import data from financial institutions, categorize expenses, and perform monthly (or periodic) reconciliations against bank statements. The design draws on double-entry accounting principles—ensuring data consistency, clarity of debits/credits, and the ability to generate meaningful financial reports.

### Key Objectives
1. **Data Integrity**
    - Use **double-entry** style transactions and splits.
    - Enforce referential integrity using foreign keys.
    - Prevent common data errors (e.g., mis-matched books for transaction vs. account).
2. **Easy Reconciliation**
    - Mark transactions as _cleared_ or _reconciled_ within the system.
    - Provide a mechanism (triggers and foreign keys) to avoid mismatched or duplicated data.
3. **Flexibility and Extensibility**
    - The schema uses **UUID** primary keys, making it easier to merge or migrate data.
    - The system can be adapted to different database backends (e.g., migrating from SQLite to PostgreSQL).
4. **Hierarchical Accounts**
    - Support **parent-child** relationships among accounts (e.g., grouping categories under top-level accounts).
    - Allow organizing expense and income categories in a tree-like structure.
5. **Reporting**
    - The schema supports queries and pivoting on **accounts**, **transactions**, and **splits**, essential for generating income/expense statements or custom reports.

## 2. Schema

![](docs/img/schema-diagram.png)

## 3. System design

- The application stores data in a SQLite Database identified by a DB URL provided as an argument.

## 4. Usage

```
usage: cli.py [-h] [--db-url DB_URL] {init-db,init-book,add-account,list-accounts,book-transaction} ...

Accounts CLI

positional arguments:
  {init-db,init-book,add-account,list-accounts,book-transaction}
    init-db             Initialize the DB schema (drop/create tables)
    init-book           Create a new Book if it doesn't exist
    add-account         Add an account to a given book
    list-accounts       List all accounts for a given book
    book-transaction    Create a transaction w/ two splits (debit & credit)

options:
  -h, --help            show this help message and exit
  --db-url, -u DB_URL   Database URL (default: sqlite:///db/accounting-system.db)
```

## A. License

```
Copyright 2025 Edward Bridges

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```