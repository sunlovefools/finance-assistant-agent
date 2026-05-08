# Expense Tracking Database Schema

**Version:** 2.0  
**Focus:** Telegram button-based expense recording flow  
**Last Updated:** 8 May 2026

---

## 1. Overview

This document defines the redesigned PostgreSQL database schema for the personal finance assistant.

The schema is designed to support a Telegram-based expense recording flow where the user selects an expense category, sub-category, merchant, amount and optional description before the transaction is stored.

The main schema changes are focused on:

- Category and sub-category structure
- Merchant location storage
- Google Places API merchant integration
- Temporary expense drafts
- Separation between normal expenses, internal transfers and transfers to other people

The schema continues to support account balance tracking, merchant reuse, category-based reporting and future expansion into detailed line-item tracking.

---

## 2. Design Principles

1. The database should support a button-driven Telegram expense flow.
2. Expense categories should be hierarchical and flexible.
3. Merchants should store latitude and longitude for distance-based lookup.
4. Merchants may come from the local database, manual user creation or Google Places API.
5. Temporary expense drafts should be stored before final transaction insertion.
6. Normal expenses and transfers should be distinguishable at the schema level.
7. Account balances should remain application-managed snapshot values.
8. Default system data and user-created data should be separated where needed.
9. The schema should remain simple enough for early-stage development.

---

## 3. High-Level Entity Structure

    users
    ├── accounts
    ├── expense_drafts
    ├── expense_transactions
    ├── account_transfers
    ├── external_transfers
    └── user-created categories / merchants

    categories
    └── hierarchical parent-child category structure

    merchants
    └── merchant_types

---

## 4. Table Summary

| Table | Purpose |
| --- | --- |
| `users` | Stores user identity and ownership root |
| `accounts` | Stores user financial accounts and balances |
| `categories` | Stores expense categories, sub-categories and category detail groups |
| `merchant_types` | Stores controlled merchant type labels |
| `merchants` | Stores merchant-location records with one primary merchant type and optional additional text-based Google Places types |
| `expense_drafts` | Stores temporary Telegram expense recording state |
| `expense_transactions` | Stores confirmed expense transactions |
| `account_transfers` | Stores transfers between the user's own accounts |
| `external_transfers` | Stores transfers from the user to other people |
| `products_services` | Optional future table for reusable item/service names |
| `expense_line_items` | Optional future table for receipt-level item tracking |

---

## 5. Table Reference

## 5.1 `users`

Stores the root identity of each user.

### SQL Definition

    CREATE TABLE users (
        user_id UUID PRIMARY KEY,
        telegram_user_id BIGINT UNIQUE,
        full_name TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );

### Column Description

| Column | Description |
| --- | --- |
| `user_id` | Primary key for the user |
| `telegram_user_id` | Telegram user identifier |
| `full_name` | User's display name |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Notes

- `telegram_user_id` is used to map Telegram messages to the correct internal user.
- `telegram_user_id` may be nullable if the system later supports other channels such as WhatsApp or web login.

---

## 5.2 `accounts`

Stores the user's financial accounts.

### SQL Definition

    CREATE TABLE accounts (
        account_id UUID PRIMARY KEY,
        user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

        account_name TEXT NOT NULL,
        account_type TEXT NOT NULL,

        balance NUMERIC(18,2) NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_accounts_name_not_empty
            CHECK (BTRIM(account_name) <> ''),

        CONSTRAINT chk_accounts_type_not_empty
            CHECK (BTRIM(account_type) <> ''),

        CONSTRAINT uq_accounts_user_account_name
            UNIQUE (user_id, account_name)
    );

### Column Description

| Column | Description |
| --- | --- |
| `account_id` | Primary key for the account |
| `user_id` | Owner of the account |
| `account_name` | User-facing account name |
| `account_type` | Account classification |
| `balance` | Application-managed account balance snapshot |
| `is_active` | Indicates whether the account can still be selected |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Suggested Account Types

    cash
    bank_account
    ewallet
    credit_card
    savings_account
    investment_account
    other

### Notes

