from __future__ import annotations

"""Telegram webhook API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.schemas import TelegramUpdate, TelegramWebhookResponse
from app.services.telegram import TelegramWebhookService

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


def get_telegram_service() -> TelegramWebhookService:
    """Dependency provider for Telegram webhook handling."""

    settings = get_settings()
    return TelegramWebhookService(bot_token=settings.telegram_bot_token)


def verify_telegram_secret(
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate Telegram's webhook secret header when configured."""

    expected_secret = settings.telegram_webhook_secret
    if expected_secret is None:
        return

    if x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram webhook secret.",
        )

"""Telegram webhook endpoint to receive updates from Telegram and log message text."""
@router.post(
    "/webhook", # The full endpoint is /api/v1/telegram/webhook
    response_model=TelegramWebhookResponse,
    dependencies=[Depends(verify_telegram_secret)],
)
def receive_telegram_webhook(
    update: TelegramUpdate,
    service: TelegramWebhookService = Depends(get_telegram_service),
) -> TelegramWebhookResponse:
    """Receive Telegram webhook updates and log incoming message text."""

    return service.handle_update(update)
