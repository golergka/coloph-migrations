# Coloph Migrations

`coloph-migrate` is an opinionated PostgreSQL migration CLI extracted from the
production deployment workflow used by Coloph.

It keeps migrations agent-friendly by making the current schema inspectable and
the dangerous states explicit:

- sequential numbered SQL files with no gaps;
- immutable checksums for applied migrations;
- one transaction per migration;
- optional SQL before each migration and after each committed migration;
- canonical, deterministic `schema.sql` snapshots;
- reconstruction and schema-equivalence validation in disposable PostgreSQL;
- checksum repair only after schema equivalence is proven;
- migration-chain collision checks against Git refs;
- old-code/new-schema compatibility checks before deployment.

The supported public interface is the CLI. Python modules are implementation
details and may change without notice.

## Configuration

Create `coloph-migrations.toml` in the repository root:

```toml
migrations_dir = "migrations"
schema_snapshot = "migrations/schema.sql"
database_url = "postgresql://postgres:postgres@localhost:5432/app"
main_ref = "main"
deployed_ref = "deployed"
deployed_fetch_remote = "origin" # optional; refresh tags before backwards check

# Optional. The before file runs in the migration transaction. During normal
# apply, the after file runs in a separate transaction after each migration is
# recorded and committed. During reconstruction, the after file runs at any
# configured checkpoint versions and once after the selected schema is fully
# rebuilt.
before_each_migration_sql = "migrations/before_each.sql"
after_each_migration_sql = "migrations/after_each.sql"

# Optional reconstruction-only behavior for extensions unavailable in the
# disposable PostgreSQL image and for catalog-heavy post hooks.
fresh_skip_feature_not_supported = true
fresh_statement_timeout_seconds = 90
fresh_vacuum_after_each_migration = true
reconstruction_after_hook_versions = ["0186"]
```

Use an ignored `coloph-migrations.local.toml` for credentials and local
overrides. Explicit CLI flags override both files. For credentials that must not appear in process arguments,
set `COLOPH_MIGRATIONS_DATABASE_URL` instead of storing `database_url` or passing `--database-url`.

## Commands

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

Pass `--json` for stable machine-readable output.

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

## License

GPL-3.0-only. The Coloph name and logo are not licensed for use as trademarks.
