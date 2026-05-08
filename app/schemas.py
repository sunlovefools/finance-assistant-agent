from __future__ import annotations

"""Pydantic schemas shared by API routers and services."""

from pydantic import BaseModel, ConfigDict, Field


class TelegramUser(BaseModel):
    """Telegram user object subset used by the webhook handler."""

    model_config = ConfigDict(extra="ignore")

    id: int
    is_bot: bool
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class TelegramChat(BaseModel):
    """Telegram chat object subset used by the webhook handler."""

    model_config = ConfigDict(extra="ignore")

    id: int
    type: str
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class TelegramMessage(BaseModel):
    """Telegram message object subset needed for this first webhook milestone."""

    model_config = ConfigDict(extra="ignore")

    message_id: int
    date: int
    chat: TelegramChat
    from_user: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None
    caption: str | None = None

    @property
    def display_text(self) -> str | None:
        """Return the user-visible text payload, if the update contains one."""

        if self.text and self.text.strip():
            return self.text.strip()
        if self.caption and self.caption.strip():
            return self.caption.strip()
        return None


class TelegramUpdate(BaseModel):
    """Telegram webhook update subset.

    Telegram sends many update shapes. Unknown fields are intentionally ignored so
    future Telegram features do not break the webhook while unsupported updates
    are safely acknowledged.
    """

    model_config = ConfigDict(extra="ignore")

    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None
    channel_post: TelegramMessage | None = None
    edited_channel_post: TelegramMessage | None = None

    @property
    def effective_message(self) -> TelegramMessage | None:
        """Return the first supported message-like payload on the update."""

        return self.message or self.edited_message or self.channel_post or self.edited_channel_post


class TelegramWebhookResponse(BaseModel):
    """Response returned after a Telegram update is accepted."""

    ok: bool = True
    received: bool
    update_id: int
    message_text: str | None = None
