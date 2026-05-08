from __future__ import annotations

"""FastAPI application setup."""

import logging

from fastapi import FastAPI

from app.config import get_settings
from app.routers.telegram import router as telegram_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    settings = get_settings()

    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(telegram_router)

    """Add a simple health check endpoint for local and container health monitoring."""
    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        """Simple liveness endpoint for local and container health checks."""

        return {"status": "ok"}

    return app


app = create_app()
