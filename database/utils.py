"""
Utility functions for database connection and configuration across all the database operation modules.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def load_dotenv(dotenv_path: str = ".env") -> None:
    """Populate process env from a local .env file if vars are not already set."""
    env_file = Path(dotenv_path)
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def build_database_url() -> str:
    """Construct the database URL from environment variables, with basic validation."""
    load_dotenv()

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")

    missing = [
        name
        for name, value in (
            ("POSTGRES_USER", user),
            ("POSTGRES_PASSWORD", password),
            ("POSTGRES_DB", database),
            ("POSTGRES_HOST", host),
            ("POSTGRES_PORT", port),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required database env var(s): {', '.join(missing)}")

    # Return a URL in the format expected by SQLAlchemy
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"

# Cache the Engine instance so that it's reused across calls
@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Get a cached SQLAlchemy Engine instance for connecting to the database."""
    return create_engine(build_database_url(), future=True)


@lru_cache(maxsize=1)
def get_default_user_id() -> int:
    """
    Return the default user_id used by operation modules.
    Uses DEFAULT_USER_ID from env when provided, otherwise falls back to 1.
    """
    load_dotenv()
    raw_value = os.getenv("DEFAULT_USER_ID", "1").strip() # Because we are not expecting more than one user now, we will just have this default user id 1
    try:
        user_id = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"DEFAULT_USER_ID must be an integer, got: {raw_value!r}") from exc

    if user_id < 1:
        raise ValueError("DEFAULT_USER_ID must be >= 1.")

    return user_id