- `balance` is a snapshot value maintained by application logic.
- Negative balances are allowed for credit card or overdraft-style accounts.
- `is_active` supports flows where the user can deactivate accounts without deleting them.
- Investment accounts is considered an account but we shouldn't show it to the user when we are recording normal expenses. We can only show it when the user selected transaction category. When the category is `Transaction / Investment / Savings`, then we can show the investment accounts.
- account_type shouldn't be a emum or a new table for now (Easier to maintain), make it free text with a check constraint to prevent empty values.

---

## 5.3 `categories`

Stores expense categories, sub-categories and optional third-level category detail groups.

### SQL Definition

    CREATE TABLE categories (
        category_id UUID PRIMARY KEY,

        parent_category_id UUID REFERENCES categories(category_id) ON DELETE RESTRICT,
        user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,

        category_name TEXT NOT NULL,
        description TEXT,
        category_level INT NOT NULL,

        flow_type TEXT NOT NULL DEFAULT 'expense',
        balance_effect TEXT NOT NULL DEFAULT 'deduct_balance',

        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        sort_order INT NOT NULL DEFAULT 0,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_categories_name_not_empty
            CHECK (BTRIM(category_name) <> ''),

        CONSTRAINT chk_categories_level_valid
            CHECK (category_level >= 1),

        CONSTRAINT chk_categories_flow_type_valid
            CHECK (flow_type IN (
                'expense',
                'internal_transfer',
                'external_transfer'
            )),

        CONSTRAINT chk_categories_balance_effect_valid
            CHECK (balance_effect IN (
                'deduct_balance',
                'no_balance_change',
                'transfer_between_accounts'
            ))
    );

### Column Description

| Column | Description |
| --- | --- |
| `category_id` | Primary key for the category |
| `parent_category_id` | Parent category for hierarchical structure |
| `user_id` | Owner of custom category; `NULL` for system default category |
| `category_name` | Category display name |
| `category_level` | Category depth level |
| `flow_type` | Defines how this category behaves in the system |
| `balance_effect` | Defines how balance should be affected |
| `is_active` | Indicates whether the category can still be selected |
| `sort_order` | Controls display order |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |
| `description` | Optional category description (Especially useful for user-created categories) |

### Category Level Meaning

| Level | Meaning | Example |
| --- | --- | --- |
| `1` | Main category | Food |
| `2` | Sub-category | Restaurant |
| `3` | Detail group | Casual Restaurant |

Note: Category levels are flexible and the system can support more than 3 levels if needed, but the current Telegram flow is designed for up to 3 levels.

### Flow Types

| Flow Type | Meaning |
| --- | --- |
| `expense` | Normal spending transaction |
| `internal_transfer` | Transfer to another account owned by the user |
| `external_transfer` | Transfer to another person or external party |

### Balance Effects

| Balance Effect | Meaning |
| --- | --- |
| `deduct_balance` | Deducts money from the selected account |
| `no_balance_change` | Records the activity without changing balance |
| `transfer_between_accounts` | Deducts money from the source account and adds money to the destination account |

### Category Uniqueness Rules

Recommended indexes:

    CREATE UNIQUE INDEX uq_categories_root_system_name_ci
    ON categories (LOWER(BTRIM(category_name)))
    WHERE parent_category_id IS NULL
    AND user_id IS NULL;

    CREATE UNIQUE INDEX uq_categories_child_system_name_ci
    ON categories (parent_category_id, LOWER(BTRIM(category_name)))
    WHERE parent_category_id IS NOT NULL
    AND user_id IS NULL;

    CREATE UNIQUE INDEX uq_categories_root_user_name_ci
    ON categories (user_id, LOWER(BTRIM(category_name)))
    WHERE parent_category_id IS NULL
    AND user_id IS NOT NULL;

    CREATE UNIQUE INDEX uq_categories_child_user_name_ci
    ON categories (user_id, parent_category_id, LOWER(BTRIM(category_name)))
    WHERE parent_category_id IS NOT NULL
    AND user_id IS NOT NULL;

### Notes

- System default categories use `user_id = NULL`.
- User-created categories use the current `user_id`.
- The hierarchy supports three levels, but the schema can support more if needed.
- `flow_type` prevents transfer-related categories from being treated the same as normal expenses.
- User-created categories are separate from system categories to allow users to customize without affecting the default options for other users.
- Category names will not be unique globally but only unique under the same parent.
- `Transaction / Investment / Savings` should use `flow_type = internal_transfer` and `balance_effect = transfer_between_accounts`.
- `Transaction to Others` should use `flow_type = external_transfer` and `balance_effect = deduct_balance`.
- `Transaction to Others` is stored in `external_transfers`, deducts from the selected source account, and is included in expense reporting.

