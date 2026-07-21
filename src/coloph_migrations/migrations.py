from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import time
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import Config


MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")
TRANSACTION_CONTROL_RE = re.compile(r"^\s*(BEGIN|COMMIT|ROLLBACK)\s*;", re.MULTILINE | re.IGNORECASE)


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: str
    path: Path
    sql: str
    checksum: str

    @property
    def filename(self) -> str:
        return self.path.name


@dataclass(frozen=True)
class MigrationStatus:
    version: str
    filename: str
    checksum: str
    status: str


def checksum_sql(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def discover_migrations(directory: Path, *, up_to: str | None = None) -> list[Migration]:
    paths = sorted(path for path in directory.glob("*.sql") if MIGRATION_RE.fullmatch(path.name))
    if not paths:
        raise MigrationError(f"No numbered SQL migrations found in {directory}")

    migrations: list[Migration] = []
    versions: list[int] = []
    for path in paths:
        match = MIGRATION_RE.fullmatch(path.name)
        assert match is not None
        version = match.group(1)
        if up_to is not None and int(version) >= int(up_to):
            continue
        text = path.read_text(encoding="utf-8")
        tx_match = TRANSACTION_CONTROL_RE.search(text)
        if tx_match:
            raise MigrationError(
                f"Migration {path.name} contains explicit {tx_match.group(1).upper()} transaction control"
            )
        versions.append(int(version))
        migrations.append(Migration(version, path, text, checksum_sql(text)))

    all_versions = [int(MIGRATION_RE.fullmatch(path.name).group(1)) for path in paths]  # type: ignore[union-attr]
    for previous, current in zip(all_versions, all_versions[1:], strict=False):
        if current != previous + 1:
            raise MigrationError(
                f"Migration sequence gap: {current:04d} follows {previous:04d}; expected {previous + 1:04d}"
            )
    return migrations


def _identifier(name: str) -> sql.Identifier:
    if not name or "\x00" in name:
        raise ValueError("Database identifier must be non-empty")
    return sql.Identifier(name)


def _ensure_table(conn: psycopg.Connection, config: Config) -> None:
    with conn.cursor() as cur:
        if config.legacy_migration_table:
            cur.execute(
                "SELECT to_regclass(%s), to_regclass(%s)",
                (config.legacy_migration_table, config.migration_table),
            )
            legacy, current = cur.fetchone()
            if legacy is not None and current is None:
                cur.execute(
                    sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                        _identifier(config.legacy_migration_table),
                        _identifier(config.migration_table),
                    )
                )
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    version TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(_identifier(config.migration_table))
        )
    conn.commit()


def _applied(conn: psycopg.Connection, config: Config) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return list(
            cur.execute(
                sql.SQL("SELECT version, filename, checksum FROM {} ORDER BY version").format(
                    _identifier(config.migration_table)
                )
            ).fetchall()
        )


def statuses(conn: psycopg.Connection, config: Config) -> list[MigrationStatus]:
    _ensure_table(conn, config)
    migrations = discover_migrations(config.migrations_dir)
    disk = {item.version: item for item in migrations}
    rows = _applied(conn, config)
    applied = {str(row["version"]): row for row in rows}
    result: list[MigrationStatus] = []

    for row in rows:
        version = str(row["version"])
        local = disk.get(version)
        if local is None:
            state = "orphan"
            filename = str(row["filename"])
        elif local.filename != row["filename"]:
            state = "renamed"
            filename = local.filename
        elif local.checksum != row["checksum"]:
            state = "checksum_mismatch"
            filename = local.filename
        else:
            state = "applied"
            filename = local.filename
        result.append(MigrationStatus(version, filename, str(row["checksum"]), state))

    for migration in migrations:
        if migration.version not in applied:
            result.append(MigrationStatus(migration.version, migration.filename, migration.checksum, "pending"))
    return sorted(result, key=lambda item: int(item.version))


def check_current(conn: psycopg.Connection, config: Config) -> list[MigrationStatus]:
    result = statuses(conn, config)
    problems = [item for item in result if item.status in {"pending", "checksum_mismatch"}]
    if problems:
        detail = ", ".join(f"{item.filename}: {item.status}" for item in problems)
        raise MigrationError(f"Migration state is not current: {detail}")
    return result


def plan(conn: psycopg.Connection, config: Config) -> list[MigrationStatus]:
    """Return pending work while preserving the legacy dry-run contract.

    Pending migrations are reported, not rejected. Applied checksum drift is
    fatal. The session advisory lock keeps the answer consistent with a
    concurrent apply, matching the old Coloph dry-run behavior.
    """
    _ensure_table(conn, config)
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout = '5s'")
        cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (config.advisory_lock_name,))
    try:
        result = statuses(conn, config)
        mismatches = [item for item in result if item.status == "checksum_mismatch"]
        if mismatches:
            detail = ", ".join(item.filename for item in mismatches)
            raise MigrationError(
                f"Applied migration checksum mismatch: {detail}; "
                "run repair-checksums only after proving schema equivalence"
            )
        return result
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (config.advisory_lock_name,))
            cur.execute("RESET lock_timeout")
        conn.commit()


