from __future__ import annotations

"""Telegram webhook processing service."""

import logging

from app.schemas import TelegramUpdate, TelegramWebhookResponse

logger = logging.getLogger(__name__)


class TelegramWebhookService:
    """Process Telegram updates without coupling business logic to FastAPI."""

    def handle_update(self, update: TelegramUpdate) -> TelegramWebhookResponse:
        """Acknowledge the update and log incoming user text."""

        message = update.effective_message
        message_text = message.display_text if message is not None else None

        if message_text is None:
            logger.info("Received Telegram update without text. update_id=%s", update.update_id)
            return TelegramWebhookResponse(received=True, update_id=update.update_id)

        chat_id = message.chat.id
        user_id = message.from_user.id if message.from_user is not None else None
        logger.info(
            "Received Telegram text. update_id=%s chat_id=%s user_id=%s text=%s",
            update.update_id,
            chat_id,
            user_id,
            message_text,
        )

        return TelegramWebhookResponse(
            received=True,
            update_id=update.update_id,
            message_text=message_text,
        )
