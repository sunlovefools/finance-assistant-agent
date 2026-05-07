from __future__ import annotations

"""LLM/draft-extraction helpers used by the expense workflow graph."""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.config import get_openrouter_api_key, get_openrouter_base_url, get_openrouter_model
from app.schemas import DraftExtraction


class DraftExtractor(Protocol):
    """Protocol for pluggable message-to-draft extractors."""

    def extract(self, user_message: str) -> DraftExtraction:
        """Parse a free-text user expense message into structured fields."""


def _clean_optional(value: str | None) -> str | None:
    """Normalize optional user text field to None when empty."""

    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


class HeuristicDraftExtractor:
    """
    Fallback extractor used when model credentials are not configured.

    This keeps the workflow usable in local/dev environments.
    """

    _amount_pattern = re.compile(r"(?:rm|myr|\$)?\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE)
    _merchant_span_pattern = re.compile(r"\bat\s+(.+?)(?:\s+\bfrom\b\s+|$)", re.IGNORECASE)
    _account_pattern = re.compile(r"\bfrom\s+(.+)$", re.IGNORECASE)

    def extract(self, user_message: str) -> DraftExtraction:
        text = user_message.strip()
        amount = self._extract_amount(text)
        account_query = self._extract_account_query(text)
        merchant_name_query, location_query = self._extract_merchant_and_location(text)

        return DraftExtraction(
            amount=amount,
            merchant_name_query=merchant_name_query,
            location_query=location_query,
            account_query=account_query,
            transaction_datetime=None,
            notes=None,
        )

    def _extract_amount(self, text: str) -> Decimal | None:
        match = self._amount_pattern.search(text)
        if not match:
            return None
        try:
            return Decimal(match.group(1))
        except InvalidOperation:
            return None

    def _extract_account_query(self, text: str) -> str | None:
        match = self._account_pattern.search(text)
        if not match:
            return None
        return _clean_optional(match.group(1))

    def _extract_merchant_and_location(self, text: str) -> tuple[str | None, str | None]:
        match = self._merchant_span_pattern.search(text)
        if not match:
            return None, None

        merchant_span = _clean_optional(match.group(1))
        if not merchant_span:
            return None, None

        parts = merchant_span.split()
        if len(parts) >= 2:
            return parts[0], " ".join(parts[1:])
        return merchant_span, None


class OpenRouterDraftExtractor:
    """Structured extractor backed by a model served through OpenRouter."""

    def __init__(self, api_key: str, base_url: str, model: str):
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=0,
        )
        self._structured_llm = self._llm.with_structured_output(DraftExtraction)

    def extract(self, user_message: str) -> DraftExtraction:
        system_prompt = (
            "Extract expense draft fields from user text. "
            "Return only known values and leave unknown fields as null. "
            "transaction_datetime must be null unless explicitly provided."
        )
        result = self._structured_llm.invoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        )
        if isinstance(result, DraftExtraction):
            return result
        return DraftExtraction.model_validate(result)


def get_draft_extractor() -> DraftExtractor:
    """
    Return OpenRouter-backed extractor when API key is present,
    otherwise return deterministic heuristic fallback.
    """

    api_key = get_openrouter_api_key()
    if api_key:
        return OpenRouterDraftExtractor(
            api_key=api_key,
            base_url=get_openrouter_base_url(),
            model=get_openrouter_model(),
        )
    return HeuristicDraftExtractor()


def classify_confirmation_response(message: str) -> str:
    """
    Classify confirmation-stage message into one of:
    yes | no | edit
    """

    normalized = message.strip().lower()
    if normalized in {"yes", "y", "confirm", "ok", "proceed"}:
        return "yes"
    if normalized in {"no", "n", "cancel", "stop"}:
        return "no"
    return "edit"


def parse_relative_datetime(message: str) -> datetime | None:
    """Parse minimal relative date terms supported by workflow v1."""

    normalized = message.strip().lower()
    now = datetime.now(timezone.utc)
    if "yesterday" in normalized:
        return (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    if "today" in normalized:
        return now
    return None
