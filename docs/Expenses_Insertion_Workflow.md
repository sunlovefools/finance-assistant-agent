# Expense Creation Workflow Specification
Version 2.0

Last Updated: 2026-04-12

## 1. Overview

This document defines the workflow for how the assistant processes a user message to create a new expense transaction.

The system follows a form-driven approach:
- The assistant interprets user input
- Constructs a structured draft
- Uses backend tools to explore and resolve entities
- Presents the draft to the user
- Only inserts into the database upon user confirmation

The assistant does not directly write to the database.

---

## 2. Design Principles

- The assistant is responsible for interpretation and draft construction
- The backend is responsible for data access and persistence
- The user is the final authority before any data is persisted
- All database writes must use fully resolved identifiers
- The system prioritizes correctness over automation when ambiguity exists

---

## 3. High-Level Workflow

```
User Input (Natural Language)
        |
        v
Draft Extraction (LLM)
        |
        v
Account Context Injection (Backend)
        |
        v
Merchant Exploration (Tools)
        |
        v
Draft Transaction Construction
        |
        v
User Clarification (if needed)
        |
        v
User Confirmation (Yes / No / Edit)
        |
        v
+---------------------------+
|        Decision           |
+---------------------------+
        | Yes        | No
        v            v
Insert into DB   Modify / Cancel
```

---

## 4. Workflow Steps

### 4.1 User Input

The user provides a natural language message.

Example:
```
Spent RM150 at Petronas Puchong from TNG eWallet
```

---

### 4.2 Draft Extraction

The assistant extracts structured fields from the message.

Example output:

```json
{
  "amount": 150.0,
  "merchant_name_query": "Petronas",
  "location_query": "Puchong",
  "account_query": "TNG eWallet",
  "transaction_datetime": null,
  "notes": null
}
```

Notes:
- No database IDs are resolved at this stage
- The assistant does not access the database directly
- Missing fields may be requested from the user

---

### 4.3 Account Context Injection

The backend automatically fetches all accounts associated with the user and injects them into the assistant context.

Example:

```json
[
  { "account_id": 1, "account_name": "Touch 'n Go eWallet" },
  { "account_id": 2, "account_name": "MAE" },
  { "account_id": 3, "account_name": "Cash" }
]
```

Behavior:
- The assistant selects the most appropriate account from this list
- If multiple accounts are plausible, the assistant must ask the user
- If no suitable account exists, the assistant proposes creating a new one

---

### 4.4 Merchant Exploration and Resolution

Unlike accounts, merchants are not preloaded.

The assistant must actively explore available merchants using backend tools.  
For the current workflow, merchant exploration is divided into two modes:

1. exploration without location
2. exploration with location

This allows the assistant to first identify likely merchant brands, and then refine using location when available.

#### 4.4.1 Merchant Exploration Without Location

```python
explore_merchants_without_location(
    merchant_name_query: str,
    limit: int = 50
)
```

Behavior:
- Retrieves candidate merchant-location rows using the merchant name only
- Useful when the user provides only a merchant brand or partial merchant name
- Allows the assistant to inspect what merchant brands or branches already exist
- Returns a ranked list of merchant and location pairs

Purpose:
- Helps the assistant identify whether the merchant brand already exists in the database
- Helps the assistant avoid proposing a new merchant too early
- Supports clarification when the user has not specified a location

Example use cases:
- User says: `Spent RM20 at Petronas`
- User says: `Paid at McD`
- User provides a typo or partial merchant name

#### 4.4.2 Merchant Exploration With Location

```python
explore_merchants_with_location(
    merchant_name_query: str,
    location_query: str,
    limit: int = 50
)
```

Behavior:
- Retrieves candidate merchant-location rows using both merchant name and location
- Applies fuzzy matching on both merchant name and location
- Returns a ranked list of merchant and location pairs

Purpose:
- Helps the assistant determine whether a specific merchant branch or location already exists
- Supports more accurate draft construction when the user has already provided a location clue
- Reduces ambiguity when there are many branches under the same merchant brand

Example use cases:
- User says: `Spent RM150 at Petronas Puchong`
- User says: `Paid at FamilyMart Sunway`
- User says: `Bought groceries at Tesco Shah Alam`

#### 4.4.3 Resolution Strategy

The assistant should follow this strategy:

1. If the user provides both merchant name and location:
   - use `explore_merchants_with_location(...)`
   - if a suitable candidate is found, use it in the draft
   - if results are ambiguous, ask the user for clarification

