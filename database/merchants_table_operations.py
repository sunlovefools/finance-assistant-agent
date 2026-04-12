from __future__ import annotations

from pydantic import BaseModel, Field
from rapidfuzz import fuzz
from sqlalchemy import text

from database.utils import get_default_user_id, get_engine


class MerchantCandidate(BaseModel):
    """One ranked merchant candidate returned by the resolver."""

    merchant_id: int
    merchant_name: str
    location_name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    score: float


class MerchantResolutionResult(BaseModel):
    """Resolution output sorted by score descending (best match first)."""

    candidates: list[MerchantCandidate] = Field(default_factory=list)


def _normalize_text(value: str) -> str:
    """Lowercase and collapse repeated whitespace for stable matching."""

    return " ".join(value.strip().lower().split())


def _build_location_text(row: dict) -> str:
    """
    Build a single location string used by RapidFuzz location scoring.
    Combines location_name + city + state + country (ignores empty parts).
    """

    parts = [
        row.get("location_name") or "",
        row.get("city") or "",
        row.get("state") or "",
        row.get("country") or "",
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def resolve_merchant(
    merchant_name_query: str,
    location_query: str,
    limit: int = 5,
) -> MerchantResolutionResult:
    """
    Resolve merchants with a 2-stage pipeline:
    1) PostgreSQL pg_trgm brand prefilter on merchant_name.
    2) RapidFuzz reranking with weighted name/location score.
    """

    # Basic input validation to avoid broad/ambiguous matching.
    if not isinstance(merchant_name_query, str) or not _normalize_text(merchant_name_query):
        raise ValueError("merchant_name_query must be a non-empty string.")
    if not isinstance(location_query, str) or not _normalize_text(location_query):
        raise ValueError("location_query must be a non-empty string.")
    if limit < 1:
        raise ValueError("limit must be >= 1.")

    merchant_name_norm = _normalize_text(merchant_name_query)
    location_query_norm = _normalize_text(location_query)
    user_id = get_default_user_id()
    # Fetch a wider initial pool so reranking has enough candidates.
    prefetch_limit = max(limit * 20, 50)

    # Stage 1: pg_trgm fuzzy match on normalized merchant_name only.
    # `%` uses trigram similarity threshold; ORDER BY similarity gives better seeds.
    # Merchant ownership scope is enforced via expense_transactions.user_id.
    stage_1_query = text(
        """
        SELECT
            m.merchant_id,
            m.merchant_name,
            m.location_name,
            m.city,
            m.state,
            m.country
        FROM merchants m
        WHERE LOWER(BTRIM(m.merchant_name)) % :merchant_name_query
          AND EXISTS (
                SELECT 1
                FROM expense_transactions et
                WHERE et.merchant_id = m.merchant_id
                  AND et.user_id = :user_id
          )
        ORDER BY similarity(LOWER(BTRIM(m.merchant_name)), :merchant_name_query) DESC, m.merchant_id ASC
        LIMIT :prefetch_limit
        """
    )

    # Use mapping rows so downstream code can access fields by name.
    with get_engine().begin() as connection:
        rows = (
            connection.execute(
                stage_1_query,
                {
                    "merchant_name_query": merchant_name_norm,
                    "user_id": user_id,
                    "prefetch_limit": prefetch_limit,
                },
            )
            .mappings()
            .all()
        )

    # No brand candidates from stage 1 -> return empty result.
    if not rows:
        return MerchantResolutionResult(candidates=[])

    # tuple fields: (final_score, merchant_name_score, merchant_id, candidate)
    scored_candidates: list[tuple[float, float, int, MerchantCandidate]] = []
    for row in rows:
        # Stage 2a: name relevance in [0.0, 1.0]. using WRatio which combines multiple fuzzy metrics for better accuracy on short strings.
        merchant_name_score = float(
            fuzz.WRatio(merchant_name_norm, _normalize_text(str(row["merchant_name"]))) / 100.0
        )
        # Stage 2b: location relevance in [0.0, 1.0].
        location_text = _normalize_text(_build_location_text(row))
        location_score = float(fuzz.WRatio(location_query_norm, location_text) / 100.0) if location_text else 0.0
        # Weighted final score as specified: 70% name, 30% location.
        final_score = (0.7 * merchant_name_score) + (0.3 * location_score)

        candidate = MerchantCandidate(
            merchant_id=int(row["merchant_id"]),
            merchant_name=str(row["merchant_name"]),
            location_name=str(row["location_name"]),
            city=row["city"],
            state=row["state"],
            country=row["country"],
            score=float(final_score),
        )
        scored_candidates.append((final_score, merchant_name_score, candidate.merchant_id, candidate))

    # Rank by final score (highest first).
    scored_candidates.sort(key=lambda item: -item[0])
    top_candidates = [candidate for _, _, _, candidate in scored_candidates[:limit]]
    return MerchantResolutionResult(candidates=top_candidates)
