from __future__ import annotations

"""Pydantic request/response/state schemas for the unified workflow API."""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class WorkflowStatus(str, Enum):
    """Top-level workflow state returned to API clients."""

    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_CONFIRMATION = "needs_confirmation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class PendingAction(str, Enum):
    """Action the client/user should provide in the next turn."""

    CLARIFY_ACCOUNT = "clarify_account"
    CLARIFY_MERCHANT = "clarify_merchant"
    CLARIFY_FIELDS = "clarify_fields"
    APPROVE_MERCHANT_CREATION = "approve_merchant_creation"
    CONFIRM_DRAFT = "confirm_draft"


class WorkflowRequest(BaseModel):
    """Unified endpoint request payload."""

    session_id: str | None = None
    message: str

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("message must be a non-empty string.")
        return value.strip()


class DraftExtraction(BaseModel):
    """Raw extracted fields before entity IDs are fully resolved."""

    amount: Decimal | None = None
    merchant_name_query: str | None = None
    location_query: str | None = None
    account_query: str | None = None
    transaction_datetime: datetime | None = None
    notes: str | None = None


class DraftAccount(BaseModel):
    """Resolved account details included in draft."""

    account_id: int
    account_name: str


class DraftMerchant(BaseModel):
    """Resolved merchant details included in draft."""

    merchant_id: int
    merchant_name: str
    location_name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None


class DraftTransaction(BaseModel):
    """Final draft shown to user before insertion."""

    amount: Decimal
    account: DraftAccount
    merchant: DraftMerchant
    transaction_datetime: datetime
    notes: str | None = None


class ClarificationOption(BaseModel):
    """One numbered option presented during clarification."""

    index: int
    label: str


class ClarificationPayload(BaseModel):
    """Clarification prompt payload for ambiguous/missing data."""

    type: str
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    """Unified endpoint response payload."""

    session_id: str
    trace_id: str
    status: WorkflowStatus
    assistant_message: str
    draft: DraftTransaction | None = None
    clarification: ClarificationPayload | None = None
    pending_action: PendingAction | None = None
    transaction_id: int | None = None
