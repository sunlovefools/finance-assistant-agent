# Financial Assistant Agent

This repository currently focuses on database design for personal expense tracking with transfer support.

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
