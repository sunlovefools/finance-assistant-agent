from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.api import app
from app.config import get_settings


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
    }
    assert "text=hello from telegram" in caplog.text


def test_telegram_webhook_accepts_non_text_update(monkeypatch):
    """
    Test that the Telegram webhook still accepts updates that do not contain text.

    Example: Telegram may send photos, stickers, commands, or other event types.
    In this case, the endpoint should not fail just because 'text' is missing.
    """

    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "")
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
    assert response.json() == {"ok": True, "received": True, "update_id": 124, "message_text": None}


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
