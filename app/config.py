from __future__ import annotations

"""Configuration helpers for workflow runtime, logging, and model settings."""

import os
from pathlib import Path

from database.utils import build_database_url, get_default_user_id, load_dotenv


def get_openrouter_api_key() -> str | None:
    """Return OpenRouter API key if configured, otherwise None."""

    load_dotenv()
    raw = os.getenv("OPENROUTER_API_KEY")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def get_openrouter_base_url() -> str:
    """Return base URL for OpenRouter-compatible ChatCompletions API."""

    load_dotenv()
    return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()


def get_openrouter_model() -> str:
    """Return default model name used by the workflow extractor."""

    load_dotenv()
    return os.getenv("OPENROUTER_MODEL", "google/gemma-3-27b-it").strip()


def get_workflow_log_path() -> Path:
    """Return path to append-only workflow JSONL event log."""

    load_dotenv()
    default_path = Path("logs") / "expense_workflow_events.jsonl"
    raw = os.getenv("WORKFLOW_LOG_PATH")
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip())
    return default_path


def get_checkpoint_conn_string() -> str:
    """
    LangGraph Postgres checkpoint saver expects a standard PostgreSQL URL.
    SQLAlchemy uses postgresql+psycopg; we normalize it here.
    """

    url = build_database_url()
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def get_default_workflow_user_id() -> int:
    """Return server-scoped user id used in v1 workflow."""

    return get_default_user_id()
