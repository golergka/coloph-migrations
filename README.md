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

# Optional. The before file runs in the migration transaction. The after file
# runs in a separate transaction after the migration is recorded and committed.
before_each_migration_sql = "migrations/before_each.sql"
after_each_migration_sql = "migrations/after_each.sql"

# Optional reconstruction-only behavior for extensions unavailable in the
# disposable PostgreSQL image and for catalog-heavy post hooks.
fresh_skip_feature_not_supported = true
fresh_statement_timeout_seconds = 90
fresh_vacuum_after_each_migration = true
```

Use an ignored `coloph-migrations.local.toml` for credentials and local
overrides. Explicit CLI flags override both files. For credentials that must not appear in process arguments,
set `COLOPH_MIGRATIONS_DATABASE_URL` instead of storing `database_url` or passing `--database-url`.

## Commands

```text
coloph-migrate apply
coloph-migrate list
coloph-migrate check
coloph-migrate snapshot
coloph-migrate validate
coloph-migrate repair-checksums
coloph-migrate check-chain
coloph-migrate check-backwards
```

Pass `--json` for stable machine-readable output.

`apply --reconstruction` activates only the configured disposable-database
policies. Ordinary production `apply` remains fail-loud.

The test suite deliberately exercises broken numbering, explicit transaction
control, failed migration rollback, pre/post-hook transaction boundaries,
checksum drift, schema drift, and safe-versus-unsafe checksum repair.

## License

GPL-3.0-only. The Coloph name and logo are not licensed for use as trademarks.
