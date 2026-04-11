from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Column, Date, DateTime, MetaData, Numeric, Table, Text, insert

from database.utils import get_engine


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
    """
    Insert one row into expense_transactions and return the new transaction_id.
    """
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
