# Expense Creation Workflow Specification
Version 3.0

Last Updated: 2026-05-07

## 1. Overview

This document defines the workflow for creating a new expense transaction through a Telegram bot.

Unlike the previous version, the primary workflow is now form-driven and button-driven. The Telegram bot guides the user step by step by asking for required information such as amount, account, merchant, category, date and notes.

AI is no longer required for the core expense recording workflow. Instead, AI may be introduced later as an optional shortcut for parsing natural language messages into a draft expense.

The system follows a controlled draft-confirm-insert approach:

- The bot collects expense information through questions and buttons
- The backend stores the collected information as a temporary draft
- The backend resolves accounts and merchants using controlled services
- The bot presents a final expense draft to the user
- The database is updated only after explicit user confirmation

The bot does not directly write incomplete or uncertain data into the database.

---

## 2. Design Principles

- Expense recording should be reliable, simple and predictable
- The core workflow should not depend on AI
- Telegram is used as the user interaction layer
- The backend is responsible for workflow state, validation and persistence
- The user is the final authority before any transaction is inserted
- All database writes must use fully resolved identifiers
- The system must ask for clarification when ambiguity exists
- No new merchant, account or entity should be created without user approval
- AI may assist with extraction, but must not bypass confirmation

---

## 3. High-Level Workflow

```text
User Starts Expense Entry
        |
        v
Telegram Bot Initiates Workflow
        |
        v
Create Expense Draft
        |
        v
Ask for Required Fields
        |
        v
Resolve Account and Merchant
        |
        v
Clarify Missing or Ambiguous Fields
        |
        v
Present Final Draft
        |
        v
User Confirmation
        |
        v
+---------------------------+
|        Decision           |
+---------------------------+
        | Confirm     | Edit / Cancel
        v             v
Insert into DB   Modify Draft / Cancel