---

## 5.4 Default Category Seed Structure

The following categories are proposed as system default records in the `categories` table.

    Food
    ├── Groceries
    ├── Restaurant
    │   ├── Budget Restaurant #Description: Used for affordable dining options such as food courts, hawker stalls, etc.
    │   ├── Casual Restaurant #Description: Better and more expensive than budget restaurants, for example fast-casual dining, regular dine-in restaurants, etc.
    │   └── Premium Restaurant #Description: Used for high-end dining experiences
    ├── Fast Food
    ├── Cafe
    ├── Snack
    └── Dessert

    Drink
    ├── Coffee
    ├── Boba
    ├── Soft Drink
    └── Other

    Home
    ├── Rent
    ├── Mortgage
    └── Household Essentials  #Description: Used for daily household items such as toilet paper, extension cords, appliances and home-use supplies.

    Utilities
    ├── Internet / WiFi
    ├── Electricity
    ├── Gas
    └── Phone

    Transportation
    ├── Parking
    ├── Vehicle Instalment / Repayment
    ├── Fuel
    ├── Public Transport
    ├── Vehicle Maintenance   #Description: Used for general vehicle maintenance such as oil change, car wash, tyre replacement, etc.
    └── Vehicle Insurance

    Personal Care
    ├── Haircut
    ├── Cosmetics
    └── Skin Care

    Life Insurance

    Self Development / Education
    ├── Books
    └── Courses

    Medical
    ├── Medicine / Pharmacy
    ├── Co-pay
    │   ├── Dental
    │   ├── Medical Consultation
    │   └── Vision
    └── Health Check-up

    Entertainment
    ├── Movie
    ├── Subscription
    ├── Games
    └── Karaoke

    Sports
    ├── Equipment
    └── Facility / Court Fee

    Personal Spending
    ├── Electronics
    ├── Gifts
    ├── Clothing
    └── Other Personal Items

    Travel
    ├── Hotels
    └── Travel Transportation

    Miscellaneous
    ├── Donation
    └── Admin / Service Fee #Description: Used for general fees that do not fit better elsewhere.

    Transaction / Investment / Savings

    Transaction to Others
    └── Family #Description: Used for transfers to family members that should be counted as expenses in reporting. Should have a sub-category for specifying the family member
    └── Friends 

### Notes

- `Budget Restaurant`, `Casual Restaurant` and `Premium Restaurant` are third-level category detail groups under `Food > Restaurant`.
- `Facility / Court Fee` is used for sports venue rental or court booking fee.
- `Household Essentials` is used for daily household items such as toilet paper, extension cords, appliances and home-use supplies.
- `Admin / Service Fee` is used for general fees that do not fit better elsewhere.
- `Life Insurance` is a main category without sub-category for now
---

## 5.5 `merchant_types`

Stores controlled merchant type labels.

### SQL Definition

    CREATE TABLE merchant_types (
        merchant_type_id UUID PRIMARY KEY,

        type_name TEXT NOT NULL,
        description TEXT,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_merchant_types_name_not_empty
            CHECK (BTRIM(type_name) <> '')
    );

### Column Description

| Column | Description |
| --- | --- |
| `merchant_type_id` | Primary key for the merchant type |
| `type_name` | Internal merchant type name |
| `description` | Optional description for the TYPE, NOT THE MERCHANT |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Recommended Unique Index

    CREATE UNIQUE INDEX uq_merchant_types_name_ci
    ON merchant_types (LOWER(BTRIM(type_name)));

### Example Merchant Types

    Restaurant
    Cafe
    Convenience Store
    Supermarket
    Pharmacy
    Gas Station
    Parking
    Hotel
    Book Store
    Clothing Store
    Electronics Store
    Medical Clinic
    Dental Clinic
    Entertainment Venue
    Sports Facility
    Other

### Notes

