from __future__ import annotations

"""Register the Telegram bot webhook from local environment variables."""

import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database.utils import load_dotenv  # noqa: E402

WEBHOOK_PATH = "/api/v1/telegram/webhook"
TELEGRAM_API_BASE_URL = "https://api.telegram.org"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _build_webhook_url(base_url: str) -> str:
    normalized_base_url = base_url.strip().rstrip("/") + "/"
    if not normalized_base_url.startswith("https://"):
        raise RuntimeError("TELEGRAM_WEBHOOK_BASE_URL must be a public HTTPS URL, such as your ngrok URL.")
    return urljoin(normalized_base_url, WEBHOOK_PATH.lstrip("/"))


def setup_webhook() -> dict[str, object]:
    """Call Telegram `setWebhook` using values from `.env`."""

    load_dotenv(str(ROOT_DIR / ".env"))

    bot_token = _required_env("TELEGRAM_BOT_TOKEN")
    webhook_base_url = _required_env("TELEGRAM_WEBHOOK_BASE_URL")
    webhook_secret = _required_env("TELEGRAM_WEBHOOK_SECRET")
    webhook_url = _build_webhook_url(webhook_base_url)

    response = requests.post(
        f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/setWebhook",
        data={
            "url": webhook_url,
            "secret_token": webhook_secret,
            "drop_pending_updates": "true",
        },
        timeout=15,
    )
    print("Webhook URL:", webhook_url)
    print("Telegram API URL:", f"{TELEGRAM_API_BASE_URL}/bot<hidden>/setWebhook")
    print("Status code:", response.status_code)
    print("Response text:", response.text)

    payload = response.json()

    if response.status_code >= 400:
        description = payload.get("description", "Unknown Telegram error")
        raise RuntimeError(f"Telegram rejected webhook: {description}")

    if not payload.get("ok"):
        description = payload.get("description", "Telegram did not accept the webhook.")
        raise RuntimeError(str(description))

    return {"webhook_url": webhook_url, "telegram_response": payload}


def main() -> None:
    """CLI entrypoint."""

    try:
        result = setup_webhook()
    except requests.RequestException as exc:
        raise SystemExit(f"Telegram webhook setup request failed: {exc}") from exc
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Telegram webhook registered: {result['webhook_url']}")
    print(result["telegram_response"].get("description", "Webhook setup completed."))


if __name__ == "__main__":
    main()