2. If the user provides only a merchant name:
   - use `explore_merchants_without_location(...)`
   - inspect whether the merchant brand already exists
   - if multiple branches exist, ask the user which location should be used
   - do not propose creating a new merchant immediately

3. If no suitable merchant-location row is found:
   - the assistant may suggest creating a new merchant
   - this must only happen after reasonable exploration has been performed
   - user approval is required before any new merchant is created

#### 4.4.4 Output Shape

Both merchant exploration tools should return a ranked list of merchant-location pairs.

Example output:

```json
[
  {
    "merchant_id": 12,
    "merchant_name": "Petronas",
    "location_name": "Pusat Bandar Puchong",
    "city": "Puchong",
    "state": "Selangor",
    "country": "Malaysia",
    "score": 0.95
  },
  {
    "merchant_id": 18,
    "merchant_name": "Petronas",
    "location_name": "Bandar Puteri Puchong",
    "city": "Puchong",
    "state": "Selangor",
    "country": "Malaysia",
    "score": 0.91
  }
]
```

The assistant is responsible for interpreting these candidates and deciding whether:
- one candidate is suitable for the draft
- user clarification is needed
- a new merchant should be proposed

### 4.5 Entity Resolution Strategy

The assistant follows this strategy:

1. Attempt to match merchant using provided queries  
2. If one clear candidate exists → use it  
3. If multiple candidates exist → ask user  
4. If no suitable candidate exists → propose creating a new merchant  

The assistant must not assume when uncertainty exists.

---

### 4.6 Draft Transaction Construction

After resolving entities, a complete draft is constructed:

```json
{
  "amount": 150.0,
  "account": {
    "account_id": 1,
    "account_name": "Touch 'n Go eWallet"
  },
  "merchant": {
    "merchant_id": 12,
    "merchant_name": "Petronas",
    "location_name": "Pusat Bandar Puchong"
  },
  "transaction_datetime": "2026-04-12T20:30:00",
  "notes": null
}
```

---

### 4.7 User Clarification

If ambiguity exists:

```
Multiple merchant matches found:

1. Petronas (Pusat Bandar Puchong)
2. Petronas (Bandar Puteri Puchong)
3. Petronas (USJ 1)

Please select the correct option.
```

If account ambiguity exists:

```
Multiple accounts match your description:

1. MAE
2. Maybank Savings

Which account should be used?
```

---

### 4.8 Handling Not Found (Creation Flow)

If no suitable merchant exists:

```
No matching merchant found.

I can create a new merchant:
Petronas / Puchong

Would you like to proceed?
```

Rules:
- The assistant must always request user approval before creating new entities
- No automatic creation is allowed

---

### 4.9 User Confirmation

The assistant presents the final draft:

```
Amount: RM150.00
Merchant: Petronas (Pusat Bandar Puchong)
Account: Touch 'n Go eWallet
Date: 2026-04-12

Confirm? (Yes / No / Edit)
```

---

### 4.10 Final Insert

The database insert is executed only after user confirmation.

```python
insert_expense_transaction(
    user_id: int,
    account_id: int,
    merchant_id: int,
    transaction_datetime: datetime,
    total_amount: Decimal,
    notes: Optional[str]
)
```

Constraints:
- All identifiers must be resolved before insertion
- No fuzzy matching is performed at this stage
- The operation must be atomic:
  1. Insert transaction
  2. Update account balance
  3. Commit

---

## 5. Tools Exposed to the Assistant

### Core Tools

```python
explore_merchants_without_location(merchant_name_query, limit=50)
explore_merchants_with_location(merchant_name_query, location_query, limit=50)
```

### Backend-Injected Context

```python
list_all_accounts(user_id)  # Injected automatically, not called by LLM
```

---

## 6. Assistant Responsibilities

The assistant must:
- Extract structured data from user input
- Select accounts from provided context
- Use merchant tools to explore and resolve merchants
- Handle ambiguity through user interaction
- Propose new entity creation when necessary
- Construct a complete draft transaction
- Request user confirmation before proceeding

---

## 7. Restrictions

The assistant must not:
- Execute SQL queries
- Access database tables directly
- Infer or fabricate identifiers
- Perform insertion operations
- Create new entities without user approval

---

## 8. Future Extensions

Potential improvements:
- Automatic category classification
- Merchant alias learning
- Location inference
- Frequent merchant prioritization
- User behavior adaptation

---

## 9. Summary

The system follows a structured, controlled workflow:

- Interpret input  
- Inject account context  
- Explore merchants dynamically  
- Construct draft  
- Clarify with user when needed  
- Confirm with user  
- Execute insert  

This ensures data integrity, transparency, and user control.
