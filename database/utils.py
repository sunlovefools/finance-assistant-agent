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
    load_dotenv()

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")

    missing = [
        name
        for name, value in (
            ("POSTGRES_USER", user),
            ("POSTGRES_PASSWORD", password),
            ("POSTGRES_DB", database),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Missing required database env var(s): {', '.join(missing)}")

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(build_database_url(), future=True)