- `merchant_types` stores the primary merchant type used by each merchant.
- Each merchant must have exactly one primary merchant type.
- `type_name` should follow Google Places primary type naming where possible.
- If a merchant is created from Google Places, the system should match the Google Places primary type to an existing `merchant_types` row.
- If no matching merchant type exists, the system may create a new merchant type.
- If a merchant is created manually, the user should select an existing merchant type or create a new one.
- Additional Google Places types are not linked to `merchant_types`. They are stored directly as text values in `merchants.google_additional_types`.
- Merchant types are mandatory for merchants.
---

## 5.6 `merchants`

Stores merchant-location records used by expense transactions.

### SQL Definition

    CREATE TABLE merchants (
        merchant_id UUID PRIMARY KEY,

        merchant_name TEXT NOT NULL,
        display_name TEXT,
        other_name TEXT,

        primary_merchant_type_id UUID NOT NULL REFERENCES merchant_types(merchant_type_id) ON DELETE RESTRICT,

        formatted_address TEXT,
        location_name TEXT,
        city TEXT,
        state TEXT,
        country TEXT,

        latitude NUMERIC(10,7) NOT NULL,
        longitude NUMERIC(10,7) NOT NULL,
        location GEOGRAPHY(Point, 4326) NOT NULL,

        source TEXT NOT NULL DEFAULT 'user_created',

        google_place_id TEXT,
        google_additional_types TEXT[],
        google_maps_uri TEXT,

        is_user_created BOOLEAN NOT NULL DEFAULT FALSE,
        created_by_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,

        last_verified_at TIMESTAMP,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_merchants_name_not_empty
            CHECK (BTRIM(merchant_name) <> ''),

        CONSTRAINT chk_merchants_source_valid
            CHECK (source IN (
                'user_created',
                'google_places'
            ))
    );

### Column Description

| Column | Description |
| --- | --- |
| `merchant_id` | Primary key for the merchant |
| `merchant_name` | Main merchant name |
| `display_name` | User-facing merchant display name |
| `other_name` | Alias or alternative name for matching |
| `primary_merchant_type_id` | Mandatory primary merchant type for the merchant |
| `formatted_address` | Full formatted address |
| `location_name` | Short location label |
| `city` | City name |
| `state` | State or region |
| `country` | Country name |
| `latitude` | Merchant latitude |
| `longitude` | Merchant longitude |
| `location` | PostGIS geography point used for distance-based merchant search |
| `source` | Source of merchant record |
| `google_place_id` | Google Places place identifier |
| `google_additional_types` | Additional Google Places types stored as text values; these do not reference `merchant_types` |
| `google_maps_uri` | Google Maps link or URI |
| `is_user_created` | Indicates whether merchant was created by user action |
| `created_by_user_id` | User who created the merchant |
| `last_verified_at` | Last time merchant data was verified |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Merchant Source Values

| Source | Meaning |
| --- | --- |
| `user_created` | Created by the user |
| `google_places` | Created from Google Places API result |

### Recommended Indexes

    CREATE INDEX idx_merchants_location_geog
    ON merchants
    USING GIST (location);

    CREATE INDEX idx_merchants_lat_lng
    ON merchants (latitude, longitude);

    CREATE INDEX idx_merchants_name_ci
    ON merchants (LOWER(BTRIM(merchant_name)));

    CREATE UNIQUE INDEX uq_merchants_google_place_id
    ON merchants (google_place_id)
    WHERE google_place_id IS NOT NULL;

### Notes

- Each merchant row represents a specific merchant-location pair.
- Each merchant has exactly one mandatory primary merchant type through `primary_merchant_type_id`.
- Additional Google Places types are stored as text values in `google_additional_types`.
- Additional Google Places types do not reference `merchant_types`.
- `latitude` and `longitude` are stored for API compatibility with Telegram and Google Places API.
- `location` is stored as PostGIS `GEOGRAPHY(Point, 4326)` for distance-based querying and sorting.
- `google_place_id` should be stored when the merchant is selected from Google Places API.
- `source` allows the system to distinguish user-created merchants from Google Places merchants.
- `formatted_address` is mandatory for Google Places merchants but may be optional for user-created merchants.
- User-created merchants should only be visible to the creator.
---

## 5.7 `expense_drafts`

Stores temporary expense recording state before final insertion.

