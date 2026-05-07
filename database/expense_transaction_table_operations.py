from __future__ import annotations

"""Expense transaction write operations used by workflow and services."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, Date, DateTime, MetaData, Numeric, Table, Text, insert, text

from database.utils import get_engine

# Minimal table metadata used for SQLAlchemy insert statements.
_METADATA = MetaData()
_EXPENSE_TRANSACTIONS = Table(
    "expense_transactions",
    _METADATA,
    Column("transaction_id", BigInteger, primary_key=True),
    Column("user_id", BigInteger, nullable=False),
    Column("account_id", BigInteger, nullable=False),
    Column("merchant_id", BigInteger, nullable=False),
    Column("transaction_datetime", DateTime(timezone=True), nullable=False),
    Column("transaction_date", Date, nullable=False),
    Column("total_amount", Numeric(18, 2), nullable=False),
    Column("notes", Text, nullable=True),
)


def insert_expense_transaction(
    user_id: int,
    account_id: int,
    merchant_id: int,
    transaction_datetime: datetime,
    total_amount: Decimal,
    notes: str | None = None,
) -> int:
    """Insert one expense row and return the generated transaction id."""
    if total_amount <= 0:
        raise ValueError("total_amount must be greater than zero.")

    stmt = (
        insert(_EXPENSE_TRANSACTIONS)
        .values(
            user_id=user_id,
            account_id=account_id,
            merchant_id=merchant_id,
            transaction_datetime=transaction_datetime,
            transaction_date=transaction_datetime.date(),
            total_amount=total_amount,
            notes=notes,
        )
        .returning(_EXPENSE_TRANSACTIONS.c.transaction_id)
    )

    with get_engine().begin() as connection:
        new_transaction_id = connection.execute(stmt).scalar_one()

    return int(new_transaction_id)


def insert_expense_and_update_balance(
    user_id: int,
    account_id: int,
    merchant_id: int,
    transaction_datetime: datetime,
    total_amount: Decimal,
    notes: str | None = None,
) -> tuple[int, Decimal]:
    """
    Perform atomic expense write:
    1) insert expense transaction row
    2) decrement source account balance
    3) commit in a single DB transaction
    """

    if total_amount <= 0:
        raise ValueError("total_amount must be greater than zero.")

    insert_stmt = (
        insert(_EXPENSE_TRANSACTIONS)
        .values(
            user_id=user_id,
            account_id=account_id,
            merchant_id=merchant_id,
            transaction_datetime=transaction_datetime,
            transaction_date=transaction_datetime.date(),
            total_amount=total_amount,
            notes=notes,
        )
        .returning(_EXPENSE_TRANSACTIONS.c.transaction_id)
    )

    # Account balance is an application-managed snapshot in this schema.
    update_balance_stmt = text(
        """
        UPDATE accounts
        SET balance = balance - :total_amount
        WHERE account_id = :account_id
          AND user_id = :user_id
        RETURNING balance
        """
    )

    with get_engine().begin() as connection:
        new_transaction_id = int(connection.execute(insert_stmt).scalar_one())
        updated_balance = connection.execute(
            update_balance_stmt,
            {
                "total_amount": total_amount,
                "account_id": account_id,
                "user_id": user_id,
            },
        ).scalar_one_or_none()

        if updated_balance is None:
            raise ValueError(
                f"No account row updated for account_id={account_id}, user_id={user_id}."
            )

    return new_transaction_id, Decimal(str(updated_balance))
