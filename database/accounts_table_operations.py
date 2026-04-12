from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import text

from database.utils import get_default_user_id, get_engine


class AccountCandidate(BaseModel):
    """One account row returned by list_all_accounts()."""

    account_id: int
    account_name: str
    account_type: str


class accountList(BaseModel):
    """Container model for account candidates."""

    candidates: list[AccountCandidate] = Field(default_factory=list)


def list_all_accounts() -> accountList:
    """
    Return all accounts for the default user.

    Notes:
    - Uses shared default user_id (currently expected to be 1 unless overridden by env).
    - Returns deterministic ordering by account_name, then account_id.
    """

    user_id = get_default_user_id()

    # Read all account rows for the scoped user only.
    query = text(
        """
        SELECT
            account_id,
            account_name,
            account_type
        FROM accounts
        WHERE user_id = :user_id
        ORDER BY LOWER(BTRIM(account_name)) ASC, account_id ASC
        """
    )

    # Use mapping rows so fields can be accessed by column name.
    with get_engine().begin() as connection:
        rows = connection.execute(query, {"user_id": user_id}).mappings().all()

    # Map raw DB rows into strongly-typed Pydantic models.
    candidates = [
        AccountCandidate(
            account_id=int(row["account_id"]),
            account_name=str(row["account_name"]),
            account_type=str(row["account_type"]),
        )
        for row in rows
    ]
    return accountList(candidates=candidates)
