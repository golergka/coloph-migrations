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

The lockfile records the exact package version. To run a fixed version without
adding a dependency, replace `VERSION` in this command:

```sh
uvx --from 'coloph-migrations==VERSION' coloph-migrate --help
```

Initialize the migration files at the repository root:

```sh
uv run coloph-migrate init
```

This command creates these files if they do not exist:

```text
coloph-migrations.toml
migrations/0001_init.sql
.env
```

The generated configuration contains:

```toml
migrations_dir = "migrations"
schema_snapshot = "migrations/schema.sql"
```

Set `DATABASE_URL` in `.env`. Process environment variables override `.env`.
The `COLOPH_MIGRATIONS_DATABASE_URL` variable remains available as a higher-priority override.

Edit the initial migration, inspect it, and apply it:

```sh
printf 'CREATE TABLE account (id bigint PRIMARY KEY);\n' > migrations/0001_init.sql
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

`--json` is a global option. Put it before the command:

```sh
uv run coloph-migrate --json list
```

Use `apply --up-to 012` to apply
versions before `012` (the boundary is exclusive). `apply --reconstruction` enables
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
deployed_fetch_remote = "origin" # optional; refresh deployed_ref before backwards check

# Optional. The before file runs in the migration transaction. During normal
# apply, the after file runs in a separate transaction after each migration is
# recorded and committed. During reconstruction, the after file runs at any
# configured checkpoint versions and once after the selected schema is fully
# rebuilt.
before_each_migration_sql = "migrations/before_each.sql"
after_each_migration_sql = "migrations/after_each.sql"

# Disposable-reconstruction options.
fresh_statement_timeout_seconds = 90
reconstruction_after_hook_versions = ["0186"]

# Optional. Fresh databases use local Docker when this environment variable is
# absent or set to "local-docker". A PostgreSQL URL selects a shared cluster;
# non-loopback URLs must use sslmode=verify-full. Loopback URLs can use the
# caller's SSL mode so an authenticated local TCP proxy remains transparent.
test_cluster_url_env = "TEST_POSTGRES_CLUSTER_DSN"
```

Explicit CLI flags override configuration files.

## Command reference

```text
coloph-migrate init
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

Put global `--json` before the command, for example `coloph-migrate --json list`.

`apply --reconstruction` activates only the configured disposable-database
policies. It applies the selected migration prefix, runs the configured after
hook at explicit checkpoint versions, and then runs it once against the rebuilt
schema. This keeps historical reconstructions from repeatedly validating every
intermediate schema while preserving known migration-chain dependencies.
Ordinary production `apply` remains fail-loud and keeps per-migration after
hooks.

## Coloph dependency workflow

When Coloph needs a `coloph-migrations` behavior change, edit this package
directly in its local checkout, test it here, commit and push the package
change, then update Coloph's pinned Git dependency and lockfile to that exact
commit. Do not patch installed site-packages or work around dependency behavior
inside Coloph.

The test suite deliberately exercises broken numbering, explicit transaction
control, failed migration rollback, pre/post-hook transaction boundaries,
checksum drift, schema drift, and safe-versus-unsafe checksum repair.

## Public writing

Do not publish links or issue references to private repositories.
This rule applies to source files, documentation, issues, pull requests, comments, and release notes.
Explain each problem with a self-contained example, the actual result, the expected result, and the practical impact.
Separate proposed features from observed defects. Do not present missing tests alone as a defect.

## License

GPL-3.0-only. The Coloph name and logo are not licensed for use as trademarks.
