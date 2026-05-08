# Expense Recording Workflow Specification

**Version:** 4.0  
**Focus:** Telegram button-based expense recording flow  
**Last Updated:** 8 May 2026

---

## 1. Overview

This document defines the expense recording workflow for the Telegram bot.

The workflow is button-driven and draft-based. The user starts by selecting an expense category, followed by sub-category, account, location-based merchant selection, amount and description. The backend stores the collected information in an expense draft first. The final transaction is only inserted into the database after the user confirms the completed draft.

This version includes account selection after category and sub-category selection. Account options are filtered based on the selected category type.

---

## 2. Main Workflow Summary

1. User sends `/add_expenses`.
2. Bot creates a new expense draft.
3. Bot asks user to select an expense category.
4. User selects category.
5. Bot asks user to select sub-category.
6. User selects sub-category or category detail group.
6a. If the selected category has child categories, bot asks user to select category detail group or skip.
7. Bot asks user to select account.
8. Backend filters account options based on selected category type. (If the category is `Transaction / Investment / Savings`, investment accounts are shown. Otherwise, only spending accounts are shown.)
9. Bot requests user location. (Is it possible to get user location from the previous request? Together when selecting the account)
10. Backend searches saved merchants and Google Places merchants near the location.
11. Bot displays top merchant candidates.
12. User selects merchant or creates a new merchant.
13. Bot asks for total amount.
14. User enters amount.
15. Bot asks for description.
16. User enters description or skips.
17. Bot shows final confirmation.
18. User confirms, edits or cancels.
19. If confirmed, backend inserts transaction and updates account balance according to transaction type.

---

## 3. Main Expense Recording Flow
## 3.1 Start Flow

User sends:

    /add_expenses

Backend actions:

1. Find user by `telegram_user_id`.
2. Create new `expense_draft`.
3. Set `draft.state = WAITING_FOR_CATEGORY`.

Bot replies:

    Choose expense category:

    [Food] [Drink]
    [Home] [Utilities]
    [Transportation] [Personal Care]
    [Life Insurance]
    [Self Development / Education]
    [Medical] [Entertainment]
    [Sports] [Personal Spending]
    [Travel] [Miscellaneous]
    [Transaction / Investment / Savings]
    [Transaction to Others]
    [+ Add New Category]
    [Cancel]

---

## 3.2 Category Selection

User selects:

    Food

Backend actions:

1. Save selected `category_id` in the draft.
2. Find child categories where `parent_category_id = selected category_id`.
3. Set `draft.state = WAITING_FOR_SUBCATEGORY`.

Bot replies:

    Choose sub-category under Food:

    [Groceries]
    [Restaurant]
    [Fast Food]
    [Cafe]
    [Snack]
    [Dessert]
    [+ Add New Subcategory]
    [Back]
    [Cancel]

---

## 3.3 Subcategory Selection

User selects:

    Restaurant

Backend actions:

1. Save selected `subcategory_id` in the draft.
2. Check whether the selected sub-category has child categories.
3. If child categories exist, move to category detail selection.
4. If no child categories exist, save selected sub-category as `final_category_id`.

If the selected sub-category has child categories, bot replies:

    Choose restaurant type:

    [Budget Restaurant]
    [Casual Restaurant]
    [Premium Restaurant]
    [Skip]
    [+ Add New Detail Group]
    [Back]
    [Cancel]

If user selects:

    Casual Restaurant

Backend actions:

1. Save selected category detail group as `final_category_id`.
2. Set `draft.state = WAITING_FOR_ACCOUNT`.

If user presses:

    [Skip]

Backend actions:

1. Use the selected sub-category as `final_category_id`.
2. Set `draft.state = WAITING_FOR_ACCOUNT`.

---

## 3.4 Account Selection

After `final_category_id` is selected, the bot asks the user to select an account.

The account list must be filtered by:

1. Current `user_id`.
2. Active accounts only.
3. Selected category flow type.

State naming:

- Normal expense account selection uses `WAITING_FOR_ACCOUNT`.
- Internal and external transfer account selection starts with `WAITING_FOR_SOURCE_ACCOUNT`.

---

### 3.4.1 Normal Expense Account Selection

For normal expense categories such as Food, Drink, Transportation, Medical, Entertainment and similar categories, only spending accounts should be shown.

Example account types shown:

    cash
    bank_account
    ewallet
    credit_card

