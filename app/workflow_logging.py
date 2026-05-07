from __future__ import annotations

"""Structured JSONL logging for workflow traceability and debugging."""

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class WorkflowEventLogger:
    """Append-only JSONL logger for workflow visibility."""

    def __init__(self, file_path: Path):
        self._file_path = file_path
        self._lock = Lock()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(
        self,
        *,
        level: str,
        trace_id: str,
        session_id: str,
        run_id: str,
        node: str,
        event_type: str,
        latency_ms: float | None = None,
        payload_summary: dict[str, Any] | None = None,
    ) -> None:
        """Write one structured event line with run/session correlation fields."""

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "trace_id": trace_id,
            "session_id": session_id,
            "run_id": run_id,
            "node": node,
            "event_type": event_type,
            "latency_ms": latency_ms,
            "payload_summary": payload_summary or {},
        }
        line = json.dumps(event, ensure_ascii=True, default=str)
        with self._lock:
            with self._file_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
