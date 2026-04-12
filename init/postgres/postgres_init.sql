-- =========================================================
-- Personal Expense Tracking - PostgreSQL Initialization Script
-- =========================================================
-- This script defines the core schema for expense tracking and
-- account transfers. It is designed for PostgreSQL 18.
--
-- Design defaults in this version:
-- 1) Master data (categories, merchants, products/services) is shared.
-- 2) accounts.balance is an application-managed snapshot.
-- 3) Balances may be negative (for credit-card style accounts).
-- =========================================================

-- Optional: keep everything in public for now.
-- If needed later, move objects into a dedicated schema.
-- CREATE SCHEMA expense_app;
-- SET search_path TO expense_app, public;

-- Needed for merchant fuzzy matching with trigram similarity/operators.
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- =========================================================
-- 1) Helper function: automatically refresh updated_at
-- =========================================================
-- Keeps audit timestamps accurate on every UPDATE.
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =========================================================================
-- 2) Helper function: validate expense_transaction - account ownership
-- ==========================================================================
-- Enforces tenant safety by checking that the expense owner and referenced account owner are the same user.
CREATE OR REPLACE FUNCTION validate_expense_transaction_user_account()
RETURNS TRIGGER AS $$
DECLARE
    account_owner_user_id BIGINT;
BEGIN
    SELECT user_id
    INTO account_owner_user_id
    FROM accounts
    WHERE account_id = NEW.account_id;

    IF account_owner_user_id IS NULL THEN
        RAISE EXCEPTION 'Invalid account_id: % does not exist', NEW.account_id;
    END IF;

    IF NEW.user_id <> account_owner_user_id THEN
        RAISE EXCEPTION
            'user_id (%) does not match the owner of account_id (%) which belongs to user_id (%)',
            NEW.user_id, NEW.account_id, account_owner_user_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =========================================================================
-- 3) Helper function: validate account_transfer - user ownership
-- =========================================================================
-- Ensures both source and destination accounts belong to the same user_id carried by the transfer row.
CREATE OR REPLACE FUNCTION validate_account_transfer_user_accounts()
RETURNS TRIGGER AS $$
DECLARE
    from_account_owner_user_id BIGINT;
    to_account_owner_user_id BIGINT;
BEGIN
    SELECT user_id
    INTO from_account_owner_user_id
    FROM accounts
    WHERE account_id = NEW.from_account_id;

    IF from_account_owner_user_id IS NULL THEN
        RAISE EXCEPTION 'Invalid from_account_id: % does not exist', NEW.from_account_id;
    END IF;

    SELECT user_id
    INTO to_account_owner_user_id
    FROM accounts
    WHERE account_id = NEW.to_account_id;

    IF to_account_owner_user_id IS NULL THEN
        RAISE EXCEPTION 'Invalid to_account_id: % does not exist', NEW.to_account_id;
    END IF;

    IF NEW.user_id <> from_account_owner_user_id THEN
        RAISE EXCEPTION
            'user_id (%) does not match the owner of from_account_id (%) which belongs to user_id (%)',
            NEW.user_id, NEW.from_account_id, from_account_owner_user_id;
    END IF;

    IF NEW.user_id <> to_account_owner_user_id THEN
        RAISE EXCEPTION
            'user_id (%) does not match the owner of to_account_id (%) which belongs to user_id (%)',
            NEW.user_id, NEW.to_account_id, to_account_owner_user_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =========================================================
-- 4) Core tables
-- =========================================================

-- 4.1 Users
CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE users IS 'Stores application users and data ownership roots.';
COMMENT ON COLUMN users.full_name IS 'Display name of the user.';


-- 4.2 Accounts
CREATE TABLE accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL,
    balance NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_accounts_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_accounts_account_type_not_blank
        CHECK (BTRIM(account_type) <> ''),

    CONSTRAINT chk_accounts_account_name_not_blank
        CHECK (BTRIM(account_name) <> ''),

    CONSTRAINT uq_accounts_user_account_name
        UNIQUE (user_id, account_name)
);

COMMENT ON TABLE accounts IS 'Stores spending source accounts such as cash, bank, card, and ewallet.';
COMMENT ON COLUMN accounts.balance IS 'Application-managed snapshot balance. Negative values are allowed.';
COMMENT ON COLUMN accounts.account_type IS 'Free-text type such as cash, bank, credit_card, ewallet.';


-- 4.3 Merchant types
CREATE TABLE merchant_types (
    merchant_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_type_name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_merchant_types_name_not_blank
        CHECK (BTRIM(merchant_type_name) <> '')
);

COMMENT ON TABLE merchant_types IS 'Controlled list of merchant types, acting like an extendable enum.';
COMMENT ON COLUMN merchant_types.merchant_type_name IS 'Case-insensitive unique name. Example: petrol_station, restaurant.';


