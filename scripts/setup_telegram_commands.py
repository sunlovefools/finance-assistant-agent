from __future__ import annotations

"""Register the Telegram bot commands from local environment variables."""

import os
import sys
from pathlib import Path

import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database.utils import load_dotenv  # noqa: E402

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
BOT_COMMANDS = [
    {
        "command": "add_expenses",
        "description": "Add a new expense",
    },
]


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def setup_commands() -> dict[str, object]:
    """Call Telegram `setMyCommands` using values from `.env`."""

    load_dotenv(str(ROOT_DIR / ".env"))

    bot_token = _required_env("TELEGRAM_BOT_TOKEN")
    response = requests.post(
        f"{TELEGRAM_API_BASE_URL}/bot{bot_token}/setMyCommands",
        json={"commands": BOT_COMMANDS},
        timeout=15,
    )

    print("Telegram API URL:", f"{TELEGRAM_API_BASE_URL}/bot<hidden>/setMyCommands")
    print("Status code:", response.status_code)
    print("Response text:", response.text)

    payload = response.json()

    if response.status_code >= 400:
        description = payload.get("description", "Unknown Telegram error")
        raise RuntimeError(f"Telegram rejected bot commands: {description}")

    if not payload.get("ok"):
        description = payload.get("description", "Telegram did not accept the bot commands.")
        raise RuntimeError(str(description))

    return {"commands": BOT_COMMANDS, "telegram_response": payload}


def main() -> None:
    """CLI entrypoint."""

    try:
        result = setup_commands()
    except requests.RequestException as exc:
        raise SystemExit(f"Telegram command setup request failed: {exc}") from exc
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    command_names = ", ".join(f"/{command['command']}" for command in result["commands"])
    print(f"Telegram bot commands registered: {command_names}")
    print(result["telegram_response"].get("description", "Command setup completed."))


if __name__ == "__main__":
    main()