### SQL Definition

    CREATE TABLE expense_drafts (
        draft_id UUID PRIMARY KEY,

        user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

        telegram_chat_id BIGINT NOT NULL,
        telegram_user_id BIGINT NOT NULL,

        state TEXT NOT NULL,

        category_id UUID REFERENCES categories(category_id) ON DELETE SET NULL,
        subcategory_id UUID REFERENCES categories(category_id) ON DELETE SET NULL,
        final_category_id UUID REFERENCES categories(category_id) ON DELETE SET NULL,

        account_id UUID REFERENCES accounts(account_id) ON DELETE SET NULL,
        from_account_id UUID REFERENCES accounts(account_id) ON DELETE SET NULL,
        to_account_id UUID REFERENCES accounts(account_id) ON DELETE SET NULL,
        merchant_id UUID REFERENCES merchants(merchant_id) ON DELETE SET NULL,

        location_latitude NUMERIC(10,7),
        location_longitude NUMERIC(10,7),

        amount NUMERIC(18,2),
        description TEXT,
        transaction_datetime TIMESTAMP,

        metadata JSONB NOT NULL DEFAULT '{}',

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMP
    );

### Column Description

| Column | Description |
| --- | --- |
| `draft_id` | Primary key for the draft |
| `user_id` | User who owns the draft |
| `telegram_chat_id` | Telegram chat identifier |
| `telegram_user_id` | Telegram user identifier |
| `state` | Current draft state |
| `category_id` | Selected main category |
| `subcategory_id` | Selected sub-category |
| `final_category_id` | Final category used for transaction insertion |
| `account_id` | Selected payment account |
| `from_account_id` | Source account for transfer-style flows; nullable for normal expenses |
| `to_account_id` | Destination account for account-to-account transfer flows; nullable for normal expenses and external transfers |
| `merchant_id` | Selected merchant |
| `location_latitude` | User location latitude captured during flow |
| `location_longitude` | User location longitude captured during flow |
| `amount` | Expense amount |
| `description` | Optional user description |
| `transaction_datetime` | Transaction datetime |
| `metadata` | Additional temporary data |
| `created_at` | Draft creation timestamp |
| `updated_at` | Draft update timestamp |
| `expires_at` | Optional draft expiry timestamp |

### Notes

- Drafts allow the Telegram flow to be resumed step by step.
- `final_category_id` is the category stored in the final transaction.
- Normal expenses use `account_id`. Internal transfers use `from_account_id` and `to_account_id`. External transfers use `from_account_id`.
- `metadata` can store temporary API data such as Google Places candidates.
- Completed or cancelled drafts may be retained for debugging or deleted later.
- Drafts will have a 7 days expiry time to prevent stale drafts from lingering indefinitely
- User shouldn't have more than 1 active draft at the same time to prevent confusion
- Google Places candidate results should be stored in `metadata` under a key such as `google_places_candidates` as an array of objects containing the relevant details for each candidate. This allows the system to present the candidate options to the user without needing to create separate tables for temporary data that is only relevant during the draft flow.
- the `state` column should be updated at each step of the flow to reflect the current stage, for example: `awaiting_amount`, `awaiting_account`, `awaiting_merchant`, `awaiting_category`, `awaiting_confirmation`, etc. This allows the backend to know what kind of input to expect next and how to process it when the user responds. But there is no need to make it emum

---

## 5.8 `expense_transactions`

Stores confirmed expense transactions.

### SQL Definition

    CREATE TABLE expense_transactions (
        transaction_id UUID PRIMARY KEY,

        user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        account_id UUID NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
        merchant_id UUID NOT NULL REFERENCES merchants(merchant_id) ON DELETE RESTRICT,
        category_id UUID NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,

        transaction_datetime TIMESTAMP NOT NULL,
        transaction_date DATE NOT NULL,

        total_amount NUMERIC(18,2) NOT NULL,
        description TEXT,

        source TEXT NOT NULL DEFAULT 'telegram',

        created_from_draft_id UUID REFERENCES expense_drafts(draft_id) ON DELETE SET NULL,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_expense_transactions_amount_positive
            CHECK (total_amount > 0),

        CONSTRAINT chk_expense_transactions_date_matches_datetime
            CHECK (transaction_date = transaction_datetime::date)
    );

