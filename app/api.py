from __future__ import annotations

"""FastAPI entrypoints for the unified expense workflow API."""

from fastapi import FastAPI, HTTPException

from app.schemas import WorkflowRequest, WorkflowResponse
from app.service import run_expense_workflow_turn

app = FastAPI(title="Financial Assistant Expense Workflow API", version="0.1.0")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Simple liveness endpoint for local and container health checks."""

    return {"status": "ok"}


@app.post("/api/v1/expenses/workflow", response_model=WorkflowResponse)
def expenses_workflow(payload: WorkflowRequest) -> WorkflowResponse:
    """
    Single unified endpoint for all expense-workflow turns.

    The same endpoint handles:
    - initial message parsing,
    - clarification replies,
    - confirmation/cancellation responses.
    """

    try:
        return run_expense_workflow_turn(
            session_id=payload.session_id,
            message=payload.message,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc
