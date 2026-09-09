# Simple example

This example creates one PostgreSQL table.

```sh
cp .env.example .env
docker compose up -d --wait
uv sync
uv run coloph-migrate plan
uv run coloph-migrate apply
uv run coloph-migrate check
```

Run `docker compose down -v` to remove the example database.
