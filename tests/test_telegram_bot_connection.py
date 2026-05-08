"""
Simple test to verify Telegram bot connection using the getMe method.
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

response = requests.get(
    f"https://api.telegram.org/bot{BOT_TOKEN}/getMe",
    timeout=10,
)

print(response.status_code)
print(response.text)