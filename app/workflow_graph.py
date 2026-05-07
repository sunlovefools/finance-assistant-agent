from __future__ import annotations

"""LangGraph workflow orchestration for unified expense insertion conversations."""

import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, TypedDict

from rapidfuzz import fuzz

from app.llm import classify_confirmation_response, get_draft_extractor, parse_relative_datetime
from app.schemas import (
    ClarificationOption,
    DraftAccount,
    DraftExtraction,
    DraftMerchant,
    DraftTransaction,
    PendingAction,
    WorkflowResponse,
    WorkflowStatus,
)
from app.workflow_logging import WorkflowEventLogger
from database.accounts_table_operations import list_all_accounts
from database.expense_transaction_table_operations import insert_expense_and_update_balance
from database.merchants_table_operations import (
    create_merchant,
    explore_merchants_with_location,
    explore_merchants_without_location,
)


class WorkflowState(TypedDict, total=False):
    """
    Mutable graph state shared across all nodes.

    A subset of these fields is persisted by the Postgres checkpointer
    under `thread_id=session_id` so subsequent turns can resume.
    """

    session_id: str
    trace_id: str
    run_id: str
    user_message: str
    status: str
    assistant_message: str
    pending_action: str | None
    clarification: dict[str, Any] | None
    extracted_draft: dict[str, Any] | None
    account_candidates: list[dict[str, Any]]
    merchant_candidates: list[dict[str, Any]]
    selected_account: dict[str, Any] | None
    selected_merchant: dict[str, Any] | None
    create_merchant_proposal: dict[str, Any] | None
    create_merchant_approved: bool
    confirmation_decision: str | None
    should_insert: bool
    draft: dict[str, Any] | None
    transaction_id: int | None
    error: str | None


def _normalize(value: str | None) -> str:
    """Normalize fuzzy-match text by lowercasing and collapsing whitespace."""

    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _parse_choice(message: str, size: int) -> int | None:
    """Parse 1-based numeric user selections from clarification prompts."""

    stripped = message.strip()
    if stripped.isdigit():
        idx = int(stripped)
        if 1 <= idx <= size:
            return idx - 1
    return None


def _clear_winner(scores: list[float], winner_threshold: float, gap_threshold: float) -> bool:
    """Return True when top candidate is strong and clearly above runner-up."""

    if not scores:
        return False
    if scores[0] < winner_threshold:
        return False
    if len(scores) == 1:
        return True
    return (scores[0] - scores[1]) >= gap_threshold


def _json_summary_error(exc: Exception) -> dict[str, str]:
    """Compact error payload used by structured workflow logs."""

    return {"error": f"{type(exc).__name__}: {exc}"}


