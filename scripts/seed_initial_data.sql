-- ============================================================================
-- Seed Script: Initial User, Accounts, Merchant Types, and Merchants
-- ============================================================================
-- Purpose
-- - Seed baseline records into an already running PostgreSQL container
--   without restarting the container.
-- - Keep script idempotent: rerunning updates target rows instead of creating
--   duplicates.
--
-- Scope
-- - Users:
--     * Ng Yoong Shen
-- - Accounts for that user:
--     * TNG E-wallet  | ewallet      | 100.00
--     * Maybank       | bank-account | 100.00
--     * Cash          | cash         | 100.00
-- - Merchant types:
--     * restaurant
--     * petrol_station
--     * grocery
-- - Merchants:
--     * Petronas  / Pusat Bandar Puchong  / petrol_station
--     * McDonald  / Bandar Puteri Puchong / restaurant
--     * Lotus     / Pusat Bandaar Puchong / grocery
--
-- How to run (PowerShell)
-- - From repository root:
--
-- $env:POSTGRES_USER="finance_assistant_application_user"
-- $env:POSTGRES_DB="finance_db"
-- Get-Content -Raw ".\scripts\seed_initial_data.sql" | docker exec -i financial-assistant-postgres psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -v ON_ERROR_STOP=1

--
-- Preconditions
-- - Docker container `financial-assistant-postgres` is running.
-- - Schema from init/postgres/postgres_init.sql has already been initialized.
-- - Environment variables POSTGRES_USER and POSTGRES_DB are set in shell.
--
-- Rerun behavior
-- - User: reuses first matching full_name if already present.
-- - Accounts: upsert by (user_id, account_name), updates type/balance.
-- - Merchant types: normalized update-then-insert using LOWER(BTRIM(...)).
-- - Merchants: upsert by (merchant_name, location_name), updates details/type.
--
-- Post-run output
-- - Script prints final summaries for user, accounts, merchant types, merchants.
-- ============================================================================

BEGIN;

DO $$
DECLARE
    v_user_id BIGINT;
    v_restaurant_type_id BIGINT;
    v_petrol_type_id BIGINT;
    v_grocery_type_id BIGINT;