def _read_optional(path: Path | None) -> str | None:
    return path.read_text(encoding="utf-8") if path is not None else None


def _run_after_hook(conn: psycopg.Connection, cur: psycopg.Cursor, config: Config, after_sql: str) -> None:
    for attempt in range(config.post_max_attempts):
        try:
            cur.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (f"{config.post_statement_timeout_seconds}s",),
            )
            cur.execute(
                "SELECT set_config('lock_timeout', %s, true)",
                (f"{config.post_lock_timeout_seconds}s",),
            )
            cur.execute(after_sql)
            conn.commit()
            break
        except psycopg.errors.LockNotAvailable:
            conn.rollback()
            if attempt == config.post_max_attempts - 1:
                raise
            time.sleep(config.retry_sleep_seconds)


def apply(
    config: Config,
    *,
    skip_advisory_lock: bool = False,
    up_to: str | None = None,
    reconstruction: bool = False,
) -> dict[str, object]:
    if config.database_url is None:
        raise MigrationError("database_url is required")
    migrations = discover_migrations(config.migrations_dir, up_to=up_to)
    before_sql = _read_optional(config.before_each_migration_sql)
    after_sql = _read_optional(config.after_each_migration_sql)
    applied_names: list[str] = []
    skipped_names: list[str] = []

    with psycopg.connect(config.database_url, row_factory=dict_row, prepare_threshold=None) as conn:
        _ensure_table(conn, config)
        with conn.cursor() as cur:
            if not skip_advisory_lock:
                cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (config.advisory_lock_name,))
            rows = _applied(conn, config)
            existing = {str(row["version"]): row for row in rows}

            for migration in migrations:
                row = existing.get(migration.version)
                if row is not None:
                    if row["checksum"] != migration.checksum:
                        raise MigrationError(
                            f"Applied migration {migration.version} differs from {migration.filename}; "
                            "run repair-checksums only after proving schema equivalence"
                        )
                    continue

                max_attempts = (
                    config.concurrent_ddl_max_attempts
                    if reconstruction and migration.version in config.concurrent_ddl_retry_versions
                    else config.apply_max_attempts
                )
                for attempt in range(max_attempts):
                    try:
                        cur.execute(
                            "SELECT set_config('lock_timeout', %s, true)", (f"{config.apply_lock_timeout_seconds}s",)
                        )
                        cur.execute(
                            "SELECT set_config('app.operation_name', %s, true)", (f"migration.{migration.version}",)
                        )
                        if before_sql:
                            cur.execute(before_sql)
                        if reconstruction:
                            cur.execute(
                                "SELECT set_config('statement_timeout', %s, true)",
                                (f"{config.fresh_statement_timeout_seconds}s",),
                            )
                        cur.execute(migration.sql)
                        cur.execute(
                            sql.SQL("INSERT INTO {} (version, filename, checksum) VALUES (%s, %s, %s)").format(
                                _identifier(config.migration_table)
                            ),
                            (migration.version, migration.filename, migration.checksum),
                        )
                        conn.commit()
                        break
                    except psycopg.errors.LockNotAvailable:
                        conn.rollback()
                        if attempt == max_attempts - 1:
                            raise
                        time.sleep(config.retry_sleep_seconds)
                    except psycopg.errors.InternalError_ as exc:
                        message = getattr(exc.diag, "message_primary", "") or str(exc)
                        if (
                            not reconstruction
                            or migration.version not in config.concurrent_ddl_retry_versions
                            or config.concurrent_ddl_retry_message not in message
                        ):
                            raise
                        conn.rollback()
                        if attempt == max_attempts - 1:
                            raise
                        time.sleep(config.concurrent_ddl_retry_sleep_seconds * (attempt + 1))
                    except psycopg.errors.FeatureNotSupported:
                        if not (reconstruction and config.fresh_skip_feature_not_supported):
                            raise
                        conn.rollback()
                        cur.execute(
                            sql.SQL("INSERT INTO {} (version, filename, checksum) VALUES (%s, %s, %s)").format(
                                _identifier(config.migration_table)
                            ),
                            (migration.version, migration.filename, migration.checksum),
                        )
                        conn.commit()
                        skipped_names.append(migration.filename)
                        break

                if migration.filename in skipped_names:
                    continue

                if after_sql and not reconstruction:
                    _run_after_hook(conn, cur, config, after_sql)
                applied_names.append(migration.filename)

                if reconstruction and config.fresh_vacuum_after_each_migration:
                    conn.autocommit = True
                    try:
                        cur.execute("VACUUM")
                    finally:
                        conn.autocommit = False

            if after_sql and reconstruction and (applied_names or skipped_names):
                _run_after_hook(conn, cur, config, after_sql)

            if not skip_advisory_lock:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (config.advisory_lock_name,))
            conn.commit()
    return {
        "applied": applied_names,
        "applied_count": len(applied_names),
        "skipped": skipped_names,
        "skipped_count": len(skipped_names),
    }


def apply_to_database(config: Config, database_url: str, *, up_to: str | None = None) -> dict[str, object]:
    from dataclasses import replace

    return apply(
        replace(config, database_url=database_url),
        skip_advisory_lock=True,
        up_to=up_to,
        reconstruction=True,
    )
