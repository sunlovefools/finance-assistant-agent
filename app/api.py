from __future__ import annotations

"""FastAPI application setup."""

import logging
from pathlib import Path

from fastapi import FastAPI

from app.config import get_settings
from app.routers.telegram import router as telegram_router


DEBUG_LOG_PATH = Path("logs/debug.log")


def _configure_logging() -> None:
    """Configure console and debug-file logging for the API process."""

    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    logging.getLogger("urllib3").setLevel(logging.INFO)

    if not any(
        isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler)
        for handler in root_logger.handlers
    ):
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)

    debug_log_file = str(DEBUG_LOG_PATH.resolve())
    if not any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename == debug_log_file
        for handler in root_logger.handlers
    ):
        file_handler = logging.FileHandler(debug_log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    _configure_logging()
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
