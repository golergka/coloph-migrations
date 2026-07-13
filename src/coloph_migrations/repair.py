from __future__ import annotations

import difflib

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import Config
from .migrations import MigrationError, _identifier, discover_migrations
from .schema import canonical_schema, detect_server_version
from .test_database import temporary_database
from .migrations import apply_to_database


def repair_checksums(config: Config, *, dry_run: bool = False) -> dict:
    if config.database_url is None:
        raise MigrationError("database_url is required")
    migrations = {item.version: item for item in discover_migrations(config.migrations_dir)}
    with psycopg.connect(config.database_url, row_factory=dict_row) as conn:
        rows = conn.execute(
            sql.SQL("SELECT version, filename, checksum FROM {} ORDER BY version").format(
                _identifier(config.migration_table)
            )
        ).fetchall()
    mismatches = [
        (str(row["version"]), migrations[str(row["version"])])
        for row in rows
        if str(row["version"]) in migrations and row["checksum"] != migrations[str(row["version"])].checksum
    ]
    if not mismatches:
        return {"repaired": [], "dry_run": dry_run}

    version = detect_server_version(config.database_url)
    with temporary_database(config) as test_url:
        apply_to_database(config, test_url)
        rebuilt = canonical_schema(config, test_url)
        target = canonical_schema(config, config.database_url)
    if rebuilt != target:
        diff = "".join(difflib.unified_diff(target.splitlines(True), rebuilt.splitlines(True), "target", "rebuilt"))
        raise MigrationError(f"Refusing checksum repair because schemas differ:\n{diff}")

    repaired = [migration.filename for _, migration in mismatches]
    if not dry_run:
        with psycopg.connect(config.database_url) as conn:
            for migration_version, migration in mismatches:
                conn.execute(
                    sql.SQL("UPDATE {} SET checksum = %s WHERE version = %s").format(
                        _identifier(config.migration_table)
                    ),
                    (migration.checksum, migration_version),
                )
            conn.commit()
    return {"repaired": repaired, "dry_run": dry_run, "postgres_version": version}