BEGIN
    -- Resolve existing user row first so reruns keep a stable owner.
    SELECT u.user_id
    INTO v_user_id
    FROM users u
    WHERE u.full_name = 'Ng Yoong Shen'
    ORDER BY u.user_id
    LIMIT 1;

    -- Insert user only if not found.
    IF v_user_id IS NULL THEN
        INSERT INTO users (full_name)
        VALUES ('Ng Yoong Shen')
        RETURNING user_id INTO v_user_id;
    END IF;

    -- Upsert accounts linked to the resolved user_id.
    INSERT INTO accounts (user_id, account_name, account_type, balance)
    VALUES
        (v_user_id, 'TNG E-wallet', 'ewallet', 100.00),
        (v_user_id, 'Maybank', 'bank-account', 100.00),
        (v_user_id, 'Cash', 'cash', 100.00)
    ON CONFLICT (user_id, account_name)
    DO UPDATE SET
        account_type = EXCLUDED.account_type,
        balance = EXCLUDED.balance,
        updated_at = NOW();

    -- Merchant type upsert pattern compatible with case-insensitive
    -- expression unique index.
    WITH desired(merchant_type_name, description) AS (
        VALUES
            ('restaurant', 'Food and beverage outlets such as cafes and fast-food chains.'),
            ('petrol_station', 'Fuel stations for refueling vehicles and related purchases.'),
            ('grocery', 'Retail stores for household groceries and daily essentials.')
    )
    UPDATE merchant_types mt
    SET
        merchant_type_name = d.merchant_type_name,
        description = d.description,
        updated_at = NOW()
    FROM desired d
    WHERE LOWER(BTRIM(mt.merchant_type_name)) = LOWER(BTRIM(d.merchant_type_name));

    WITH desired(merchant_type_name, description) AS (
        VALUES
            ('restaurant', 'Food and beverage outlets such as cafes and fast-food chains.'),
            ('petrol_station', 'Fuel stations for refueling vehicles and related purchases.'),
            ('grocery', 'Retail stores for household groceries and daily essentials.')
    )
    INSERT INTO merchant_types (merchant_type_name, description)
    SELECT d.merchant_type_name, d.description
    FROM desired d
    WHERE NOT EXISTS (
        SELECT 1
        FROM merchant_types mt
        WHERE LOWER(BTRIM(mt.merchant_type_name)) = LOWER(BTRIM(d.merchant_type_name))
    );

    -- Resolve merchant_type_id values for merchant upserts.
    SELECT mt.merchant_type_id
    INTO v_restaurant_type_id
    FROM merchant_types mt
    WHERE LOWER(BTRIM(mt.merchant_type_name)) = 'restaurant'
    ORDER BY mt.merchant_type_id
    LIMIT 1;

    SELECT mt.merchant_type_id
    INTO v_petrol_type_id
    FROM merchant_types mt
    WHERE LOWER(BTRIM(mt.merchant_type_name)) = 'petrol_station'
    ORDER BY mt.merchant_type_id
    LIMIT 1;

    SELECT mt.merchant_type_id
    INTO v_grocery_type_id
    FROM merchant_types mt
    WHERE LOWER(BTRIM(mt.merchant_type_name)) = 'grocery'
    ORDER BY mt.merchant_type_id
    LIMIT 1;

    IF v_restaurant_type_id IS NULL OR v_petrol_type_id IS NULL OR v_grocery_type_id IS NULL THEN
        RAISE EXCEPTION 'Could not resolve one or more merchant_type_id values after upsert.';
    END IF;

    -- Upsert merchants by (merchant_name, location_name).
    INSERT INTO merchants (
        merchant_type_id,
        merchant_name,
        location_name,
        city,
        state,
        country,
        other_name
    )
    VALUES
        (v_petrol_type_id, 'Petronas', 'Pusat Bandar Puchong', 'Puchong', 'Selangor', 'Malaysia', NULL),
        (v_restaurant_type_id, 'McDonald', 'Bandar Puteri Puchong', 'Puchong', 'Selangor', 'Malaysia', 'mcdonald near setiawalk'),
        (v_grocery_type_id, 'Lotus', 'Pusat Bandaar Puchong', 'Puchong', 'Selangor', 'Malaysia', NULL)
    ON CONFLICT (merchant_name, location_name)
    DO UPDATE SET
        merchant_type_id = EXCLUDED.merchant_type_id,
        city = EXCLUDED.city,
        state = EXCLUDED.state,
        country = EXCLUDED.country,
        other_name = EXCLUDED.other_name,
        updated_at = NOW();
END
$$ LANGUAGE plpgsql;

-- Final summaries for verification.
SELECT
    u.user_id,
    u.full_name,
    u.created_at,
    u.updated_at
FROM users u
WHERE u.full_name = 'Ng Yoong Shen'
ORDER BY u.user_id;

SELECT
    a.account_id,
    a.user_id,
    a.account_name,
    a.account_type,
    a.balance,
    a.updated_at
FROM accounts a
JOIN users u ON u.user_id = a.user_id
WHERE u.full_name = 'Ng Yoong Shen'
  AND a.account_name IN ('TNG E-wallet', 'Maybank', 'Cash')
ORDER BY a.account_id;

SELECT
    mt.merchant_type_id,
    mt.merchant_type_name,
    mt.description,
    mt.updated_at
FROM merchant_types mt
WHERE LOWER(BTRIM(mt.merchant_type_name)) IN ('restaurant', 'petrol_station', 'grocery')
ORDER BY mt.merchant_type_id;

SELECT
    m.merchant_id,
    m.merchant_name,
    m.location_name,
    mt.merchant_type_name,
    m.city,
    m.state,
    m.country,
    m.other_name,
    m.updated_at
FROM merchants m
JOIN merchant_types mt ON mt.merchant_type_id = m.merchant_type_id
WHERE (m.merchant_name = 'Petronas' AND m.location_name = 'Pusat Bandar Puchong')
   OR (m.merchant_name = 'McDonald' AND m.location_name = 'Bandar Puteri Puchong')
   OR (m.merchant_name = 'Lotus' AND m.location_name = 'Pusat Bandaar Puchong')
ORDER BY m.merchant_id;

COMMIT;
