# Expense Tracking Database Schema

Updated on 2026-04-11

This document describes the PostgreSQL schema used by this project, including expenses, line items, and account-to-account transfers.

## Design Defaults

1. Master data is shared across users:
   - `merchant_types`
   - `merchants`
   - `categories`
   - `products_services`
2. User-owned tables:
   - `accounts`
   - `expense_transactions`
   - `account_transfers`
3. `accounts.balance` is an application-managed snapshot value.
4. Negative balances are allowed (for credit-card and overdraft style accounts).

## ERD

The source ERD is in [Database_ERD.mmd](/c:/Users/Yoong%20Shen/Desktop/Financial%20Assitant%20Agent/docs/Database_ERD.mmd).

## Table Reference

### USERS
Stores data ownership roots.

- `user_id` (PK)
- `full_name`
- `created_at`, `updated_at`

### ACCOUNTS
Stores user spending/funding accounts.

- `account_id` (PK)
- `user_id` (FK -> `users.user_id`, `ON DELETE CASCADE`)
- `account_name` (unique per user)
- `account_type`
- `balance` (`NUMERIC(18,2)`, signed)
- `created_at`, `updated_at`

Key constraints:
- `BTRIM(account_name) <> ''`
- `BTRIM(account_type) <> ''`
- `UNIQUE (user_id, account_name)`

### MERCHANT_TYPES
Controlled list of merchant classes (extendable enum pattern).

- `merchant_type_id` (PK)
- `merchant_type_name`
- `description`
- `created_at`, `updated_at`

Key constraints:
- `BTRIM(merchant_type_name) <> ''`
- Case-insensitive uniqueness via `UNIQUE INDEX uq_merchant_types_name_ci ON LOWER(BTRIM(merchant_type_name))`

### MERCHANTS
Merchant-location rows used by expense transactions.

- `merchant_id` (PK)
- `merchant_type_id` (FK -> `merchant_types.merchant_type_id`, `ON DELETE RESTRICT`)
- `merchant_name`
- `location_name`
- `city`, `state`, `country`
- `other_name` (semantic alias for matching)
- `created_at`, `updated_at`

Key constraints:
- `BTRIM(merchant_name) <> ''`
- `BTRIM(location_name) <> ''`
- `UNIQUE (merchant_name, location_name)`

### CATEGORIES
Hierarchical expense categories.

- `category_id` (PK)
- `parent_category_id` (nullable FK -> `categories.category_id`, `ON DELETE RESTRICT`)
- `category_name`
- `category_level`
- `created_at`, `updated_at`

Key constraints:
- `BTRIM(category_name) <> ''`
- `category_level >= 1`
- Root uniqueness (case-insensitive): unique `LOWER(BTRIM(category_name))` where `parent_category_id IS NULL`
- Child uniqueness (case-insensitive): unique `(parent_category_id, LOWER(BTRIM(category_name)))` where `parent_category_id IS NOT NULL`

### PRODUCTS_SERVICES
Standardized item names for repeated products/services.

- `product_service_id` (PK)
- `default_name`
- `default_category_id` (FK -> `categories.category_id`, `ON DELETE RESTRICT`)
- `unit_of_measure`
- `created_at`, `updated_at`

Key constraints:
- `BTRIM(default_name) <> ''`
- Case-insensitive uniqueness via `UNIQUE INDEX uq_products_services_default_name_ci ON LOWER(BTRIM(default_name))`

### EXPENSE_TRANSACTIONS
Each expense payment event.

- `transaction_id` (PK)
- `user_id` (FK -> `users.user_id`, `ON DELETE CASCADE`)
- `account_id` (FK -> `accounts.account_id`, `ON DELETE RESTRICT`)
- `merchant_id` (FK -> `merchants.merchant_id`, `ON DELETE RESTRICT`)
- `transaction_datetime`
- `transaction_date`
- `total_amount`
- `notes`
- `created_at`, `updated_at`

Key constraints:
- `total_amount > 0`
- `transaction_date = transaction_datetime::date`

Trigger-enforced invariant:
- `expense_transactions.user_id` must match the owner of `account_id`

### ACCOUNT_TRANSFERS
Money movement between two accounts of the same user.

- `transfer_id` (PK)
- `user_id` (FK -> `users.user_id`, `ON DELETE CASCADE`)
- `from_account_id` (FK -> `accounts.account_id`, `ON DELETE RESTRICT`)
- `to_account_id` (FK -> `accounts.account_id`, `ON DELETE RESTRICT`)
- `transfer_datetime`
- `transfer_date`
- `amount`
- `notes`
- `created_at`, `updated_at`

Key constraints:
- `amount > 0`
- `from_account_id <> to_account_id`
- `transfer_date = transfer_datetime::date`

Trigger-enforced invariant:
- `account_transfers.user_id` must match both source and destination account owners

### EXPENSE_LINE_ITEMS
Detailed purchased items under each expense transaction.

- `line_item_id` (PK)
- `transaction_id` (FK -> `expense_transactions.transaction_id`, `ON DELETE CASCADE`)
- `product_service_id` (nullable FK -> `products_services.product_service_id`, `ON DELETE SET NULL`)
- `category_id` (FK -> `categories.category_id`, `ON DELETE RESTRICT`)
- `item_name`
- `quantity`
- `unit_price`
- `total_price`
- `created_at`, `updated_at`

Key constraints:
- `BTRIM(item_name) <> ''`
- `quantity > 0`
- `unit_price >= 0`
- `total_price >= 0`
- `ABS(total_price - ROUND(quantity * unit_price, 2)) <= 0.01`

## Transaction Types and Reporting

Use these rules in analytics and balance logic:

1. Expense (`expense_transactions`):
   - Account outflow only.
2. Transfer (`account_transfers`):
   - Source account outflow and destination account inflow.
   - Should not be counted as expense spending.

## Balance Semantics

`accounts.balance` is a stored snapshot maintained by application logic.

Recommended write pattern:

1. Begin DB transaction.
2. Insert expense/transfer row.
3. Update affected `accounts.balance` rows.
4. Commit.

This keeps history and balance updates atomic without adding DB-side balance mutation triggers.

## Naming and Uniqueness Rules

Case-insensitive uniqueness is enforced for:

- `merchant_types.merchant_type_name`
- `products_services.default_name`
- `categories.category_name` with root vs child logic

Normalization used in indexes:

- `LOWER(BTRIM(value))`

This prevents duplicates that differ only by case or accidental edge whitespace.

## Audit and Trigger Behavior

`updated_at` is automatically refreshed on every row update for all core tables via the shared `set_updated_at()` trigger function.

Ownership validation triggers:

- `trg_validate_expense_transaction_user_account`
- `trg_validate_account_transfer_user_accounts`

Both protect against cross-user references that pass foreign-key checks but violate data ownership intent.

## Operational Notes

### Docker initialization path

`docker-compose.yml` mounts:

- `./init/postgres` -> `/docker-entrypoint-initdb.d`

### Important PostgreSQL container behavior

Init scripts in `/docker-entrypoint-initdb.d` run only when the database volume is empty.

If schema files change and you need a clean re-initialization:

```bash
docker compose down -v
docker compose up -d
```

`down -v` removes data volume contents. Use with care.