-- 4.4 Merchants
CREATE TABLE merchants (
    merchant_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_type_id BIGINT NOT NULL,
    merchant_name TEXT NOT NULL,
    location_name TEXT NOT NULL,
    city TEXT,
    state TEXT,
    country TEXT,
    other_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_merchants_merchant_type
        FOREIGN KEY (merchant_type_id)
        REFERENCES merchant_types(merchant_type_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_merchants_name_not_blank
        CHECK (BTRIM(merchant_name) <> ''),

    CONSTRAINT chk_merchants_location_not_blank
        CHECK (BTRIM(location_name) <> ''),

    CONSTRAINT uq_merchants_name_location
        UNIQUE (merchant_name, location_name)
);

COMMENT ON TABLE merchants IS 'Stores merchant-location combinations where spending occurred.';
COMMENT ON COLUMN merchants.other_name IS 'Alternative clue or semantic description for agent matching.';


-- 4.5 Categories
CREATE TABLE categories (
    category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_category_id BIGINT NULL,
    category_name TEXT NOT NULL,
    category_level INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_categories_parent
        FOREIGN KEY (parent_category_id)
        REFERENCES categories(category_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_categories_name_not_blank
        CHECK (BTRIM(category_name) <> ''),

    CONSTRAINT chk_categories_level_positive
        CHECK (category_level >= 1)
);

COMMENT ON TABLE categories IS 'Hierarchical categories used for expense classification.';
COMMENT ON COLUMN categories.parent_category_id IS 'NULL for top-level categories.';
COMMENT ON COLUMN categories.category_level IS '1 = root category, 2+ = child depth.';


-- 4.6 Products/services
CREATE TABLE products_services (
    product_service_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    default_name TEXT NOT NULL,
    default_category_id BIGINT NOT NULL,
    unit_of_measure TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_products_services_default_category
        FOREIGN KEY (default_category_id)
        REFERENCES categories(category_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_products_services_name_not_blank
        CHECK (BTRIM(default_name) <> '')
);

COMMENT ON TABLE products_services IS 'Standardized product/service master list for repeated items.';
COMMENT ON COLUMN products_services.default_name IS 'Case-insensitive unique normalized item name.';
COMMENT ON COLUMN products_services.default_category_id IS 'Default category used when this item is reused.';


-- 4.7 Expense transactions
CREATE TABLE expense_transactions (
    transaction_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    account_id BIGINT NOT NULL,
    merchant_id BIGINT NOT NULL,
    transaction_datetime TIMESTAMPTZ NOT NULL,
    transaction_date DATE NOT NULL,
    total_amount NUMERIC(18,2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_expense_transactions_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_expense_transactions_account
        FOREIGN KEY (account_id)
        REFERENCES accounts(account_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_expense_transactions_merchant
        FOREIGN KEY (merchant_id)
        REFERENCES merchants(merchant_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_expense_transactions_total_amount_positive
        CHECK (total_amount > 0),

    CONSTRAINT chk_expense_transactions_date_matches_datetime
        CHECK (transaction_date = transaction_datetime::date)
);

COMMENT ON TABLE expense_transactions IS 'Stores each expense payment event.';
COMMENT ON COLUMN expense_transactions.user_id IS 'Owner of the transaction.';
COMMENT ON COLUMN expense_transactions.transaction_date IS 'Date-only field for reporting filters.';
COMMENT ON COLUMN expense_transactions.notes IS 'Optional free-text note about the spending event.';


-- 4.8 Account transfers
CREATE TABLE account_transfers (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL,
    from_account_id BIGINT NOT NULL,
    to_account_id BIGINT NOT NULL,
    transfer_datetime TIMESTAMPTZ NOT NULL,
    transfer_date DATE NOT NULL,
    amount NUMERIC(18,2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_account_transfers_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_account_transfers_from_account
        FOREIGN KEY (from_account_id)
        REFERENCES accounts(account_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_account_transfers_to_account
        FOREIGN KEY (to_account_id)
        REFERENCES accounts(account_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_account_transfers_amount_positive
        CHECK (amount > 0),

    CONSTRAINT chk_account_transfers_accounts_different
        CHECK (from_account_id <> to_account_id),

    CONSTRAINT chk_account_transfers_date_matches_datetime
        CHECK (transfer_date = transfer_datetime::date)
);

COMMENT ON TABLE account_transfers IS 'Stores money movement between two accounts owned by the same user.';
COMMENT ON COLUMN account_transfers.from_account_id IS 'Account balance should decrease by amount.';
COMMENT ON COLUMN account_transfers.to_account_id IS 'Account balance should increase by amount.';
COMMENT ON COLUMN account_transfers.amount IS 'Transfer amount. Must be strictly positive.';


-- 4.9 Expense line items
CREATE TABLE expense_line_items (
    line_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_id BIGINT NOT NULL,
    product_service_id BIGINT NULL,
    category_id BIGINT NOT NULL,
    item_name TEXT NOT NULL,
    quantity NUMERIC(18,3) NOT NULL DEFAULT 1.000,
    unit_price NUMERIC(18,2) NOT NULL,
    total_price NUMERIC(18,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_expense_line_items_transaction
        FOREIGN KEY (transaction_id)
        REFERENCES expense_transactions(transaction_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_expense_line_items_product_service
        FOREIGN KEY (product_service_id)
        REFERENCES products_services(product_service_id)
        ON DELETE SET NULL,

    CONSTRAINT fk_expense_line_items_category
        FOREIGN KEY (category_id)
        REFERENCES categories(category_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_expense_line_items_name_not_blank
        CHECK (BTRIM(item_name) <> ''),

    CONSTRAINT chk_expense_line_items_quantity_positive
        CHECK (quantity > 0),

    CONSTRAINT chk_expense_line_items_unit_price_non_negative
        CHECK (unit_price >= 0),

    CONSTRAINT chk_expense_line_items_total_price_non_negative
        CHECK (total_price >= 0),

    CONSTRAINT chk_expense_line_items_total_matches_qty_price
        CHECK (ABS(total_price - ROUND((quantity * unit_price)::numeric, 2)) <= 0.01)
);

COMMENT ON TABLE expense_line_items IS 'Stores detailed purchased items inside each expense transaction.';
COMMENT ON COLUMN expense_line_items.product_service_id IS 'Nullable until the item is standardized into the master list.';


-- =========================================================
-- 5) Indexes
-- =========================================================
-- Join and filter indexes
CREATE INDEX idx_accounts_user_id
    ON accounts(user_id);

CREATE INDEX idx_merchants_merchant_type_id
    ON merchants(merchant_type_id);

CREATE INDEX IF NOT EXISTS idx_merchants_name_trgm_ci
    ON merchants USING gin (LOWER(BTRIM(merchant_name)) gin_trgm_ops);

CREATE INDEX idx_categories_parent_category_id
    ON categories(parent_category_id);

CREATE INDEX idx_products_services_default_category_id
    ON products_services(default_category_id);

CREATE INDEX idx_expense_transactions_user_id
    ON expense_transactions(user_id);

CREATE INDEX idx_expense_transactions_account_id
    ON expense_transactions(account_id);

CREATE INDEX idx_expense_transactions_merchant_id
    ON expense_transactions(merchant_id);

CREATE INDEX idx_expense_transactions_transaction_date
    ON expense_transactions(transaction_date);

CREATE INDEX idx_expense_transactions_transaction_datetime
    ON expense_transactions(transaction_datetime);

CREATE INDEX idx_account_transfers_user_id
    ON account_transfers(user_id);

CREATE INDEX idx_account_transfers_transfer_date
    ON account_transfers(transfer_date);

CREATE INDEX idx_account_transfers_from_account_id
    ON account_transfers(from_account_id);

CREATE INDEX idx_account_transfers_to_account_id
    ON account_transfers(to_account_id);

CREATE INDEX idx_account_transfers_user_transfer_date
    ON account_transfers(user_id, transfer_date);

CREATE INDEX idx_expense_line_items_transaction_id
    ON expense_line_items(transaction_id);

CREATE INDEX idx_expense_line_items_category_id
    ON expense_line_items(category_id);

CREATE INDEX idx_expense_line_items_product_service_id
    ON expense_line_items(product_service_id);

-- Case-insensitive uniqueness indexes
CREATE UNIQUE INDEX uq_merchant_types_name_ci
    ON merchant_types (LOWER(BTRIM(merchant_type_name)));

CREATE UNIQUE INDEX uq_products_services_default_name_ci
    ON products_services (LOWER(BTRIM(default_name)));

-- Root categories: unique by normalized name where parent is NULL.
CREATE UNIQUE INDEX uq_categories_root_name_ci
    ON categories (LOWER(BTRIM(category_name)))
    WHERE parent_category_id IS NULL;

-- Child categories: unique by parent + normalized name.
CREATE UNIQUE INDEX uq_categories_parent_name_ci
    ON categories (parent_category_id, LOWER(BTRIM(category_name)))
    WHERE parent_category_id IS NOT NULL;


-- =========================================================
-- 6) updated_at triggers
-- =========================================================
CREATE TRIGGER trg_users_set_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_accounts_set_updated_at
BEFORE UPDATE ON accounts
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_merchant_types_set_updated_at
BEFORE UPDATE ON merchant_types
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_merchants_set_updated_at
BEFORE UPDATE ON merchants
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_categories_set_updated_at
BEFORE UPDATE ON categories
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_products_services_set_updated_at
BEFORE UPDATE ON products_services
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_expense_transactions_set_updated_at
BEFORE UPDATE ON expense_transactions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_account_transfers_set_updated_at
BEFORE UPDATE ON account_transfers
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_expense_line_items_set_updated_at
BEFORE UPDATE ON expense_line_items
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- =========================================================
-- 7) Ownership validation triggers
-- =========================================================
CREATE TRIGGER trg_validate_expense_transaction_user_account
BEFORE INSERT OR UPDATE ON expense_transactions
FOR EACH ROW
EXECUTE FUNCTION validate_expense_transaction_user_account();

CREATE TRIGGER trg_validate_account_transfer_user_accounts
BEFORE INSERT OR UPDATE ON account_transfers
FOR EACH ROW
EXECUTE FUNCTION validate_account_transfer_user_accounts();