Bot replies:

    Which account did you use?

    [Cash]
    [MAE]
    [Touch 'n Go eWallet]
    [Credit Card]
    [Back]
    [Cancel]

Backend actions after user selects account:

1. Save selected `account_id` in the draft.
2. Set `draft.state = WAITING_FOR_LOCATION`.

---

### 3.4.2 Transaction / Investment / Savings Account Selection

If the selected category is:

    Transaction / Investment / Savings

Then investment and savings accounts are allowed to appear in the account list.

Example account types shown:

    cash
    bank_account
    ewallet
    savings_account
    investment_account

Bot replies:

    Select source account:

    [Cash]
    [MAE]
    [Touch 'n Go eWallet]
    [Bank Account]
    [Back]
    [Cancel]

Backend actions after source account is selected:

1. Save `from_account_id` in the draft.
2. Set `draft.state = WAITING_FOR_DESTINATION_ACCOUNT`.

Bot asks:

    Select destination account:

    [Savings Account]
    [Investment Account]
    [ASNB]
    [Brokerage Account]
    [+ Add New Account]
    [Back]
    [Cancel]

Backend actions after destination account is selected:

1. Save `to_account_id` in the draft.
2. Infer the insert path from the selected category `flow_type = internal_transfer`.
3. Set `draft.state = WAITING_FOR_AMOUNT`.

Notes:

- Investment accounts should only be visible when the selected category is `Transaction / Investment / Savings`.
- Investment accounts should not appear in normal expense account selection.
- This flow may skip merchant selection because internal transfers usually do not require a merchant.
---

### 3.4.3 Transaction to Others Account Selection

If the selected category is:

    Transaction to Others

Then the bot should ask for the account where the money leaves from.

Bot replies:

    Which account did you transfer from?

    [Cash]
    [MAE]
    [Touch 'n Go eWallet]
    [Bank Account]
    [Back]
    [Cancel]

Backend actions:

1. Save selected `from_account_id` in the draft.
2. Infer the insert path from the selected category `flow_type = external_transfer`.
3. Set `draft.state = WAITING_FOR_RECIPIENT`.
---

## 3.5 Location Collection

For normal expense categories, after account selection is completed, the bot requests the user's location.

Bot replies:

    Please share your current location so I can find nearby merchants.

    [Share Location]
    [Skip Location]
    [Back]
    [Cancel]

Backend receives:

    {
      "latitude": 3.1234567,
      "longitude": 101.1234567
    }

Backend actions:

1. Save `location_latitude` in the draft.
2. Save `location_longitude` in the draft.
3. Set `draft.state = WAITING_FOR_MERCHANT`.
4. Start merchant search using the received location.

If user presses:

    [Skip Location]

Backend actions:

1. Leave `location_latitude` and `location_longitude` empty.
2. Set `draft.state = WAITING_FOR_MERCHANT`.
3. Show recent merchants used by the same user under the same final category.
4. Allow the user to add a new merchant.

Notes:

- Skipping location means the backend cannot perform nearby merchant search.
- The fallback merchant choices should be recent merchants under the same final category.
- If the user adds a new merchant after skipping location, the user must provide either a Google Maps URL or a manually entered address that the backend can resolve to coordinates.
---

## 3.6 Merchant Search

Backend performs two searches:

1. Search saved merchants from the database by distance.
2. Search Google Places API near the user's location.

Saved merchant search uses:

    user location latitude
    user location longitude
    merchant latitude
    merchant longitude
    merchant source
    merchant type
    selected category

Google Places search uses:

    user location latitude
    user location longitude
    search radius
    included place types based on selected category

Example category-to-Google-Places mapping:

| Selected Category | Google Place Types |
| --- | --- |
| Food > Restaurant | restaurant |
| Food > Cafe | cafe |
| Food > Groceries | supermarket, grocery_store |
| Drink > Coffee | cafe, coffee_shop |
| Transportation > Fuel | gas_station |
| Transportation > Parking | parking, parking_lot |
| Medical > Medicine / Pharmacy | pharmacy |
| Travel > Hotels | hotel |
---

## 3.7 Merchant Ranking and Merge Rules

Backend merges saved merchants and Google Places merchants into one candidate list.

Ranking rule:

    effective_distance_m = actual_distance_m - source_priority_bonus_m

Suggested source priority bonus:

| Source | Priority Bonus |
| --- | ---: |
| Saved database merchant | 10 meters |
| Google Places merchant | 0 meters |

Sorting order:

1. `effective_distance_m` ascending.
2. Saved merchants before Google Places merchants if effective distance is the same.
3. `actual_distance_m` ascending.
4. Merchant name ascending.

Rules:

1. Show top 10 merchants only.
2. Saved merchants receive 10m prioritisation.
3. Google Places merchants are not inserted immediately during search.
4. If user selects a saved merchant, use the existing `merchant_id`.
5. If user selects a Google Places merchant, create the merchant record first, then use the new `merchant_id`.

---

## 3.8 Merchant List Returned to User

Bot replies:

    Choose merchant near you:

    [Restaurant ABC - Saved - 15m away]
    [Restaurant XYZ - Google Places - 5m away]
    [Restaurant 123 - Saved - 30m away]
    [Restaurant 456 - Google Places - 25m away]

    [Show Recent Restaurant Merchants]
    [+ Add New Merchant]
    [Back]
    [Cancel]

Backend state:

    draft.state = WAITING_FOR_MERCHANT

If the user skipped location, the bot should not show nearby merchant candidates. Instead, it should show recent merchants for the same final category and the same add-new-merchant option.

---

## 3.9 Recent Merchant by Category

If user presses:

    [Show Recent Restaurant Merchants]

Backend searches recent merchants used by the same user and same final category.

Example query logic:

    SELECT merchant_id, merchant_name, COUNT(*), MAX(transaction_datetime)
    FROM expense_transactions
    WHERE user_id = :user_id
    AND category_id = :final_category_id
    GROUP BY merchant_id, merchant_name
    ORDER BY MAX(transaction_datetime) DESC
    LIMIT 10;

Bot replies:

    Recent merchants for Restaurant:

    [McDonald's - Last used 2 days ago]
    [KFC - Last used 5 days ago]
    [Restaurant ABC - Last used 1 week ago]

    [Back to Nearby Merchants]
    [+ Add New Merchant]
    [Cancel]

Backend action after user selects a recent merchant:

1. Save selected `merchant_id` in the draft.
2. Set `draft.state = WAITING_FOR_AMOUNT`.

---

## 3.10 Merchant Selected

User selects:

    Restaurant ABC - Saved - 15m away

Backend actions:

1. Save selected `merchant_id` in the draft.
2. Set `draft.state = WAITING_FOR_AMOUNT`.

Bot replies:

    Enter total amount:

---

## 3.11 Amount Entry

User enters:

    25.90

Backend validates:

1. Amount is numeric.
2. Amount is greater than 0.
3. Save amount in draft.
4. Set `draft.state = WAITING_FOR_DESCRIPTION`.

Bot replies:

    Add description?

    Example: Lunch with friends

    [Skip]
    [Back]
    [Cancel]

---

## 3.12 Description Entry

User enters:

    Lunch after class

Or user presses:

    [Skip]

Backend actions:

1. Save description or `NULL`.
2. Set `transaction_datetime = NOW()`.
3. Check whether all required fields are completed.
4. Set `draft.state = WAITING_FOR_CONFIRMATION`.

---

## 3.13 Confirmation

Bot replies:

    Please confirm this expense:

    Category: Food > Restaurant > Casual Restaurant
    Merchant: Restaurant ABC
    Distance: 15m away
    Amount: RM25.90
    Account: MAE
    Date: 8 May 2026
    Description: Lunch after class

    [Confirm]
    [Edit]
    [Cancel]

Rules:

1. No transaction is inserted before user confirmation.
2. User can edit any draft field before confirming.
3. User can cancel the draft.
4. Backend inserts the transaction only after `[Confirm]`.

---

## 3.14 Final Insert for Normal Expense

If user presses:

    [Confirm]

Backend actions:

1. Begin database transaction.
2. Insert row into `expense_transactions`.
3. Deduct `total_amount` from selected account balance.
4. Mark draft as `COMPLETED`.
5. Commit database transaction.

If any step fails:

1. Roll back database transaction.
2. Keep draft available for retry.
3. Show error message to user.

Bot replies:

    Expense recorded successfully.

    RM25.90 at Restaurant ABC
    Category: Food > Restaurant > Casual Restaurant

---

## 4. Transaction / Investment / Savings Flow

This flow is used when the selected category is:

    Transaction / Investment / Savings

This flow is not treated as normal merchant spending.

---

## 4.1 Account Selection

Bot asks for source account:

    Select source account:

    [MAE]
    [Touch 'n Go eWallet]
    [Cash]
    [Bank Account]
    [Back]
    [Cancel]

User selects:

    MAE

Backend actions:

1. Save `from_account_id`.
2. Set `draft.state = WAITING_FOR_DESTINATION_ACCOUNT`.

Bot asks for destination account:

    Select destination account:

    [Savings Account]
    [Investment Account]
    [ASNB]
    [Brokerage Account]
    [+ Add New Account]
    [Back]
    [Cancel]

User selects:

    Investment Account

Backend actions:

1. Save `to_account_id`.
2. Set `draft.state = WAITING_FOR_AMOUNT`.

---

## 4.2 Amount Entry

Bot asks:

    Enter transfer amount:

User enters:

    500.00

Backend actions:

1. Validate amount.
2. Save amount.
3. Set `draft.state = WAITING_FOR_DESCRIPTION`.

---

## 4.3 Description Entry

Bot asks:

    Add description?

    Example: Monthly investment contribution

    [Skip]

User enters:

    Monthly investment contribution

Backend actions:

1. Save description.
2. Set `transaction_datetime = NOW()`.
3. Set `draft.state = WAITING_FOR_CONFIRMATION`.

---

## 4.4 Confirmation

Bot replies:

    Please confirm this transfer:

    Type: Transaction / Investment / Savings
    From: MAE
    To: Investment Account
    Amount: RM500.00
    Date: 8 May 2026
    Description: Monthly investment contribution

    [Confirm]
    [Edit]
    [Cancel]

---

## 4.5 Final Insert

If user presses:

    [Confirm]

Backend actions:

1. Begin database transaction.
2. Insert row into `account_transfers`.
3. Deduct amount from the source account.
4. Add amount to the destination account.
5. Mark draft as `COMPLETED`.
6. Commit database transaction.
---

## 5. Transaction to Others Flow

This flow is used when the selected category is:

    Transaction to Others

---

## 5.1 Account Selection

Bot asks:

    Which account did you transfer from?

    [Cash]
    [MAE]
    [Touch 'n Go eWallet]
    [Bank Account]
    [Back]
    [Cancel]

Backend actions after selection:

1. Save selected `from_account_id`.
2. Set `draft.state = WAITING_FOR_RECIPIENT`.

---

## 5.2 Recipient Selection

Bot asks:

    Who did you transfer to?

    [Family]
    [+ Add Recipient]
    [Enter Manually]
    [Back]
    [Cancel]

If user selects:

    Family

Bot replies:

    Select family member:

    [Mother]
    [Father]
    [Sibling]
    [+ Add Family Member]
    [Back]
    [Cancel]

Backend actions:

1. Save selected `recipient_group` and `recipient_name`.
2. Set `draft.state = WAITING_FOR_AMOUNT`.

Recipient meaning:

- `recipient_group` stores the selected sub-category under `Transaction to Others`, such as `Family` or `Friends`.
- `recipient_name` stores the selected child category under that group, such as `Mother`, `Father`, `Sibling` or a specific friend name.
- For MVP, recipient values are stored as text in `external_transfers`; there is no separate recipient table.
---

## 5.3 Amount, Description and Confirmation

The amount and description flow follows the same structure as normal expenses.

Confirmation example:

    Please confirm this transfer:

    Type: Transaction to Others
    Recipient: Mother
    Account: MAE
    Amount: RM300.00
    Date: 8 May 2026
    Description: Monthly family support

    [Confirm]
    [Edit]
    [Cancel]

---

## 5.4 Final Insert

If user presses:

    [Confirm]

Backend actions:

1. Begin database transaction.
2. Insert row into `external_transfers`.
3. Deduct amount from selected source account.
4. Mark draft as `COMPLETED`.
5. Commit database transaction.
---

## 6. Add New Category Flow

---

## 6.1 Add New Main Category

User presses:

    [+ Add New Category]

Bot asks:

    Enter new category name:

User enters:

    Pet Care

Backend actions:

1. Create category with `parent_category_id = NULL`.
2. Set `user_id = current user_id`.
3. Set `category_level = 1`.
4. Set `flow_type = expense`.
5. Set `balance_effect = deduct_balance`.
6. Return to main category flow.

Bot replies:

    Category added: Pet Care

    Now choose sub-category:

    [+ Add New Subcategory]
    [Skip Subcategory]
    [Cancel]

---

## 6.2 Add New Subcategory

User presses:

    [+ Add New Subcategory]

Bot asks:

    Enter new sub-category under Food:

User enters:

    Hawker Food

Backend actions:

1. Create category.
2. Set `parent_category_id = Food`.
3. Set `category_level = 2`.
4. Set `user_id = current user_id`.
5. Return to current expense draft flow.

Bot replies:

    Sub-category added: Hawker Food

    Continue with account selection.

Backend actions:

1. Save new subcategory as `final_category_id`.
2. Set `draft.state = WAITING_FOR_ACCOUNT`.

---

## 6.3 Add New Detail Group

User presses:

    [+ Add New Detail Group]

Bot asks:

    Enter new detail group under Restaurant:

User enters:

    Japanese Restaurant

Backend actions:

1. Create category.
2. Set `parent_category_id = Restaurant`.
3. Set `category_level = 3`.
4. Set `user_id = current user_id`.
5. Save new detail group as `final_category_id`.
6. Set `draft.state = WAITING_FOR_ACCOUNT`.

Bot replies:

    Detail group added: Japanese Restaurant

    Continue with account selection.

---

## 7. Add New Merchant Flow

---

## 7.1 Start Add Merchant

User presses:

    [+ Add New Merchant]

Backend actions:

1. Save current draft state.
2. Set `draft.state = WAITING_FOR_NEW_MERCHANT_NAME`.

Bot replies:

    Enter merchant name:

---

## 7.2 Merchant Name

User enters:

    Restaurant ABC

Backend actions:

1. Save `merchant_name = Restaurant ABC` in draft metadata.
2. Set `draft.state = WAITING_FOR_NEW_MERCHANT_PRIMARY_TYPE`.

Bot replies:

    Choose primary merchant type:

    [Restaurant]
    [Cafe]
    [Convenience Store]
    [Supermarket]
    [Pharmacy]
    [Parking]
    [Gas Station]
    [Hotel]
    [+ Add New Merchant Type]
    [Back]
    [Cancel]

---

## 7.3 Primary Merchant Type

User selects:

    Restaurant

Backend actions:

1. Save selected `primary_merchant_type_id` in draft metadata.
2. Set `draft.state = WAITING_FOR_NEW_MERCHANT_ADDITIONAL_TYPES`.

Bot replies:

    Choose additional types if any:

    [Food]
    [Casual Dining]
    [Halal]
    [Chain Store]
    [Skip]
    [Back]
    [Cancel]
---

## 7.4 Merchant Address / Location

Bot replies:

    How do you want to set the merchant location?

    [Use my current location]
    [Send Google Maps link]
    [Enter address manually]
    [Back]
    [Cancel]

Rules:

1. A merchant cannot be saved without latitude and longitude.
2. If the user chooses manual merchant creation, the bot must collect either a Google Maps URL or a manually entered address.
3. A Google Maps URL should be resolved by the backend into merchant details such as name, formatted address, coordinates, Google place ID when available, and Google Maps URI.
4. A manually entered address must be geocoded into latitude and longitude before the merchant is inserted.
5. If the backend cannot resolve coordinates, the bot should ask the user to provide another address, send a Google Maps URL, or cancel merchant creation.

---

### 7.4.1 Option A: Use Current Location

User presses:

    [Use my current location]

Backend actions:

1. Use `draft.location_latitude`.
2. Use `draft.location_longitude`.
3. Reverse geocode if needed.
4. Save merchant only if coordinates are available.
---

### 7.4.2 Option B: Send Google Maps Link

User sends:

    Google Maps link

Backend actions:

1. Parse Google Maps link.
2. Extract `place_id` or coordinates if possible.
3. Call Google Places API or geocoding service if needed.
4. Save formatted address.
5. Save latitude and longitude.
6. Save `google_place_id` if available.
7. Save `google_maps_uri` if available.
8. Save merchant.
---

### 7.4.3 Option C: Enter Address Manually

User presses:

    [Enter address manually]

Bot asks:

    Enter merchant address:

User enters:

    123 Jalan Example, Kuala Lumpur

Backend actions:

1. Save address as `formatted_address`.
2. Geocode address to get latitude and longitude.
3. Save merchant only if geocoding succeeds.
---

## 7.5 Merchant Created

Backend inserts row into `merchants`.

Backend actions:

1. Save new `merchant_id` into current expense draft.
2. Return to main expense flow.
3. Set `draft.state = WAITING_FOR_AMOUNT`.

Bot replies:

    Merchant added: Restaurant ABC

    Enter total amount:

---

## 8. Edit Flow

If user presses:

    [Edit]

Bot replies:

    What would you like to edit?

    [Category]
    [Account]
    [Merchant]
    [Amount]
    [Description]
    [Date]
    [Cancel Expense]

Backend actions:

1. Set draft state based on selected edit option.
2. Update selected field.
3. Return to confirmation screen.
---

## 9. Cancel Flow

If user presses:

    [Cancel]

Bot replies:

    Cancel this expense?

    [Yes, Cancel]
    [No, Continue]

If user confirms cancel:

Backend actions:

1. Set `draft.state = CANCELLED`.
2. Do not insert any transaction.

Bot replies:

    Expense recording cancelled.

---

## 10. Updated Workflow States

### Main Expense States

    WAITING_FOR_CATEGORY
    WAITING_FOR_SUBCATEGORY
    WAITING_FOR_CATEGORY_DETAIL
    WAITING_FOR_ACCOUNT
    WAITING_FOR_LOCATION
    WAITING_FOR_MERCHANT
    WAITING_FOR_AMOUNT
    WAITING_FOR_DESCRIPTION
    WAITING_FOR_CONFIRMATION

### Internal Transfer States

    WAITING_FOR_SOURCE_ACCOUNT
    WAITING_FOR_DESTINATION_ACCOUNT
    WAITING_FOR_AMOUNT
    WAITING_FOR_DESCRIPTION
    WAITING_FOR_CONFIRMATION

### External Transfer States

    WAITING_FOR_SOURCE_ACCOUNT
    WAITING_FOR_RECIPIENT
    WAITING_FOR_AMOUNT
    WAITING_FOR_DESCRIPTION
    WAITING_FOR_CONFIRMATION

### New Category States

    WAITING_FOR_NEW_CATEGORY_NAME
    WAITING_FOR_NEW_SUBCATEGORY_NAME
    WAITING_FOR_NEW_CATEGORY_DETAIL_NAME

### New Merchant States

    WAITING_FOR_NEW_MERCHANT_NAME
    WAITING_FOR_NEW_MERCHANT_PRIMARY_TYPE
    WAITING_FOR_NEW_MERCHANT_ADDITIONAL_TYPES
    WAITING_FOR_NEW_MERCHANT_LOCATION_METHOD
    WAITING_FOR_NEW_MERCHANT_GOOGLE_LINK
    WAITING_FOR_NEW_MERCHANT_ADDRESS

### Final States

    COMPLETED
    CANCELLED

---

## 11. Account Visibility Rules

Account options must be filtered based on selected category.

### Normal Expense Categories

Visible account types:

    cash
    bank_account
    ewallet
    credit_card

Hidden account types:

    investment_account

### Transaction / Investment / Savings

Visible account types:

    cash
    bank_account
    ewallet
    savings_account
    investment_account

Rules:

1. Source account should usually be a spending account.
2. Destination account may be a savings or investment account.
3. Investment accounts only appear in this flow.

### Transaction to Others

Visible account types:

    cash
    bank_account
    ewallet

Rules:

1. Account selected is the source account.
2. Investment accounts should not appear.
3. Credit card visibility is TODO depending on whether transfers from credit card are allowed.

TODO:

- TODO: Confirm whether credit cards can be used for `Transaction to Others`.
- TODO: Confirm whether savings accounts can be used as source accounts.
- TODO: Confirm whether investment accounts can ever be used as source accounts.

---

## 12. Final Insert Rules

### Normal Expense

Insert table:

    expense_transactions

Balance effect:

    Deduct amount from selected account.

Required draft fields:

    user_id
    account_id
    merchant_id
    final_category_id
    amount
    transaction_datetime

---

### Transaction / Investment / Savings

Insert table:

    account_transfers

Balance effect:

    Deduct amount from source account.
    Add amount to destination account.

Required draft fields:

    user_id
    from_account_id
    to_account_id
    amount
    transaction_datetime

---

### Transaction to Others

Insert table:

    external_transfers

Balance effect:

    Deduct amount from selected source account.

Required draft fields:

    user_id
    from_account_id
    recipient_group
    recipient_name
    amount
    transaction_datetime

---
