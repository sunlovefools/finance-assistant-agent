from __future__ import annotations

"""Service bootstrap for LangGraph workflow runner and Postgres checkpointing."""

import atexit
from functools import lru_cache

from app.config import (
    get_checkpoint_conn_string,
    get_default_workflow_user_id,
    get_workflow_log_path,
)
from app.schemas import WorkflowResponse
from app.workflow_graph import ExpenseWorkflowRunner, WorkflowState
from app.workflow_logging import WorkflowEventLogger

_CHECKPOINTER_CONTEXT_MANAGER = None


def _build_checkpointer():
    """
    Build and initialize a Postgres-backed LangGraph checkpointer.

    The context manager is kept globally and closed on interpreter shutdown.
    """

    global _CHECKPOINTER_CONTEXT_MANAGER
    try:
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency for Postgres checkpointing. "
            "Install `langgraph-checkpoint-postgres`."
        ) from exc

    conn_string = get_checkpoint_conn_string()
    context_manager = PostgresSaver.from_conn_string(conn_string)
    checkpointer = context_manager.__enter__()
    _CHECKPOINTER_CONTEXT_MANAGER = context_manager

    if hasattr(checkpointer, "setup"):
        checkpointer.setup()

    def _close_checkpointer() -> None:
        global _CHECKPOINTER_CONTEXT_MANAGER
        if _CHECKPOINTER_CONTEXT_MANAGER is None:
            return
        _CHECKPOINTER_CONTEXT_MANAGER.__exit__(None, None, None)
        _CHECKPOINTER_CONTEXT_MANAGER = None

    atexit.register(_close_checkpointer)
    return checkpointer


@lru_cache(maxsize=1)
def get_workflow_runner() -> ExpenseWorkflowRunner:
    """Create and cache a single compiled workflow runner for process lifetime."""

    from langgraph.graph import StateGraph

    logger = WorkflowEventLogger(get_workflow_log_path())
    runner = ExpenseWorkflowRunner(
        compiled_graph=None,
        logger=logger,
        user_id=get_default_workflow_user_id(),
    )
    graph_builder = StateGraph(WorkflowState)
    runner.wire_graph(graph_builder)
    checkpointer = _build_checkpointer()
    compiled_graph = graph_builder.compile(checkpointer=checkpointer)
    runner._graph = compiled_graph  # noqa: SLF001 - internal wiring during bootstrap.
    return runner


def run_expense_workflow_turn(session_id: str | None, message: str) -> WorkflowResponse:
    """Convenience service method called by API layer."""

    return get_workflow_runner().run_expense_workflow_turn(session_id=session_id, message=message)
