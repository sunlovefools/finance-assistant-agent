from __future__ import annotations

"""Merchant read/write operations used by the expense workflow."""

from pydantic import BaseModel, Field
from rapidfuzz import fuzz
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

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


class CreatedMerchantResult(BaseModel):
    """Result of creating or reusing a merchant row."""

    merchant_id: int
    merchant_name: str
    location_name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None


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


def _search_merchants_ranked(
    merchant_name_query: str,
    location_query: str | None,
    limit: int = 5,
) -> MerchantResolutionResult:
    """
    Resolve merchant candidates with a 2-stage ranking pipeline:
    1) PostgreSQL pg_trgm brand prefilter on merchant_name.
    2) RapidFuzz reranking with weighted name/location score.

    This function is intentionally private; public callers should use:
    - explore_merchants_without_location(...)
    - explore_merchants_with_location(...)
    """

    # Basic input validation to avoid broad/ambiguous matching.
    if not isinstance(merchant_name_query, str) or not _normalize_text(merchant_name_query):
        raise ValueError("merchant_name_query must be a non-empty string.")
    if limit < 1:
        raise ValueError("limit must be >= 1.")

    merchant_name_norm = _normalize_text(merchant_name_query)
    if isinstance(location_query, str):
        normalized_location = _normalize_text(location_query)
        location_query_norm = normalized_location if normalized_location else None
    else:
        location_query_norm = None
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
        WHERE LOWER(BTRIM(m.merchant_name)) % CAST(:merchant_name_query AS TEXT)
          AND EXISTS (
                SELECT 1
                FROM expense_transactions et
                WHERE et.merchant_id = m.merchant_id
                  AND et.user_id = :user_id
          )
        ORDER BY similarity(
            LOWER(BTRIM(m.merchant_name)),
            CAST(:merchant_name_query AS TEXT)
        ) DESC, m.merchant_id ASC
        LIMIT :prefetch_limit
        """
    )

    # Use mapping rows so downstream code can access fields by name.
    try:
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
    except ProgrammingError:
        # If pg_trgm operators are unavailable in the running DB, retry
        # with a LIKE prefilter in a fresh transaction.
        fallback_query = text(
            """
            SELECT
                m.merchant_id,
                m.merchant_name,
                m.location_name,
                m.city,
                m.state,
                m.country
            FROM merchants m
            WHERE LOWER(BTRIM(m.merchant_name)) LIKE :merchant_like
              AND EXISTS (
                    SELECT 1
                    FROM expense_transactions et
                    WHERE et.merchant_id = m.merchant_id
                      AND et.user_id = :user_id
              )
            ORDER BY LOWER(BTRIM(m.merchant_name)) ASC, m.merchant_id ASC
            LIMIT :prefetch_limit
            """
        )
        with get_engine().begin() as connection:
            rows = (
                connection.execute(
                    fallback_query,
                    {
                        "merchant_like": f"%{merchant_name_norm}%",
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
        # If no location_query is provided, treat location as perfect (100%).
        location_text = _normalize_text(_build_location_text(row))
        if location_query_norm is None:
            location_score = 1.0
        else:
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


def explore_merchants_without_location(
    merchant_name_query: str,
    limit: int = 50,
) -> MerchantResolutionResult:
    """
    Public tool used by the workflow when only merchant name is available.
    """

    return _search_merchants_ranked(
        merchant_name_query=merchant_name_query,
        location_query=None,
        limit=limit,
    )


def explore_merchants_with_location(
    merchant_name_query: str,
    location_query: str,
    limit: int = 50,
) -> MerchantResolutionResult:
    """
    Public tool used by the workflow when both merchant and location are available.
    """

    if not isinstance(location_query, str) or not _normalize_text(location_query):
        raise ValueError("location_query must be a non-empty string.")

    return _search_merchants_ranked(
        merchant_name_query=merchant_name_query,
        location_query=location_query,
        limit=limit,
    )


def _resolve_or_create_unknown_merchant_type_id(connection) -> int:
    """Resolve a stable merchant_type_id for 'unknown', creating it if missing."""

    existing = connection.execute(
        text(
            """
            SELECT merchant_type_id
            FROM merchant_types
            WHERE LOWER(BTRIM(merchant_type_name)) = 'unknown'
            ORDER BY merchant_type_id ASC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if existing is not None:
        return int(existing)

    inserted = connection.execute(
        text(
            """
            INSERT INTO merchant_types (merchant_type_name, description)
            VALUES ('unknown', 'Fallback merchant type created by expense workflow.')
            RETURNING merchant_type_id
            """
        )
    ).scalar_one()
    return int(inserted)


def create_merchant(
    merchant_name: str,
    location_name: str,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
) -> CreatedMerchantResult:
    """
    Create a merchant row using a deterministic default merchant type ('unknown').
    If a normalized merchant + location match exists, reuse it.
    """

    merchant_name_norm = _normalize_text(merchant_name)
    location_name_norm = _normalize_text(location_name)
    if not merchant_name_norm:
        raise ValueError("merchant_name must be a non-empty string.")
    if not location_name_norm:
        raise ValueError("location_name must be a non-empty string.")

    with get_engine().begin() as connection:
        existing = connection.execute(
            text(
                """
                SELECT
                    merchant_id,
                    merchant_name,
                    location_name,
                    city,
                    state,
                    country
                FROM merchants
                WHERE LOWER(BTRIM(merchant_name)) = :merchant_name_norm
                  AND LOWER(BTRIM(location_name)) = :location_name_norm
                ORDER BY merchant_id ASC
                LIMIT 1
                """
            ),
            {
                "merchant_name_norm": merchant_name_norm,
                "location_name_norm": location_name_norm,
            },
        ).mappings().first()

        if existing:
            return CreatedMerchantResult(
                merchant_id=int(existing["merchant_id"]),
                merchant_name=str(existing["merchant_name"]),
                location_name=str(existing["location_name"]),
                city=existing["city"],
                state=existing["state"],
                country=existing["country"],
            )

        merchant_type_id = _resolve_or_create_unknown_merchant_type_id(connection)
        created = connection.execute(
            text(
                """
                INSERT INTO merchants (
                    merchant_type_id,
                    merchant_name,
                    location_name,
                    city,
                    state,
                    country
                )
                VALUES (
                    :merchant_type_id,
                    :merchant_name,
                    :location_name,
                    :city,
                    :state,
                    :country
                )
                RETURNING
                    merchant_id,
                    merchant_name,
                    location_name,
                    city,
                    state,
                    country
                """
            ),
            {
                "merchant_type_id": merchant_type_id,
                "merchant_name": merchant_name.strip(),
                "location_name": location_name.strip(),
                "city": city.strip() if isinstance(city, str) and city.strip() else None,
                "state": state.strip() if isinstance(state, str) and state.strip() else None,
                "country": country.strip() if isinstance(country, str) and country.strip() else None,
            },
        ).mappings().one()

    return CreatedMerchantResult(
        merchant_id=int(created["merchant_id"]),
        merchant_name=str(created["merchant_name"]),
        location_name=str(created["location_name"]),
        city=created["city"],
        state=created["state"],
        country=created["country"],
    )