### Column Description

| Column | Description |
| --- | --- |
| `transaction_id` | Primary key for the expense transaction |
| `user_id` | User who owns the transaction |
| `account_id` | Account used to pay for the expense |
| `merchant_id` | Merchant where the expense happened |
| `category_id` | Final selected expense category |
| `transaction_datetime` | Full transaction datetime |
| `transaction_date` | Date-only value for easier filtering |
| `total_amount` | Total transaction amount |
| `description` | Optional transaction description |
| `source` | Source channel of the transaction |
| `created_from_draft_id` | Related draft record |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Source Values

    telegram
    manual
    imported
    ai_assisted

### Notes

- `category_id` is stored directly because the Telegram flow records one category per expense.
- `merchant_id` is mandatory because `expense_transactions` only stores normal merchant-based spending.
- Internal transfers are stored in `account_transfers`.
- Transfers to other people are stored in `external_transfers`.
- Account balance deduction is handled by application logic after insertion.
- `transaction_date` should be generated automatically from `transaction_datetime` to ensure consistency in date-based reporting and filtering.
- One transaction should only have one category

---

## 5.9 `account_transfers`

Stores transfers between the user's own accounts.

### SQL Definition

    CREATE TABLE account_transfers (
        transfer_id UUID PRIMARY KEY,

        user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,

        from_account_id UUID NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
        to_account_id UUID NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,

        transfer_datetime TIMESTAMP NOT NULL,
        transfer_date DATE NOT NULL,

        amount NUMERIC(18,2) NOT NULL,
        description TEXT,

        created_from_draft_id UUID REFERENCES expense_drafts(draft_id) ON DELETE SET NULL,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_account_transfers_amount_positive
            CHECK (amount > 0),

        CONSTRAINT chk_account_transfers_different_accounts
            CHECK (from_account_id <> to_account_id),

        CONSTRAINT chk_account_transfers_date_matches_datetime
            CHECK (transfer_date = transfer_datetime::date)
    );

### Column Description

| Column | Description |
| --- | --- |
| `transfer_id` | Primary key for the transfer |
| `user_id` | Owner of the transfer |
| `from_account_id` | Source account |
| `to_account_id` | Destination account |
| `transfer_datetime` | Full transfer datetime |
| `transfer_date` | Date-only value for filtering |
| `amount` | Transfer amount |
| `description` | Optional transfer description |
| `created_from_draft_id` | Related draft record |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Notes

- Account transfers should not be counted as expense spending.
- Application logic should deduct from the source account and add to the destination account.
- Every `Transaction / Investment / Savings`should end up in this table.
- This table should affect the balance of the accounts involved, but should not be treated as an expense in reporting.
---

## 5.10 `external_transfers`

Stores transfers from the user to another person or external party.

### SQL Definition

    CREATE TABLE external_transfers (
        external_transfer_id UUID PRIMARY KEY,

        user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
        from_account_id UUID NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,

        recipient_name TEXT NOT NULL,
        recipient_group TEXT,

        category_id UUID REFERENCES categories(category_id) ON DELETE RESTRICT,

        transfer_datetime TIMESTAMP NOT NULL,
        transfer_date DATE NOT NULL,

        amount NUMERIC(18,2) NOT NULL,
        description TEXT,

        created_from_draft_id UUID REFERENCES expense_drafts(draft_id) ON DELETE SET NULL,

        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

        CONSTRAINT chk_external_transfers_amount_positive
            CHECK (amount > 0),

        CONSTRAINT chk_external_transfers_recipient_name_not_empty
            CHECK (BTRIM(recipient_name) <> ''),

        CONSTRAINT chk_external_transfers_date_matches_datetime
            CHECK (transfer_date = transfer_datetime::date)
    );

### Column Description

| Column | Description |
| --- | --- |
| `external_transfer_id` | Primary key for the external transfer |
| `user_id` | Owner of the record |
| `from_account_id` | Account where money leaves from |
| `recipient_name` | Recipient child category under the recipient group, such as Mother, Father, Sibling or a specific friend name |
| `recipient_group` | Recipient sub-category under `Transaction to Others`, such as Family or Friends |
| `category_id` | Category reference |
| `transfer_datetime` | Full transfer datetime |
| `transfer_date` | Date-only value for filtering |
| `amount` | Transfer amount |
| `description` | Optional description |
| `created_from_draft_id` | Related draft record |
| `created_at` | Row creation timestamp |
| `updated_at` | Row update timestamp |

