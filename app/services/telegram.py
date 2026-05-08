from __future__ import annotations

"""Telegram webhook processing service."""

import logging

import requests

from app.schemas import TelegramUpdate, TelegramWebhookResponse

logger = logging.getLogger(__name__)

ADD_EXPENSES_COMMAND = "add_expenses"
ADD_EXPENSES_REPLY = "What Expenses You Want To Add?"
TELEGRAM_API_BASE_URL = "https://api.telegram.org"


class TelegramWebhookService:
    """Process Telegram updates without coupling business logic to FastAPI."""

    def __init__(self, bot_token: str | None = None) -> None:
        self.bot_token = bot_token

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

        reply_text = None
        command_name = _extract_command_name(message_text)
        is_add_expenses_command = command_name == ADD_EXPENSES_COMMAND

        logger.debug(
            "telegram.add_expenses.command_check update_id=%s chat_id=%s user_id=%s "
            "message_text=%r command_name=%r matched=%s",
            update.update_id,
            chat_id,
            user_id,
            message_text,
            command_name,
            is_add_expenses_command,
        )

        if is_add_expenses_command:
            reply_text = ADD_EXPENSES_REPLY
            self._send_message(
                chat_id=chat_id,
                text=reply_text,
                update_id=update.update_id,
                user_id=user_id,
            )

        return TelegramWebhookResponse(
            received=True,
            update_id=update.update_id,
            message_text=message_text,
            reply_text=reply_text,
        )

    def _send_message(self, chat_id: int, text: str, update_id: int, user_id: int | None) -> None:
        """Send a text message back to the Telegram chat."""

        if self.bot_token is None:
            logger.debug(
                "telegram.add_expenses.reply_skipped update_id=%s chat_id=%s user_id=%s reason=no_bot_token",
                update_id,
                chat_id,
                user_id,
            )
            return

        logger.debug(
            "telegram.add_expenses.reply_send_attempt update_id=%s chat_id=%s user_id=%s text=%r",
            update_id,
            chat_id,
            user_id,
            text,
        )

        try:
            response = requests.post(
                f"{TELEGRAM_API_BASE_URL}/bot{self.bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=15,
            )
            payload = response.json()
        except requests.RequestException:
            logger.exception(
                "telegram.add_expenses.reply_send_failed update_id=%s chat_id=%s user_id=%s",
                update_id,
                chat_id,
                user_id,
            )
            return

        if response.status_code >= 400 or not payload.get("ok"):
            logger.error(
                "telegram.add_expenses.reply_rejected update_id=%s chat_id=%s user_id=%s "
                "status_code=%s telegram_response=%s",
                update_id,
                chat_id,
                user_id,
                response.status_code,
                payload,
            )
            return

        logger.debug(
            "telegram.add_expenses.reply_sent update_id=%s chat_id=%s user_id=%s message_id=%s",
            update_id,
            chat_id,
            user_id,
            payload.get("result", {}).get("message_id"),
        )


def _extract_command_name(message_text: str) -> str | None:
    """Return the normalized Telegram command name at the start of the text."""

    first_token = message_text.split(maxsplit=1)[0]
    if not first_token.startswith("/"):
        return None

    return first_token[1:].split("@", maxsplit=1)[0].lower()
