from __future__ import annotations

from app.workflow_graph import ExpenseWorkflowRunner
from app.workflow_logging import WorkflowEventLogger


class _DummyGraph:
    def invoke(self, state, config=None):  # noqa: ARG002
        return state


def _runner(tmp_path) -> ExpenseWorkflowRunner:
    logger = WorkflowEventLogger(tmp_path / "events.jsonl")
    return ExpenseWorkflowRunner(compiled_graph=_DummyGraph(), logger=logger, user_id=1)


def test_resolve_account_selects_clear_match(tmp_path):
    runner = _runner(tmp_path)
    state = {
        "status": "needs_clarification",
        "pending_action": None,
        "account_candidates": [
            {"account_id": 1, "account_name": "Touch 'n Go eWallet", "account_type": "ewallet"},
            {"account_id": 2, "account_name": "Cash", "account_type": "cash"},
        ],
        "extracted_draft": {"account_query": "cash"},
    }
    updated = runner.node_resolve_account(state)
    assert updated["selected_account"]["account_id"] == 2
    assert updated.get("pending_action") is None


def test_resolve_account_requests_clarification_when_ambiguous(tmp_path):
    runner = _runner(tmp_path)
    state = {
        "status": "needs_clarification",
        "pending_action": None,
        "account_candidates": [
            {"account_id": 1, "account_name": "Maybank", "account_type": "bank"},
            {"account_id": 2, "account_name": "MAE", "account_type": "ewallet"},
        ],
        "extracted_draft": {"account_query": None},
    }
    updated = runner.node_resolve_account(state)
    assert updated["pending_action"] == "clarify_account"
    assert updated["clarification"]["type"] == "account_ambiguity"


def test_resolve_merchant_proposes_creation_when_not_found(tmp_path):
    runner = _runner(tmp_path)
    state = {
        "status": "needs_clarification",
        "pending_action": None,
        "merchant_candidates": [],
        "extracted_draft": {"merchant_name_query": "Petronas", "location_query": "Puchong"},
    }
    updated = runner.node_resolve_merchant(state)
    assert updated["pending_action"] == "approve_merchant_creation"
    assert updated["create_merchant_proposal"]["merchant_name"] == "Petronas"


def test_extract_draft_cancellation_from_confirmation(tmp_path):
    runner = _runner(tmp_path)
    state = {
        "status": "needs_confirmation",
        "pending_action": "confirm_draft",
        "user_message": "No",
        "extracted_draft": {"amount": "10.00"},
    }
    updated = runner.node_extract_draft(state)
    assert updated["status"] == "cancelled"
    assert updated["pending_action"] is None

