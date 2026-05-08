from __future__ import annotations

"""Environment-backed application settings."""

import os
from functools import lru_cache

from pydantic import BaseModel, field_validator

from database.utils import load_dotenv


class Settings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "Financial Assistant API" # Application name for API metadata
    app_version: str = "1.0.0"
    telegram_bot_token: str | None = None # Telegram bot token for API authentication
    telegram_webhook_secret: str | None = None # Telegram webhook secret for validating incoming requests

    # Validators to convert empty strings to None for optional settings
    #TODO: Make it where the webhook secret is a MUST, same goes to the bot token
    @field_validator("telegram_bot_token", "telegram_webhook_secret", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def telegram_webhook_secret_configured(self) -> bool:
        """Return whether Telegram webhook requests should be secret-checked."""

        return self.telegram_webhook_secret is not None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings after loading local `.env` values."""

    load_dotenv()
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET"),
    )