class ExpenseWorkflowRunner:
    """Runtime wrapper around compiled LangGraph graph plus logging/extractor services."""

    def __init__(self, compiled_graph, logger: WorkflowEventLogger, user_id: int):
        self._graph = compiled_graph
        self._logger = logger
        self._user_id = user_id
        self._extractor = get_draft_extractor()

    def run_expense_workflow_turn(self, session_id: str | None, message: str) -> WorkflowResponse:
        """
        Run one API turn for the given session.

        The checkpointer uses `session_id` as thread id, so this method can
        continue prior clarification/confirmation flows in a single endpoint.
        """

        final_session_id = session_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        state: WorkflowState = {
            "session_id": final_session_id,
            "trace_id": trace_id,
            "run_id": run_id,
            "user_message": message.strip(),
        }
        config = {"configurable": {"thread_id": final_session_id}}

        self._logger.log_event(
            level="INFO",
            trace_id=trace_id,
            session_id=final_session_id,
            run_id=run_id,
            node="workflow",
            event_type="run_start",
            payload_summary={"message": message.strip()},
        )

        try:
            result = self._graph.invoke(state, config=config)
        except Exception as exc:
            self._logger.log_event(
                level="ERROR",
                trace_id=trace_id,
                session_id=final_session_id,
                run_id=run_id,
                node="workflow",
                event_type="run_error",
                payload_summary=_json_summary_error(exc),
            )
            return WorkflowResponse(
                session_id=final_session_id,
                trace_id=trace_id,
                status=WorkflowStatus.ERROR,
                assistant_message="I ran into an internal error while processing your request.",
                pending_action=None,
            )

        self._logger.log_event(
            level="INFO",
            trace_id=trace_id,
            session_id=final_session_id,
            run_id=run_id,
            node="workflow",
            event_type="run_end",
            payload_summary={
                "status": result.get("status"),
                "pending_action": result.get("pending_action"),
                "transaction_id": result.get("transaction_id"),
            },
        )

        clarification_payload = None
        if result.get("clarification"):
            clarification_payload = {
                "type": result["clarification"]["type"],
                "question": result["clarification"]["question"],
                "options": [
                    ClarificationOption(index=opt["index"], label=opt["label"])
                    for opt in result["clarification"].get("options", [])
                ],
            }

        try:
            response_status = WorkflowStatus(result.get("status", WorkflowStatus.ERROR.value))
        except ValueError:
            response_status = WorkflowStatus.ERROR

        pending_action = None
        raw_pending = result.get("pending_action")
        if raw_pending:
            try:
                pending_action = PendingAction(raw_pending)
            except ValueError:
                pending_action = None

        return WorkflowResponse(
            session_id=final_session_id,
            trace_id=trace_id,
            status=response_status,
            assistant_message=result.get("assistant_message", ""),
            draft=DraftTransaction.model_validate(result["draft"]) if result.get("draft") else None,
            clarification=clarification_payload,
            pending_action=pending_action,
            transaction_id=result.get("transaction_id"),
        )

    def _with_node_logging(self, node_name: str, fn: Callable[[WorkflowState], WorkflowState]):
        """Decorator helper that emits node_enter/node_exit/node_error log events."""

        def _wrapped(state: WorkflowState) -> WorkflowState:
            trace_id = state.get("trace_id", "")
            session_id = state.get("session_id", "")
            run_id = state.get("run_id", "")
            self._logger.log_event(
                level="INFO",
                trace_id=trace_id,
                session_id=session_id,
                run_id=run_id,
                node=node_name,
                event_type="node_enter",
                payload_summary={"pending_action": state.get("pending_action")},
            )
            start = time.perf_counter()
            try:
                updated = fn(state)
            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                self._logger.log_event(
                    level="ERROR",
                    trace_id=trace_id,
                    session_id=session_id,
                    run_id=run_id,
                    node=node_name,
                    event_type="node_error",
                    latency_ms=latency_ms,
                    payload_summary=_json_summary_error(exc),
                )
                raise

            latency_ms = (time.perf_counter() - start) * 1000
            self._logger.log_event(
                level="INFO",
                trace_id=trace_id,
                session_id=session_id,
                run_id=run_id,
                node=node_name,
                event_type="node_exit",
                latency_ms=latency_ms,
                payload_summary={
                    "status": updated.get("status"),
                    "pending_action": updated.get("pending_action"),
                    "transaction_id": updated.get("transaction_id"),
                },
            )
            return updated

        return _wrapped

    def node_ingest_message(self, state: WorkflowState) -> WorkflowState:
        """Initialize per-turn transient fields before routing logic starts."""

        state["assistant_message"] = ""
        state["clarification"] = None
        state["confirmation_decision"] = None
        state["should_insert"] = False
        if not state.get("status"):
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
        return state

    def node_extract_draft(self, state: WorkflowState) -> WorkflowState:
        """
        Parse initial user message into structured draft fields, or
        interpret user reply when a pending action already exists.
        """

        pending_action = state.get("pending_action")
        message = state.get("user_message", "").strip()
        if not message:
            state["status"] = WorkflowStatus.ERROR.value
            state["assistant_message"] = "Message cannot be empty."
            return state

        if pending_action == PendingAction.CLARIFY_ACCOUNT.value:
            return state
        if pending_action == PendingAction.CLARIFY_MERCHANT.value:
            return state
        if pending_action == PendingAction.APPROVE_MERCHANT_CREATION.value:
            return state
        if pending_action == PendingAction.CLARIFY_FIELDS.value:
            self._apply_clarify_fields_input(state, message)
            return state

        if pending_action == PendingAction.CONFIRM_DRAFT.value:
            decision = classify_confirmation_response(message)
            state["confirmation_decision"] = decision
            if decision == "no":
                state["status"] = WorkflowStatus.CANCELLED.value
                state["pending_action"] = None
                state["assistant_message"] = "Expense insertion cancelled."
                return state
            if decision == "edit":
                self._apply_confirmation_edit(state, message)
                return state
            return state

        extracted = self._extractor.extract(message)
        if extracted.transaction_datetime is None:
            extracted.transaction_datetime = parse_relative_datetime(message)
        state["extracted_draft"] = extracted.model_dump(mode="json")
        state["selected_account"] = None
        state["selected_merchant"] = None
        return state

    def _apply_confirmation_edit(self, state: WorkflowState, message: str) -> None:
        """Apply lightweight edit commands to existing extracted draft."""

        existing = DraftExtraction.model_validate(state.get("extracted_draft") or {})
        normalized = message.lower()
        amount_match = None
        for token in message.replace(",", " ").split():
            cleaned = token.lower().replace("rm", "").replace("$", "").strip()
            try:
                amount_match = Decimal(cleaned)
                break
            except Exception:
                continue
        if amount_match is not None and any(keyword in normalized for keyword in ("amount", "rm", "$")):
            existing.amount = amount_match

        if "from " in normalized:
            existing.account_query = message.lower().split("from ", 1)[1].strip()
            state["selected_account"] = None

        if " at " in normalized:
            merchant_chunk = message.lower().split(" at ", 1)[1].strip()
            if " from " in merchant_chunk:
                merchant_chunk = merchant_chunk.split(" from ", 1)[0].strip()
            merchant_parts = merchant_chunk.split()
            if merchant_parts:
                existing.merchant_name_query = merchant_parts[0]
                existing.location_query = " ".join(merchant_parts[1:]) if len(merchant_parts) > 1 else None
                state["selected_merchant"] = None

        if "note " in normalized:
            existing.notes = message.split("note", 1)[1].strip()

        state["extracted_draft"] = existing.model_dump(mode="json")
        state["pending_action"] = None
        state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value

    def _apply_clarify_fields_input(self, state: WorkflowState, message: str) -> None:
        """Fill missing fields based on the active clarification prompt type."""

        clarification = state.get("clarification") or {}
        clarification_type = clarification.get("type")
        extracted = DraftExtraction.model_validate(state.get("extracted_draft") or {})
        if clarification_type == "missing_amount":
            try:
                extracted.amount = Decimal(message.strip())
                state["pending_action"] = None
            except Exception:
                pass
        elif clarification_type == "missing_merchant":
            parts = message.strip().split()
            if parts:
                extracted.merchant_name_query = parts[0]
                extracted.location_query = " ".join(parts[1:]) if len(parts) > 1 else None
                state["pending_action"] = None
        elif clarification_type == "missing_account":
            extracted.account_query = message.strip()
            state["pending_action"] = None

        state["extracted_draft"] = extracted.model_dump(mode="json")

    def node_inject_accounts(self, state: WorkflowState) -> WorkflowState:
        """Load account candidates from backend and place into graph state."""

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return state
        accounts = list_all_accounts().candidates
        state["account_candidates"] = [account.model_dump() for account in accounts]
        return state

    def node_resolve_account(self, state: WorkflowState) -> WorkflowState:
        """
        Resolve account from extracted query or clarification response.

        If ambiguity remains, this node sets `pending_action=clarify_account`.
        """

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return state

        accounts = state.get("account_candidates", [])
        if not accounts:
            state["status"] = WorkflowStatus.ERROR.value
            state["assistant_message"] = "No accounts available for this user."
            return state

        if state.get("pending_action") == PendingAction.CLARIFY_ACCOUNT.value:
            selected_idx = _parse_choice(state.get("user_message", ""), len(accounts))
            if selected_idx is None:
                state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
                return state
            selected = accounts[selected_idx]
            state["selected_account"] = {
                "account_id": int(selected["account_id"]),
                "account_name": str(selected["account_name"]),
            }
            state["pending_action"] = None
            state["clarification"] = None
            return state

        if state.get("selected_account") is not None:
            return state

        extracted = DraftExtraction.model_validate(state.get("extracted_draft") or {})
        account_query = _normalize(extracted.account_query)
        if not account_query:
            if len(accounts) == 1:
                only = accounts[0]
                state["selected_account"] = {
                    "account_id": int(only["account_id"]),
                    "account_name": str(only["account_name"]),
                }
                return state
            state["pending_action"] = PendingAction.CLARIFY_ACCOUNT.value
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
            state["clarification"] = {
                "type": "account_ambiguity",
                "question": "Multiple accounts are available. Please choose an account.",
                "options": [
                    {"index": idx + 1, "label": account["account_name"]}
                    for idx, account in enumerate(accounts[:5])
                ],
            }
            state["account_candidates"] = accounts[:5]
            return state

        scored_accounts: list[tuple[float, dict[str, Any]]] = []
        for account in accounts:
            candidate_text = _normalize(
                f"{account.get('account_name', '')} {account.get('account_type', '')}"
            )
            score = float(fuzz.WRatio(account_query, candidate_text))
            scored_accounts.append((score, account))
        scored_accounts.sort(key=lambda item: item[0], reverse=True)

        if _clear_winner(
            [score for score, _ in scored_accounts],
            winner_threshold=88.0,
            gap_threshold=8.0,
        ):
            top = scored_accounts[0][1]
            state["selected_account"] = {
                "account_id": int(top["account_id"]),
                "account_name": str(top["account_name"]),
            }
            return state

        state["pending_action"] = PendingAction.CLARIFY_ACCOUNT.value
        state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
        state["clarification"] = {
            "type": "account_ambiguity",
            "question": "Multiple account matches found. Please choose one.",
            "options": [
                {"index": idx + 1, "label": candidate["account_name"]}
                for idx, (_, candidate) in enumerate(scored_accounts[:5])
            ],
        }
        state["account_candidates"] = [candidate for _, candidate in scored_accounts[:5]]
        return state

    def node_explore_merchants(self, state: WorkflowState) -> WorkflowState:
        """
        Fetch merchant candidates using mode matching the available inputs:
        - with location
        - without location
        """

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return state
        if state.get("pending_action") in {
            PendingAction.CLARIFY_ACCOUNT.value,
            PendingAction.CLARIFY_MERCHANT.value,
            PendingAction.APPROVE_MERCHANT_CREATION.value,
        }:
            return state
        if state.get("selected_merchant") is not None:
            return state

        extracted = DraftExtraction.model_validate(state.get("extracted_draft") or {})
        merchant_name = _normalize(extracted.merchant_name_query)
        if not merchant_name:
            state["pending_action"] = PendingAction.CLARIFY_FIELDS.value
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
            state["clarification"] = {
                "type": "missing_merchant",
                "question": "Please provide the merchant name (and location if available).",
                "options": [],
            }
            return state

        location_query = _normalize(extracted.location_query)
        if location_query:
            candidates = explore_merchants_with_location(
                merchant_name_query=merchant_name,
                location_query=location_query,
                limit=10,
            ).candidates
        else:
            candidates = explore_merchants_without_location(
                merchant_name_query=merchant_name,
                limit=10,
            ).candidates
        state["merchant_candidates"] = [candidate.model_dump() for candidate in candidates]
        return state

    def node_resolve_merchant(self, state: WorkflowState) -> WorkflowState:
        """
        Resolve merchant candidate, or request clarification/creation approval.
        """

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return state
        pending_action = state.get("pending_action")

        if pending_action == PendingAction.CLARIFY_MERCHANT.value:
            candidates = state.get("merchant_candidates", [])
            selected_idx = _parse_choice(state.get("user_message", ""), len(candidates))
            if selected_idx is None:
                state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
                return state
            selected = candidates[selected_idx]
            state["selected_merchant"] = {
                "merchant_id": int(selected["merchant_id"]),
                "merchant_name": str(selected["merchant_name"]),
                "location_name": str(selected["location_name"]),
                "city": selected.get("city"),
                "state": selected.get("state"),
                "country": selected.get("country"),
            }
            state["pending_action"] = None
            state["clarification"] = None
            return state

        if pending_action == PendingAction.APPROVE_MERCHANT_CREATION.value:
            decision = classify_confirmation_response(state.get("user_message", ""))
            if decision == "yes":
                state["create_merchant_approved"] = True
                state["pending_action"] = None
                return state
            if decision == "no":
                state["status"] = WorkflowStatus.CANCELLED.value
                state["assistant_message"] = "Merchant creation cancelled. Expense was not inserted."
                state["pending_action"] = None
                return state
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
            return state

        if state.get("selected_merchant") is not None:
            return state

        candidates = state.get("merchant_candidates", [])
        if not candidates:
            extracted = DraftExtraction.model_validate(state.get("extracted_draft") or {})
            merchant_name = extracted.merchant_name_query or "Unknown merchant"
            location_name = extracted.location_query or "Unknown location"
            state["create_merchant_proposal"] = {
                "merchant_name": merchant_name.strip(),
                "location_name": location_name.strip(),
            }
            state["pending_action"] = PendingAction.APPROVE_MERCHANT_CREATION.value
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
            return state

        scored = sorted(candidates, key=lambda item: float(item.get("score", 0.0)), reverse=True)
        top_scores = [float(item.get("score", 0.0)) for item in scored[:2]]
        if _clear_winner(top_scores, winner_threshold=0.90, gap_threshold=0.05):
            winner = scored[0]
            state["selected_merchant"] = {
                "merchant_id": int(winner["merchant_id"]),
                "merchant_name": str(winner["merchant_name"]),
                "location_name": str(winner["location_name"]),
                "city": winner.get("city"),
                "state": winner.get("state"),
                "country": winner.get("country"),
            }
            return state

        state["pending_action"] = PendingAction.CLARIFY_MERCHANT.value
        state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
        state["clarification"] = {
            "type": "merchant_ambiguity",
            "question": "Multiple merchant matches found. Please choose the correct option.",
            "options": [
                {
                    "index": idx + 1,
                    "label": f"{candidate['merchant_name']} ({candidate['location_name']})",
                }
                for idx, candidate in enumerate(scored[:5])
            ],
        }
        state["merchant_candidates"] = scored[:5]
        return state

    def node_create_merchant_if_approved(self, state: WorkflowState) -> WorkflowState:
        """Create merchant only after explicit user approval in prior step."""

        if not state.get("create_merchant_approved"):
            return state
        if state.get("selected_merchant") is not None:
            return state

        proposal = state.get("create_merchant_proposal") or {}
        created = create_merchant(
            merchant_name=proposal.get("merchant_name", ""),
            location_name=proposal.get("location_name", ""),
        )
        state["selected_merchant"] = DraftMerchant(
            merchant_id=created.merchant_id,
            merchant_name=created.merchant_name,
            location_name=created.location_name,
            city=created.city,
            state=created.state,
            country=created.country,
        ).model_dump()
        state["create_merchant_approved"] = False
        return state

    def node_build_draft(self, state: WorkflowState) -> WorkflowState:
        """
        Construct final draft once amount/account/merchant are resolved.
        """

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return state
        if state.get("pending_action") in {
            PendingAction.CLARIFY_ACCOUNT.value,
            PendingAction.CLARIFY_MERCHANT.value,
            PendingAction.APPROVE_MERCHANT_CREATION.value,
            PendingAction.CLARIFY_FIELDS.value,
        }:
            return state

        extracted = DraftExtraction.model_validate(state.get("extracted_draft") or {})
        if extracted.amount is None:
            state["pending_action"] = PendingAction.CLARIFY_FIELDS.value
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
            state["clarification"] = {
                "type": "missing_amount",
                "question": "Please provide the expense amount.",
                "options": [],
            }
            return state
        if extracted.account_query is None and state.get("selected_account") is None:
            state["pending_action"] = PendingAction.CLARIFY_FIELDS.value
            state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
            state["clarification"] = {
                "type": "missing_account",
                "question": "Please provide which account was used for this expense.",
                "options": [],
            }
            return state
        if state.get("selected_account") is None or state.get("selected_merchant") is None:
            return state

        transaction_datetime = extracted.transaction_datetime or datetime.now(timezone.utc)
        draft = DraftTransaction(
            amount=extracted.amount,
            account=DraftAccount.model_validate(state["selected_account"]),
            merchant=DraftMerchant.model_validate(state["selected_merchant"]),
            transaction_datetime=transaction_datetime,
            notes=extracted.notes,
        )
        state["draft"] = draft.model_dump(mode="json")

        if state.get("confirmation_decision") == "yes":
            state["should_insert"] = True
            state["pending_action"] = None
            return state

        state["pending_action"] = PendingAction.CONFIRM_DRAFT.value
        state["status"] = WorkflowStatus.NEEDS_CONFIRMATION.value
        return state

    def node_ask_clarification(self, state: WorkflowState) -> WorkflowState:
        """Render clarification question as assistant-facing message text."""

        clarification = state.get("clarification") or {}
        question = clarification.get("question", "Please provide more details.")
        options = clarification.get("options", [])
        if options:
            lines = [question, ""]
            for opt in options:
                lines.append(f"{opt['index']}. {opt['label']}")
            state["assistant_message"] = "\n".join(lines)
        else:
            state["assistant_message"] = question
        state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
        return state

    def node_ask_create_merchant(self, state: WorkflowState) -> WorkflowState:
        """Render merchant-creation approval question."""

        proposal = state.get("create_merchant_proposal") or {}
        merchant_name = proposal.get("merchant_name", "Unknown merchant")
        location_name = proposal.get("location_name", "Unknown location")
        state["assistant_message"] = (
            "No matching merchant found.\n\n"
            "I can create a new merchant:\n"
            f"{merchant_name} / {location_name}\n\n"
            "Would you like to proceed? (Yes / No)"
        )
        state["status"] = WorkflowStatus.NEEDS_CLARIFICATION.value
        return state

    def node_ask_confirmation(self, state: WorkflowState) -> WorkflowState:
        """Render final draft summary for yes/no/edit confirmation."""

        draft = DraftTransaction.model_validate(state.get("draft") or {})
        state["assistant_message"] = (
            f"Amount: RM{draft.amount:.2f}\n"
            f"Merchant: {draft.merchant.merchant_name} ({draft.merchant.location_name})\n"
            f"Account: {draft.account.account_name}\n"
            f"Date: {draft.transaction_datetime.date().isoformat()}\n\n"
            "Confirm? (Yes / No / Edit)"
        )
        state["status"] = WorkflowStatus.NEEDS_CONFIRMATION.value
        state["pending_action"] = PendingAction.CONFIRM_DRAFT.value
        return state

    def node_insert_transaction_atomic(self, state: WorkflowState) -> WorkflowState:
        """Persist confirmed draft and update account balance atomically."""

        if not state.get("should_insert"):
            return state
        draft = DraftTransaction.model_validate(state.get("draft") or {})
        try:
            transaction_id, _ = insert_expense_and_update_balance(
                user_id=self._user_id,
                account_id=draft.account.account_id,
                merchant_id=draft.merchant.merchant_id,
                transaction_datetime=draft.transaction_datetime,
                total_amount=Decimal(draft.amount),
                notes=draft.notes,
            )
        except Exception as exc:
            state["status"] = WorkflowStatus.ERROR.value
            state["assistant_message"] = (
                "Failed to insert expense transaction. "
                f"Reason: {type(exc).__name__}: {exc}"
            )
            state["pending_action"] = None
            state["error"] = str(exc)
            return state

        state["transaction_id"] = transaction_id
        state["status"] = WorkflowStatus.COMPLETED.value
        state["pending_action"] = None
        state["assistant_message"] = f"Expense inserted successfully with transaction_id={transaction_id}."
        state["should_insert"] = False
        return state

    def route_after_resolve_account(self, state: WorkflowState) -> str:
        """Conditional edge selector after account resolution node."""

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return "end"
        if state.get("pending_action") == PendingAction.CLARIFY_ACCOUNT.value:
            return "ask_clarification"
        return "explore_merchants"

    def route_after_resolve_merchant(self, state: WorkflowState) -> str:
        """Conditional edge selector after merchant resolution node."""

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return "end"
        if state.get("pending_action") == PendingAction.CLARIFY_MERCHANT.value:
            return "ask_clarification"
        if state.get("pending_action") == PendingAction.APPROVE_MERCHANT_CREATION.value:
            return "ask_create_merchant"
        if state.get("pending_action") == PendingAction.CLARIFY_FIELDS.value:
            return "ask_clarification"
        if state.get("create_merchant_approved"):
            return "create_merchant_if_approved"
        return "build_draft"

    def route_after_build_draft(self, state: WorkflowState) -> str:
        """Conditional edge selector after draft build node."""

        if state.get("status") in {WorkflowStatus.CANCELLED.value, WorkflowStatus.ERROR.value}:
            return "end"
        if state.get("pending_action") == PendingAction.CLARIFY_FIELDS.value:
            return "ask_clarification"
        if state.get("should_insert"):
            return "insert_transaction_atomic"
        return "ask_confirmation"

    def wire_graph(self, builder) -> None:
        """Register all nodes/edges and conditional routes on the graph builder."""

        from langgraph.graph import END, START

        builder.add_node("ingest_message", self._with_node_logging("ingest_message", self.node_ingest_message))
        builder.add_node("extract_draft", self._with_node_logging("extract_draft", self.node_extract_draft))
        builder.add_node("inject_accounts", self._with_node_logging("inject_accounts", self.node_inject_accounts))
        builder.add_node("resolve_account", self._with_node_logging("resolve_account", self.node_resolve_account))
        builder.add_node("explore_merchants", self._with_node_logging("explore_merchants", self.node_explore_merchants))
        builder.add_node("resolve_merchant", self._with_node_logging("resolve_merchant", self.node_resolve_merchant))
        builder.add_node(
            "create_merchant_if_approved",
            self._with_node_logging("create_merchant_if_approved", self.node_create_merchant_if_approved),
        )
        builder.add_node("build_draft", self._with_node_logging("build_draft", self.node_build_draft))
        builder.add_node(
            "ask_clarification",
            self._with_node_logging("ask_clarification", self.node_ask_clarification),
        )
        builder.add_node(
            "ask_create_merchant",
            self._with_node_logging("ask_create_merchant", self.node_ask_create_merchant),
        )
        builder.add_node(
            "ask_confirmation",
            self._with_node_logging("ask_confirmation", self.node_ask_confirmation),
        )
        builder.add_node(
            "insert_transaction_atomic",
            self._with_node_logging("insert_transaction_atomic", self.node_insert_transaction_atomic),
        )

        builder.add_edge(START, "ingest_message")
        builder.add_edge("ingest_message", "extract_draft")
        builder.add_edge("extract_draft", "inject_accounts")
        builder.add_edge("inject_accounts", "resolve_account")
        builder.add_conditional_edges(
            "resolve_account",
            self.route_after_resolve_account,
            {
                "ask_clarification": "ask_clarification",
                "explore_merchants": "explore_merchants",
                "end": END,
            },
        )
        builder.add_edge("explore_merchants", "resolve_merchant")
        builder.add_conditional_edges(
            "resolve_merchant",
            self.route_after_resolve_merchant,
            {
                "ask_clarification": "ask_clarification",
                "ask_create_merchant": "ask_create_merchant",
                "create_merchant_if_approved": "create_merchant_if_approved",
                "build_draft": "build_draft",
                "end": END,
            },
        )
        builder.add_edge("create_merchant_if_approved", "build_draft")
        builder.add_conditional_edges(
            "build_draft",
            self.route_after_build_draft,
            {
                "ask_clarification": "ask_clarification",
                "ask_confirmation": "ask_confirmation",
                "insert_transaction_atomic": "insert_transaction_atomic",
                "end": END,
            },
        )
        builder.add_edge("ask_clarification", END)
        builder.add_edge("ask_create_merchant", END)
        builder.add_edge("ask_confirmation", END)
        builder.add_edge("insert_transaction_atomic", END)
