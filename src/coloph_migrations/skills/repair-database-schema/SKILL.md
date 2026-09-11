---
name: repair-database-schema
description: Diagnose failed database migrations, changed migration checksums, or a database schema that differs from its migration history. Use to recover a broken schema change; ordinary pending migrations and unrelated data cleanup are not repair tasks.
---

# Repair database schema

Use the project's pinned CLI through `uv run coloph-migrate`. Read `coloph-migrations.toml`
and project operating rules. Identify the intended database and deployed Git
revision before interpreting local files. A stale branch can explain a
mismatch; it is not the only possible cause. Do not print credentials.

Run `uv run coloph-migrate --json list` and `uv run coloph-migrate --json plan` from the
configuration directory. Global options go before the command. Status commands
can initialize the tracking table. `plan` and `check` reject invalid applied
history, including missing and renamed migration files.

- Only `pending`: use the normal deployment path. Do not repair checksums.
- `orphan` or `renamed`: reconcile local files with the deployed history before
  applying anything. Do not delete migration records to suppress the report.
- `checksum_mismatch`: establish which applied file changed. Prefer restoring
  applied history and adding a new migration. Never update checksums directly.
- SQL failure: inspect the first error and recorded state before retrying.
  Earlier migrations stay committed. `apply` first checks transaction boundaries
  in a disposable database, so inspect that result before target recovery.
- After-hook failure: the migration already committed. A later `apply` can
  retry its recorded incomplete hook. Keep the hook SQL safe to retry, then run
  `apply` again and verify the final schema.

Use `uv run coloph-migrate --json validate --match-applied` only as a repair diagnostic
to compare the target schema with a reconstruction through the highest recorded
version. Normal pre-deployment verification uses `uv run coloph-migrate --json verify`,
which requires the full history, committed snapshot, and target to agree.

For a specific failing version, write diagnostic dumps to separate files:

```sh
uv run coloph-migrate --schema-snapshot /tmp/schema-target.sql snapshot
uv run coloph-migrate --schema-snapshot /tmp/schema-before.sql snapshot --fresh --up-to NNNN
diff -u /tmp/schema-before.sql /tmp/schema-target.sql
```

Replace `NNNN` with the version. The boundary is exclusive. Differences can
include expected later migrations; a diff alone does not establish corruption.
Fresh reconstruction and schema comparison require Docker for dumps and the
project's configured disposable database environment.

For an intentional, justified edit of applied history, preview with
`uv run coloph-migrate --json repair-checksums --dry-run`. It compares the target with
the full reconstructed chain before permitting checksum updates. Schema
equality does not prove that changed data transformations are equivalent.
Resolve that question and coordinate with the project's deployment owner
before an authorized `repair-checksums` run. If schemas differ, stop and
diagnose the diff; do not bypass the check.

After recovery, repeat `list`, `plan`, and `validate --match-applied`. Report
remaining pending work separately from the repaired failure.
