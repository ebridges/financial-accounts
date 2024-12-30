PRAGMA foreign_keys = OFF;  -- Temporarily disable FK checks for a clean drop.

------------------------------------------------------------------------------
-- 0. Drop existing triggers and tables (if any).
------------------------------------------------------------------------------
DROP TRIGGER IF EXISTS check_split_book_insert;
DROP TRIGGER IF EXISTS check_split_book_update;
DROP TRIGGER IF EXISTS split_set_updated_at;
DROP TRIGGER IF EXISTS transactions_set_updated_at;
DROP TRIGGER IF EXISTS account_set_updated_at;
DROP TRIGGER IF EXISTS account_type_set_updated_at;
DROP TRIGGER IF EXISTS book_set_updated_at;

DROP TABLE IF EXISTS split;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS account;
DROP TABLE IF EXISTS account_type;
DROP TABLE IF EXISTS book;

PRAGMA foreign_keys = ON;   -- Re-enable foreign key checks.

------------------------------------------------------------------------------
-- 1. book
------------------------------------------------------------------------------
CREATE TABLE book (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER book_set_updated_at
AFTER UPDATE ON book
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE book
      SET updated_at = CURRENT_TIMESTAMP
      WHERE id = NEW.id;
END;


------------------------------------------------------------------------------
-- 2. account_type
------------------------------------------------------------------------------
CREATE TABLE account_type (
    id UUID PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (name IN ('ASSET', 'LIABILITY', 'INCOME', 'EXPENSE', 'EQUITY'))
);

CREATE TRIGGER account_type_set_updated_at
AFTER UPDATE ON account_type
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE account_type
      SET updated_at = CURRENT_TIMESTAMP
      WHERE id = NEW.id;
END;

/* Optionally insert the five standard account types. 
   Replace the UUID values with real ones if you generate them in your code. */
INSERT INTO account_type (id, name)
VALUES
    ('00000000-0000-0000-0000-000000000001','ASSET'),
    ('00000000-0000-0000-0000-000000000002','LIABILITY'),
    ('00000000-0000-0000-0000-000000000003','INCOME'),
    ('00000000-0000-0000-0000-000000000004','EXPENSE'),
    ('00000000-0000-0000-0000-000000000005','EQUITY');


------------------------------------------------------------------------------
-- 3. account
------------------------------------------------------------------------------
CREATE TABLE account (
    id UUID PRIMARY KEY,
    book_id UUID NOT NULL,
    parent_account_id UUID,
    type_id UUID NOT NULL,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    hidden BOOLEAN NOT NULL DEFAULT FALSE,
    placeholder BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (book_id) REFERENCES book(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    FOREIGN KEY (parent_account_id) REFERENCES account(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,
    FOREIGN KEY (type_id) REFERENCES account_type(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT,

    -- Keep code unique per book, if desired
    UNIQUE (book_id, code)
);

CREATE TRIGGER account_set_updated_at
AFTER UPDATE ON account
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE account
      SET updated_at = CURRENT_TIMESTAMP
      WHERE id = NEW.id;
END;


------------------------------------------------------------------------------
-- 4. transactions
------------------------------------------------------------------------------
CREATE TABLE transactions (
    id UUID PRIMARY KEY,
    book_id UUID NOT NULL,
    transaction_date DATE NOT NULL,
    entry_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    transaction_description TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (book_id) REFERENCES book(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);

CREATE TRIGGER transactions_set_updated_at
AFTER UPDATE ON transactions
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE transactions
      SET updated_at = CURRENT_TIMESTAMP
      WHERE id = NEW.id;
END;


------------------------------------------------------------------------------
-- 5. split
------------------------------------------------------------------------------
CREATE TABLE split (
    id UUID PRIMARY KEY,
    transaction_id UUID NOT NULL,
    account_id UUID NOT NULL,
    amount DECIMAL(20,4) NOT NULL,  -- negative for credits, positive for debits
    memo TEXT,
    reconcile_date TIMESTAMP,
    reconcile_state CHAR(1) NOT NULL DEFAULT 'n'
       CHECK (reconcile_state IN ('n','c','r')),  -- n=Not, c=Cleared, r=Reconciled
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    FOREIGN KEY (account_id) REFERENCES account(id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);

CREATE TRIGGER split_set_updated_at
AFTER UPDATE ON split
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE split
      SET updated_at = CURRENT_TIMESTAMP
      WHERE id = NEW.id;
END;


------------------------------------------------------------------------------
-- 6. Cross-table checks to ensure transactions.book_id == account.book_id
------------------------------------------------------------------------------
-- Trigger for BEFORE INSERT on split using a WHEN clause
CREATE TRIGGER check_split_book_insert
BEFORE INSERT ON split
WHEN
(
    (SELECT t.book_id FROM transactions t WHERE t.id = NEW.transaction_id)
    !=
    (SELECT a.book_id FROM account a WHERE a.id = NEW.account_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Mismatch between transactions.book_id and account.book_id');
END;

-- Trigger for BEFORE UPDATE on split using a WHEN clause
CREATE TRIGGER check_split_book_update
BEFORE UPDATE ON split
WHEN
(
    (SELECT t.book_id FROM transactions t WHERE t.id = NEW.transaction_id)
    !=
    (SELECT a.book_id FROM account a WHERE a.id = NEW.account_id)
)
BEGIN
    SELECT RAISE(ABORT, 'Mismatch between transactions.book_id and account.book_id');
END;
