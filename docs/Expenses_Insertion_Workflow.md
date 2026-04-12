# Expense Creation Workflow Specification
Version 1.0


Last Updated: 2026-04-12

## 1. Overview

This document defines the workflow for how the assistant processes a user message to create a new expense transaction.

The system follows a form-driven approach:
- The assistant interprets user input
- Constructs a structured draft
- Resolves entities via backend tools
- Presents the draft to the user
- Only inserts into the database upon user confirmation

The assistant does not directly write to the database.

---

## 2. Design Principles

- The assistant is responsible for interpretation and draft construction
- The backend is responsible for data resolution and validation
- The user is the final authority before any data is persisted
- All database writes must use fully resolved identifiers

---

## 3. High-Level Workflow

```
User Input (Natural Language)
    ↓
Draft Extraction (LLM)
    ↓
Entity Resolution (Backend Tools)
    ↓
Draft Transaction Construction
    ↓
User Confirmation (Yes / No / Edit)
    ↓
If Yes → Insert into Database
If No  → Modify or Cancel
```
---

## 4. Workflow Steps

### 4.1 User Input

The user provides a natural language message.

Example:
Spent RM150 at Petronas Puchong from TNG eWallet

---

### 4.2 Draft Extraction

The assistant extracts structured fields from the message.

Example output:
```
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

### 4.3 Entity Resolution

The backend provides tools to resolve extracted fields into database entities.

#### 4.3.1 Account Resolution
```
resolve_account_name(account_query: str, user_id: int)
```
Behavior:
- Matches against accounts.account_name
- Filters by user_id
- Applies normalization and fuzzy matching
- Returns best match and candidate list

---

#### 4.3.2 Merchant Resolution
```
resolve_merchant_name(
    merchant_name_query: str,
    location_query: str | None
)
```
Behavior:

1. Merchant Name Matching
   - Match against:
     - merchant_name
     - other_name
   - Apply fuzzy matching

2. Location Matching
   - Match against:
     - location_name
     - city, state, country (if available)

3. Scoring

final_score = weighted(merchant_name_score, location_score)

Typical weighting:
- Merchant name: 70%
- Location: 30%

4. Ranking
- Candidates are sorted by final_score

---

### Entity Resolution Outcomes
Ultimately, what we want to achieve is to allow the agent to resolve the merchant and account smartly, using only the clues given in the user input. The agent should be able to ask for clarification if needed or try to find the best suitable match based on the tools that is provided to it to explore the database.

### 4.4 Draft Transaction Construction

After resolution, a complete draft is constructed:
```
{
  "amount": 150.0,
  "account": {
    "account_id": 3,
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

### 4.5 User Confirmation

The assistant presents the draft:
```
Amount: RM150.00
Merchant: Petronas (Pusat Bandar Puchong)
Account: Touch 'n Go eWallet
Date: 2026-04-12

Confirm? (Yes / No / Edit)
```
---

### 4.6 Handling Ambiguity

If multiple candidates are plausible:
```
Multiple merchant matches found:

1. Petronas (Pusat Bandar Puchong)
2. Petronas (Bandar Puteri Puchong)
3. Petronas (USJ 1)

Please select the correct location.
```
---

### 4.7 Handling Not Found

If no match is found:

The merchant does not exist in current records.

Options:
1. Create a new merchant
2. Use a default placeholder

---

### 4.8 Final Insert

The database insert is executed only after user confirmation.
```
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
```
resolve_merchant_name(merchant_name_query, location_query)

list_user_accounts(user_id) # Secondary tool for account selection if the first doesn't perform well
search_merchants(merchant_name_query, location_query) # Secondary tool to provide a list of potential matches for user selection if resolution is ambiguous
```
---

## 6. Assistant Responsibilities

The assistant must:
- Extract structured data from user input
- Call appropriate resolver tools
- Handle ambiguity through user interaction
- Construct a complete draft transaction
- Request user confirmation before proceeding

---

## 7. Restrictions

The assistant must not:
- Execute SQL queries
- Access database tables directly
- Infer or fabricate identifiers
- Perform insertion operations
- Apply fuzzy matching logic independently

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
- Resolve entities
- Construct draft
- Confirm with user
- Execute insert

This ensures data integrity, transparency, and user control.