### Notes

- This table is used for `Transaction to Others`.
- This is separate from `expense_transactions` because the meaning is different from normal merchant spending.
- This structure supports simple person-based transfers without requiring a full recipient table yet.
- This will be counted as expenses in reporting, but the category can be used to filter or group them separately from merchant expenses.
- external transfers should not have a merchant
- `recipient_group` represents the sub-category under `Transaction to Others`.
- `recipient_name` represents the child category under the selected recipient group.

---

## 6. Balance Semantics

Account balances are stored in `accounts.balance`.

The balance is maintained by application logic rather than database triggers.

### Normal Expense

Table used:

    expense_transactions

Balance effect:

    Deduct total_amount from selected account.

### Internal Transfer

Table used:

    account_transfers

Balance effect:

    Deduct amount from source account.
    Add amount to destination account.

### External Transfer

Table used:

    external_transfers

Balance effect:

    Deduct amount from source account.

Reporting effect:

    Include in expense reports, with the ability to filter or group separately from merchant expenses.
---

## 7. Merchant Distance Search Support

Merchant location search is supported by these columns in `merchants`:

    latitude
    longitude
    location
    source
    google_place_id
    primary_merchant_type_id
    google_additional_types

### Distance-Based Search Rule

Saved merchants and Google Places merchants can be ranked using effective distance.

    effective_distance_m = actual_distance_m - source_priority_bonus_m

Suggested source priority bonus (the bonus is 10m for saved merchants to give them an advantage over Google Places merchants):

| Source | Bonus |
| --- | --- |
| Saved database merchant | 10 meters |
| Google Places merchant | 0 meters |

### Example

| Merchant | Source | Actual Distance | Effective Distance |
| --- | --- | ---: | ---: |
| Restaurant ABC | Saved | 15m | 5m |
| Restaurant XYZ | Google Places | 5m | 5m |

### Notes

- The ranking calculation belongs in application logic.
- `latitude` and `longitude` are kept for API compatibility.
- `location GEOGRAPHY(Point, 4326)` is used for efficient distance-based querying in PostgreSQL.
- Saved merchants and Google Places merchants are merged by the backend before returning merchant choices to the user.
- Google Places candidates are only inserted into `merchants` after the user selects them.
---

## 8. Transaction Type and Reporting Rules

### Expense Spending

Included tables:

    expense_transactions

Included in expense reports:

    Yes

### Internal Account Transfer

Included tables:

    account_transfers

Included in expense reports:

    No

### External Transfer to Others

Included tables:

    external_transfers

Included in expense reports:

    Yes, but can be filtered or grouped separately by category
---

## 9. Audit Fields

All core tables use the following audit fields:

    created_at
    updated_at

Recommended trigger:

    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;

### Notes

- `created_at` is set once when the row is created.
- `updated_at` is refreshed on every update.
---

## 10. Ownership and Validation Rules

### User-Owned Tables

    accounts
    expense_drafts
    expense_transactions
    account_transfers
    external_transfers

### Shared or Semi-Shared Tables

    categories
    merchant_types
    merchants
### Ownership Rules

1. A user can only create transactions for their own accounts.
2. A user can only create transfers between accounts they own.
3. A user-created category belongs to that user and only visible to that user.
4. A system default category has `user_id = NULL`.
5. A user-created merchant must store `created_by_user_id`.
6. User-created merchants are only visible to the creator.
7. Google Places merchants may be shared globally if they have a valid `google_place_id`.

### TODO

- TODO: Add database triggers to validate account ownership for expenses and transfers.
- TODO: Add validation to prevent cross-user draft-to-transaction insertion.

---

## 11. Recommended Initial MVP Tables

For the first implementation, the minimum recommended schema is:

    users
    accounts
    categories
    merchant_types
    merchants
    expense_drafts
    expense_transactions
    account_transfers
    external_transfers

Optional later tables:

    products_services
    expense_line_items
    transfer_recipients
    merchant_aliases
    transaction_audit_logs

---
