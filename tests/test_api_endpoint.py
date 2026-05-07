from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import app
from app.schemas import DraftAccount, DraftMerchant, DraftTransaction, WorkflowResponse, WorkflowStatus


def test_workflow_endpoint_returns_expected_shape(monkeypatch):
    draft = DraftTransaction(
        amount=Decimal("15.50"),
        account=DraftAccount(account_id=1, account_name="Cash"),
        merchant=DraftMerchant(
            merchant_id=2,
            merchant_name="Petronas",
            location_name="Puchong",
            city="Puchong",
            state="Selangor",
            country="Malaysia",
        ),
        transaction_datetime=datetime.now(timezone.utc),
        notes=None,
    )

    def _stub(session_id: str | None, message: str) -> WorkflowResponse:  # noqa: ARG001
        return WorkflowResponse(
            session_id=session_id or "new-session",
            trace_id="trace-1",
            status=WorkflowStatus.NEEDS_CONFIRMATION,
            assistant_message="Confirm? (Yes / No / Edit)",
            draft=draft,
            clarification=None,
            pending_action="confirm_draft",
            transaction_id=None,
        )

    monkeypatch.setattr("app.api.run_expense_workflow_turn", _stub)

    client = TestClient(app)
    response = client.post("/api/v1/expenses/workflow", json={"message": "Spent RM15.50 at Petronas"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "new-session"
    assert payload["trace_id"] == "trace-1"
    assert payload["status"] == "needs_confirmation"
    assert payload["pending_action"] == "confirm_draft"
    assert payload["draft"]["amount"] == "15.50"
