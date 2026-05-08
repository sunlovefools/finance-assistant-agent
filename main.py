from __future__ import annotations

"""Local executable entrypoint for running FastAPI workflow service."""

import uvicorn

from app.api import app


def main() -> None:
    """Start API server in non-reload mode for stable local runtime."""

    uvicorn.run("app.api:app", host="0.0.0.0", port=8001, reload=False) # Main entry point will be app/api.py


if __name__ == "__main__":
    main()
