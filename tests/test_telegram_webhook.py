from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings
from app.schemas import TelegramUpdate
from app.services.telegram import TelegramWebhookService


def _clear_settings_cache() -> None:
    """
    Clear the cached application settings.

    get_settings() is probably using @lru_cache, so once settings are loaded,
    they are reused. Since these tests change environment variables using
    monkeypatch, we need to clear the cache so the app reads the latest values.
    """
    get_settings.cache_clear()


def test_telegram_webhook_logs_text(monkeypatch, caplog):
    """
    Test that the Telegram webhook accepts a normal text message update,
    returns the expected response, and logs the message text.
    """

    # Disable webhook secret validation for this test
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")

    # Clear cached setting so that the new env is applied
    _clear_settings_cache()
    client = TestClient(app) # Create a test client for the FastAPI app

    payload = {
        "update_id": 123,
        "message": {
            "message_id": 55,
            "date": 1_714_000_000,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": 888, "is_bot": False, "first_name": "Tester"},
            "text": "hello from telegram",
        },
    }

    with caplog.at_level(logging.INFO):
        response = client.post("/api/v1/telegram/webhook", json=payload)
    
    # Assert that the response is correct and that the message text was logged
    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "received": True,
        "update_id": 123,
        "message_text": "hello from telegram",
        "reply_text": None,
    }
    assert "text=hello from telegram" in caplog.text


def test_telegram_webhook_accepts_non_text_update(monkeypatch):
    """
    Test that the Telegram webhook still accepts updates that do not contain text.

    Example: Telegram may send photos, stickers, commands, or other event types.
    In this case, the endpoint should not fail just because 'text' is missing.
    """

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    _clear_settings_cache()
    client = TestClient(app)

    payload = {
        "update_id": 124,
        "message": {
            "message_id": 56,
            "date": 1_714_000_001,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": 888, "is_bot": False},
        },
    }

    response = client.post("/api/v1/telegram/webhook", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "received": True,
        "update_id": 124,
        "message_text": None,
        "reply_text": None,
    }


def test_telegram_webhook_returns_add_expenses_prompt(monkeypatch):
    """Test that the add expenses command returns the first prompt."""

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    _clear_settings_cache()
    client = TestClient(app)

    payload = {
        "update_id": 126,
        "message": {
            "message_id": 57,
            "date": 1_714_000_002,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": 888, "is_bot": False},
            "text": "/add_expenses",
        },
    }

    response = client.post("/api/v1/telegram/webhook", json=payload)

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "received": True,
        "update_id": 126,
        "message_text": "/add_expenses",
        "reply_text": "What Expenses You Want To Add?",
    }


def test_telegram_service_sends_add_expenses_prompt(monkeypatch):
    """Test that the add expenses command sends a Telegram reply."""

    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"message_id": 99}}

    def fake_post(url, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr("app.services.telegram.requests.post", fake_post)
    service = TelegramWebhookService(bot_token="test-token")

    payload = {
        "update_id": 127,
        "message": {
            "message_id": 58,
            "date": 1_714_000_003,
            "chat": {"id": 999, "type": "private"},
            "from": {"id": 888, "is_bot": False},
            "text": "/add_expenses@TestFinanceBot",
        },
    }

    response = service.handle_update(TelegramUpdate.model_validate(payload))

    assert response.reply_text == "What Expenses You Want To Add?"
    assert calls == [
        {
            "url": "https://api.telegram.org/bottest-token/sendMessage",
            "json": {"chat_id": 999, "text": "What Expenses You Want To Add?"},
            "timeout": 15,
        }
    ]


def test_telegram_webhook_rejects_invalid_secret(monkeypatch):
    """
    Test that the Telegram webhook rejects requests with the wrong secret token.

    Telegram supports a secret token header:
    X-Telegram-Bot-Api-Secret-Token

    If the backend expects one secret but receives a different value,
    the request should be rejected with HTTP 401 Unauthorized.
    """
    
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    _clear_settings_cache()
    client = TestClient(app)

    payload = {"update_id": 125}
    response = client.post(
        "/api/v1/telegram/webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )

    assert response.status_code == 401
