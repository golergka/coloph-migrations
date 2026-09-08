# Coloph Migrations

`coloph-migrate` is an opinionated PostgreSQL migration CLI extracted from
Coloph's production deployment workflow. It uses sequential SQL migrations,
immutable applied checksums, and canonical schema snapshots. The CLI is the
public interface; Python modules are internal.

## Quick start

Add it to the repository's development dependencies (and commit the updated
`pyproject.toml` and lockfile):

```sh
uv add --dev coloph-migrations
```

Then add `coloph-migrations.toml` at the repository root:

```toml
migrations_dir = "migrations"
schema_snapshot = "migrations/schema.sql"
database_url = "postgresql://postgres:postgres@localhost:5432/app"
```

Create a numbered migration, inspect it, and apply it:

```sh
mkdir -p migrations
printf 'CREATE TABLE account (id bigint PRIMARY KEY);\n' > migrations/001_create_account.sql
uv run coloph-migrate plan
uv run coloph-migrate apply
uv run coloph-migrate snapshot
```

Use an ignored `coloph-migrations.local.toml` for local credentials and
overrides. `COLOPH_MIGRATIONS_DATABASE_URL` keeps the URL out of files and
process arguments.

## Common workflows

```sh
# Show applied and pending migrations
uv run coloph-migrate list

# Require that every migration is applied and its checksum still matches
uv run coloph-migrate check

# Rebuild a disposable database and compare its schema to the target database
uv run coloph-migrate validate

# Regenerate schema.sql from a disposable reconstruction
uv run coloph-migrate snapshot --fresh

# Check a new migration number against main and deployed Git refs
uv run coloph-migrate check-chain

# Run deployed code against the new schema before deployment
uv run coloph-migrate check-backwards
```

For machine-readable output, add `--json`. Use `apply --up-to 012` to stop at a
specific version. `apply --reconstruction` enables
only the disposable-database policies configured for reconstruction.

## What it prevents

| Problem | Example | Guardrail |
| --- | --- | --- |
| Edited history | `004_add_index.sql` changes after production applied it | `plan` and `check` reject checksum drift. |
| Bad ordering | A branch adds `007_*.sql` while `main` already has `007_*.sql` | `check-chain` detects collisions across refs. |
| Partial change | A migration's second statement fails | Each migration runs in one transaction, so it rolls back. |
| Snapshot lies | `schema.sql` no longer matches executable migrations | `validate` reconstructs and compares schemas. |
| Unsafe checksum repair | Someone wants to accept modified applied SQL | `repair-checksums` requires schema equivalence first. |
| Unsafe deploy | New schema breaks currently deployed code | `check-backwards` tests deployed code against it. |

## Configuration

```toml
migrations_dir = "migrations"
schema_snapshot = "migrations/schema.sql"
database_url = "postgresql://postgres:postgres@localhost:5432/app"
main_ref = "main"
deployed_ref = "deployed"
deployed_fetch_remote = "origin" # optional; refresh tags before backwards check

# Runs before a migration in its transaction, and after it in a new transaction.
before_each_migration_sql = "migrations/before_each.sql"
after_each_migration_sql = "migrations/after_each.sql"

# Disposable-reconstruction options.
fresh_skip_feature_not_supported = true
fresh_statement_timeout_seconds = 90
fresh_vacuum_after_each_migration = true
```

Explicit CLI flags override configuration files.

## Command reference

```text
coloph-migrate apply
coloph-migrate list
coloph-migrate plan
coloph-migrate check
coloph-migrate snapshot
coloph-migrate validate
coloph-migrate repair-checksums
coloph-migrate check-chain
coloph-migrate check-backwards
```

## License

GPL-3.0-only. The Coloph name and logo are not licensed for use as trademarks.
