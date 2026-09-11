---
name: change-database-schema
description: Change database tables, columns, constraints, indexes, or functions and prepare the schema change for deployment. Use for schema changes in a project with numbered SQL migrations; leave application data modeling and infrastructure operations to project guidance.
---

# Change database schema

Use the project's pinned `coloph-migrate` CLI for migration operations. Read
`coloph-migrations.toml` and the project's deployment instructions. Run from the
configuration directory, or pass global `--config PATH`. Use the configured
migration and snapshot paths below. Python projects usually run the CLI through
`uv run`.

Read the committed schema snapshot for current structure. Add the requested
change as the next numbered SQL file. Use `coloph-migrate check-chain` to check
against configured main and deployed refs. Resolve reported conflicts through
the project's Git workflow; do not renumber applied history.

Use `coloph-migrate --json plan` to inspect pending migrations and checksum
drift against the intended database. It does not execute the SQL. These status
commands can initialize the migration tracking table; they are not strictly
read-only. For a reported failure, use the repair-database-schema skill.

Regenerate with `coloph-migrate snapshot --fresh`, review the resulting SQL,
and commit the migration and snapshot together. This replays migrations in a
disposable database; it does not apply them to the target. Docker is required
for schema dumps, even with a remote test cluster. Use the existing project
test-cluster configuration rather than provisioning infrastructure.

Run `coloph-migrate --json verify` after updating the migration and snapshot.
It is the normal pre-deployment schema check and requires the complete history,
committed snapshot, and intended current target database to agree.

Before deployment, run the project's relevant application tests and configured
`coloph-migrate --json check-backwards`. Inspect its status: `skipped` does not
mean compatibility passed. Its tests exercise deployed code against the final
rebuilt schema, not every intermediate prefix or production data shape. Commit
the changes first: new-migration detection compares Git HEAD with the deployed
ref. Do not treat uncommitted changes as a tested deployment revision.

When old code remains active during migration, deploy code that stops using an
object before a later deployment drops or renames it. The deployed revision,
not merely main, determines when destructive cleanup is ready.

Apply through the project's deployment workflow. Use `coloph-migrate apply`
directly only when the task includes applying to that database. Let package
checks enforce migration rules; do not replace them with checksum scripts or
disable locking. Do not add transaction control to migration SQL: the runner
owns each transaction, and its current text guard does not catch every alias.

Optional snapshot notes start with `-- schema-doc:` immediately before the SQL
statement they describe. Snapshot regeneration preserves them when the next
statement line still matches. They are file comments, not database metadata.
