# Financial Assistant Agent

This repository currently focuses on a Telegram-backed financial assistant and database design for personal expense tracking with transfer support.

## Telegram Webhook API

The FastAPI backend receives Telegram bot webhooks at:

- `POST /api/v1/telegram/webhook`

For the current milestone, the webhook validates the incoming Telegram update with Pydantic and logs the text sent to the bot. The log prints to the server console.

Run locally:

```bash
python main.py
```

Local health check:

```bash
curl http://localhost:8000/health
```

After starting ngrok, set `TELEGRAM_WEBHOOK_BASE_URL` in `.env` to your public ngrok HTTPS URL, then run:

```bash
python scripts/setup_telegram_webhook.py
```

Register the bot command menu:

```bash
python scripts/setup_telegram_commands.py
```

Required config:

- `TELEGRAM_BOT_TOKEN`: your bot token, already used when registering the webhook.
- `TELEGRAM_WEBHOOK_BASE_URL`: your public ngrok HTTPS URL, for example `https://your-domain.ngrok-free.app`.
- `TELEGRAM_WEBHOOK_SECRET`: a random secret you provide to Telegram through `secret_token`; Telegram will send it back in `X-Telegram-Bot-Api-Secret-Token`.

Supported bot commands:

- `/add_expenses`: returns `What Expenses You Want To Add?`.

Debug logs are written to `logs/debug.log`. The add-expenses command path uses
`telegram.add_expenses.*` log messages so command detection and reply sending are
easy to filter.

Run tests:

```bash
pytest -q
```

## Core Capabilities

- Record expense transactions and detailed line items.
- Track account-to-account transfers.
- Keep shared master data for merchants, categories, and products/services.
- Enforce ownership consistency between users and account-linked records.

## Database Docs

- ERD: [docs/Database_ERD.mmd](/c:/Users/Yoong%20Shen/Desktop/Financial%20Assitant%20Agent/docs/Database_ERD.mmd)
- Schema guide: [docs/DATABASE_SCHEMA.md](/c:/Users/Yoong%20Shen/Desktop/Financial%20Assitant%20Agent/docs/DATABASE_SCHEMA.md)
- Init SQL: [init/postgres/postgres_init.sql](/c:/Users/Yoong%20Shen/Desktop/Financial%20Assitant%20Agent/init/postgres/postgres_init.sql)

## Local PostgreSQL (Docker)

```bash
docker compose up -d
```

The compose file mounts `./init/postgres` to `/docker-entrypoint-initdb.d`.

Important: PostgreSQL only runs init scripts on first startup with an empty data volume.

If you want to recreate the schema from scratch:

```bash
docker compose down -v
docker compose up -d
```

If you already have a populated volume, new init SQL changes (for example `pg_trgm` extension/index additions) will not auto-apply. Either recreate the volume as above, or run the equivalent `CREATE EXTENSION/CREATE INDEX` statements manually on the running database.
