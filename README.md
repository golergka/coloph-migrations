# Coloph Migrations

`coloph-migrate` is a PostgreSQL migration CLI built for coding agents. It pairs
goal-driven project skills with numbered SQL migrations, checksum checks,
schema reconstruction, and deployed-code compatibility tests. Agents use the
CLI to inspect, change, and diagnose schemas instead of writing migration
machinery. The CLI is the public interface; Python modules are internal.

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
skills/change-database-schema/SKILL.md
skills/repair-database-schema/SKILL.md
```

`init` installs the bundled skills in the host project's `./skills` directory.
Configure your agent to discover that directory or load these files through
the project's agent instructions. File installation alone does not guarantee
automatic discovery in every agent host. Existing identical skills are left
alone. If a skill differs, `init` fails before writing files. Reconcile or move
that file before retrying, including when updating skills from a new release.
Existing application-specific skills, such as `db-schema`, remain separate.

The skills cover schema changes and failure diagnosis. CLI and configuration
details belong in this README and command help, not in skill descriptions.

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
| Failed SQL | A migration's second statement fails | The runner rolls back its transaction; earlier migrations remain committed. See transaction-control limitations below. |
| Schema drift | The target database differs from executable migrations | `validate` reconstructs and compares database schemas. It does not read the committed snapshot. |
| Unsafe checksum repair | Someone wants to accept modified applied SQL | `repair-checksums` requires schema equivalence first. |
| Incompatible deployed code | New schema breaks a tested query in deployed code | Configured `check-backwards` tests exercise deployed code against the final rebuilt schema. |

## Result boundaries and recovery

`plan` reports pending files and rejects checksum mismatches; it does not run
migration SQL. `list` reports `applied`, `pending`, `orphan`, `renamed`, and
`checksum_mismatch`. Inspect those statuses: `check` currently rejects pending
and checksum mismatches but does not reject orphaned or renamed records.
Status commands can create the migration tracking table.
Stricter history checks are tracked in
[#23](https://github.com/golergka/coloph-migrations/issues/23).

`validate --match-applied` reconstructs through the highest recorded migration
version. It assumes a contiguous applied history. Plain `validate` rebuilds the
full local chain. Neither compares data contents or the committed `schema.sql`.
A non-mutating snapshot check is tracked in
[#21](https://github.com/golergka/coloph-migrations/issues/21).

`repair-checksums --dry-run` previews updates after comparing the target schema
with the full reconstructed chain. Schema equality does not prove equivalent
data transformations. Do not replace this check with direct tracking-table
updates or treat ordinary pending migrations as checksum repairs.

The runner owns each migration transaction. Do not include transaction control
in migration SQL. The current text guard misses aliases such as `END;`, which
can cause partial application. This defect is tracked in
[#18](https://github.com/golergka/coloph-migrations/issues/18).

The before hook runs inside the migration transaction. The after hook runs
after that migration and its record commit, in a separate transaction. If the
after hook fails, the migration remains applied. A later `apply` currently
skips that unfinished hook; verify and complete it through the project's repair
process rather than assuming a successful retry repaired it. Durable hook
recovery is tracked in [#19](https://github.com/golergka/coloph-migrations/issues/19).

`check-backwards` can return `skipped`; that is not a passed compatibility test.
It detects added SQL files between the deployed revision and committed HEAD,
then tests deployed code against a reconstruction from the current files.
Use a committed, clean candidate for deployment checks. Tests cover the final
schema, not each intermediate prefix or the production data set.

If migrations run while old code serves traffic, first deploy code that stops
using an object. Drop or rename that object in a later deployment, after the
compatible code is actually deployed. A commit on main alone is insufficient.

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

The local TOML file overrides the base TOML file. Database URL resolution uses
this order: CLI flag, process `COLOPH_MIGRATIONS_DATABASE_URL`, process
`DATABASE_URL`, the same two names in `.env`, then the merged TOML value.
Relative TOML paths and `.env` resolve from the configuration directory.
These details identify which database a command will use; credentials and
cluster provisioning remain the host project's responsibility.

Fresh databases use Docker by default. A configured remote cluster must permit
temporary database creation and deletion. Schema dumps still use Docker with
a PostgreSQL client image, even when the temporary database is remote.

Configure backwards tests to accept the disposable database URL, for example:

```toml
backwards_setup_command = ["uv", "sync"]
backwards_test_command = ["uv", "run", "pytest"]
backwards_test_globs = ["tests/test_database_*.py"]
backwards_database_url_env = "TEST_DATABASE_URL"
```

The deployed test harness must use that environment variable. Test setup and
test selection belong to the consuming project.

Snapshot files can contain `-- schema-doc:` comments immediately before the SQL
statement they describe. Regeneration restores these notes when the following
statement line still matches. They do not become live database metadata.

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

`apply --reconstruction` applies the selected migration prefix, runs the configured after
hook at explicit checkpoint versions, and then runs it once against the rebuilt
schema. This keeps historical reconstructions from repeatedly validating every
intermediate schema while preserving known migration-chain dependencies.
Ordinary production `apply` remains fail-loud and keeps per-migration after
hooks.

Obsolete reconstruction settings and compatibility paths are scheduled for
complete removal in [#22](https://github.com/golergka/coloph-migrations/issues/22).
Do not rely on the accepted feature-skip or concurrent-DDL-retry settings:
the active batch path does not use them. Failed migrations must stop the run.

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
