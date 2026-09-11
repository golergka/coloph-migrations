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
MIGRATION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DEFAULT_MIGRATION_TEMPLATE = "-- Add migration SQL here.\n"


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
    paths = sorted(
        (path for path in directory.glob("*.sql") if MIGRATION_RE.fullmatch(path.name)),
        key=lambda path: int(MIGRATION_RE.fullmatch(path.name).group(1)),  # type: ignore[union-attr]
    )
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
        versions.append(int(version))
        migrations.append(Migration(version, path, text, checksum_sql(text)))

    all_versions = [int(MIGRATION_RE.fullmatch(path.name).group(1)) for path in paths]  # type: ignore[union-attr]
    for previous, current in zip(all_versions, all_versions[1:], strict=False):
        if current != previous + 1:
            raise MigrationError(
                f"Migration sequence gap: {current:04d} follows {previous:04d}; expected {previous + 1:04d}"
            )
    return migrations


def create_migration(directory: Path, name: str, *, template: Path | None = None) -> Path:
    normalized_name = re.sub(r"[\s-]+", "_", name.strip().lower()).strip("_")
    if not MIGRATION_NAME_RE.fullmatch(normalized_name):
        raise MigrationError(
            "Migration name must start with a letter and contain only letters, numbers, spaces, hyphens, or underscores"
        )
    migrations = discover_migrations(directory)
    version = f"{int(migrations[-1].version) + 1:04d}"
    path = directory / f"{version}_{normalized_name}.sql"
    if path.exists():
        raise MigrationError(f"Migration already exists: {path}")
    try:
        contents = template.read_text(encoding="utf-8") if template is not None else DEFAULT_MIGRATION_TEMPLATE
    except OSError as exc:
        raise MigrationError(f"Unable to read migration template {template}: {exc}") from exc
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(contents)
    except FileExistsError as exc:
        raise MigrationError(f"Migration already exists: {path}") from exc
    return path


def _identifier(name: str) -> sql.Identifier:
    if not name or "\x00" in name:
        raise ValueError("Database identifier must be non-empty")
    return sql.Identifier(name)


def _ensure_table(conn: psycopg.Connection, config: Config) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {} (
                    version TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    post_hook_completed BOOLEAN NOT NULL DEFAULT TRUE,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(_identifier(config.migration_table))
        )
        cur.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS post_hook_completed BOOLEAN NOT NULL DEFAULT TRUE").format(
                _identifier(config.migration_table)
            )
        )
    conn.commit()


def _applied(conn: psycopg.Connection, config: Config) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return list(
            cur.execute(
                sql.SQL("SELECT version, filename, checksum, post_hook_completed FROM {} ORDER BY version").format(
                    _identifier(config.migration_table)
                )
            ).fetchall()
        )


def _migration_state(
    conn: psycopg.Connection, config: Config, *, initialize: bool = True
) -> tuple[list[MigrationStatus], list[str]]:
    if initialize:
        _ensure_table(conn, config)
    elif conn.execute("SELECT to_regclass(%s)", (config.migration_table,)).fetchone()[0] is None:
        raise MigrationError(f"Migration tracking table {config.migration_table} does not exist")
    migrations = discover_migrations(config.migrations_dir)
    disk = {item.version: item for item in migrations}
    rows = _applied(conn, config)
    applied = {str(row["version"]): row for row in rows}
    result: list[MigrationStatus] = []
    history_errors: list[str] = []

    for row in rows:
        version = str(row["version"])
        applied_filename = str(row["filename"])
        local = disk.get(version)
        if local is None:
            state = "orphan"
            filename = applied_filename
            history_errors.append(f"version {version} ({applied_filename}): file is missing")
        elif local.filename != applied_filename:
            state = "renamed"
            filename = local.filename
            reason = f"renamed from {applied_filename} to {local.filename}"
            if local.checksum != row["checksum"]:
                reason += "; checksum differs"
            history_errors.append(f"version {version}: {reason}")
        elif local.checksum != row["checksum"]:
            state = "checksum_mismatch"
            filename = local.filename
            history_errors.append(f"version {version} ({local.filename}): checksum differs")
        elif not row["post_hook_completed"]:
            state = "post_hook_incomplete"
            filename = local.filename
        else:
            state = "applied"
            filename = local.filename
        result.append(MigrationStatus(version, filename, str(row["checksum"]), state))

    for migration in migrations:
        if migration.version not in applied:
            result.append(MigrationStatus(migration.version, migration.filename, migration.checksum, "pending"))
    return sorted(result, key=lambda item: int(item.version)), history_errors


def statuses(conn: psycopg.Connection, config: Config) -> list[MigrationStatus]:
    return _migration_state(conn, config)[0]


def check_current(
    conn: psycopg.Connection, config: Config, *, initialize: bool = True
) -> list[MigrationStatus]:
    result, problems = _migration_state(conn, config, initialize=initialize)
    problems.extend(f"version {item.version} ({item.filename}): pending" for item in result if item.status == "pending")
    problems.extend(
        f"version {item.version} ({item.filename}): post-migration hook is incomplete"
        for item in result
        if item.status == "post_hook_incomplete"
    )
    if problems:
        raise MigrationError(f"Migration state is not current: {', '.join(problems)}")
    return result


def plan(conn: psycopg.Connection, config: Config) -> list[MigrationStatus]:
    """Return pending work while preserving the legacy dry-run contract.

    Pending migrations are reported, not rejected. Invalid applied history is
    fatal. The session advisory lock keeps the answer consistent with a
    concurrent apply, matching the old Coloph dry-run behavior.
    """
    _ensure_table(conn, config)
    with conn.cursor() as cur:
        cur.execute("SET lock_timeout = '5s'")
        cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (config.advisory_lock_name,))
    try:
        result, history_errors = _migration_state(conn, config)
        if history_errors:
            detail = ", ".join(history_errors)
            if any("checksum differs" in error for error in history_errors):
                detail += "; run repair-checksums only after proving schema equivalence"
            raise MigrationError(f"Applied migration history is invalid: {detail}")
        return result
    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (config.advisory_lock_name,))
            cur.execute("RESET lock_timeout")
        conn.commit()


def _read_optional(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MigrationError(f"Migration hook SQL file is missing: {path}") from exc


def _positive_attempt_count(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MigrationError(f"{name} must be a positive integer")
    return value


def _run_after_hook(
    conn: psycopg.Connection,
    cur: psycopg.Cursor,
    config: Config,
    after_sql: str,
    migration_version: str | None,
) -> None:
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
            if migration_version is None:
                cur.execute(
                    sql.SQL("UPDATE {} SET post_hook_completed = TRUE WHERE NOT post_hook_completed").format(
                        _identifier(config.migration_table)
                    )
                )
            else:
                cur.execute(
                    sql.SQL("UPDATE {} SET post_hook_completed = TRUE WHERE version = %s").format(
                        _identifier(config.migration_table)
                    ),
                    (migration_version,),
                )
            conn.commit()
            break
        except psycopg.errors.LockNotAvailable:
            conn.rollback()
            if attempt == config.post_max_attempts - 1:
                raise
            time.sleep(config.retry_sleep_seconds)


def _sql_literal(conn: psycopg.Connection, value: object) -> str:
    return sql.Literal(value).as_string(conn)


def _append_reconstruction_hook(statements: list[str], conn: psycopg.Connection, config: Config, after_sql: str) -> None:
    statements.extend(
        [
            "BEGIN;",
            (
                "SELECT set_config('statement_timeout', "
                f"{_sql_literal(conn, f'{config.post_statement_timeout_seconds}s')}, true);"
            ),
            (
                "SELECT set_config('lock_timeout', "
                f"{_sql_literal(conn, f'{config.post_lock_timeout_seconds}s')}, true);"
            ),
            after_sql,
            (
                f"UPDATE {_identifier(config.migration_table).as_string(conn)} "
                "SET post_hook_completed = TRUE WHERE NOT post_hook_completed;"
            ),
            "COMMIT;",
        ]
    )


def _apply_reconstruction_batch(
    conn: psycopg.Connection,
    config: Config,
    migrations: list[Migration],
    before_sql: str | None,
    after_sql: str | None,
) -> list[str]:
    """Apply an isolated rebuild without paying a network round trip per command.

    Every migration remains its own PostgreSQL transaction. ClientCursor uses
    PostgreSQL's simple-query protocol, so the whole ordered script crosses a
    remote test-cluster link once while each explicit COMMIT is still honored.
    """
    applied_names: list[str] = []
    statements: list[str] = []

    for index, migration in enumerate(migrations):
        statements.extend(
            [
                (
                    "SELECT set_config('lock_timeout', "
                    f"{_sql_literal(conn, f'{config.apply_lock_timeout_seconds}s')}, true);"
                ),
                f"SELECT set_config('app.operation_name', {_sql_literal(conn, f'migration.{migration.version}')}, true);",
            ]
        )
        if before_sql:
            statements.append(before_sql)
        statements.extend(
            [
                (
                    "SELECT set_config('statement_timeout', "
                    f"{_sql_literal(conn, f'{config.fresh_statement_timeout_seconds}s')}, true);"
                ),
                migration.sql,
                (
                    f"INSERT INTO {_identifier(config.migration_table).as_string(conn)} "
                    "(version, filename, checksum, post_hook_completed) VALUES "
                    f"({_sql_literal(conn, migration.version)}, {_sql_literal(conn, migration.filename)}, "
                    f"{_sql_literal(conn, migration.checksum)}, {'FALSE' if after_sql else 'TRUE'});"
                ),
                "COMMIT;",
            ]
        )
        applied_names.append(migration.filename)
        if after_sql and migration.version in config.reconstruction_after_hook_versions:
            _append_reconstruction_hook(statements, conn, config, after_sql)
        if index < len(migrations) - 1:
            statements.append("BEGIN;")

    if after_sql and applied_names:
        _append_reconstruction_hook(statements, conn, config, after_sql)

    if statements:
        with psycopg.ClientCursor(conn) as cur:
            cur.execute("\n".join(statements))

    return applied_names


def _incomplete_after_hooks(conn: psycopg.Connection, config: Config) -> list[str]:
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            sql.SQL("SELECT version FROM {} WHERE NOT post_hook_completed ORDER BY version").format(
                _identifier(config.migration_table)
            )
        ).fetchall()
    return [str(row["version"]) for row in rows]


# MIGRATIONS MUST EITHER APPLY COMPLETELY OR CRASH THE RUN.
# NEVER SKIP A FAILED MIGRATION. DO NOT SILENTLY EAT ERRORS.
def apply(
    config: Config,
    *,
    skip_advisory_lock: bool = False,
    up_to: str | None = None,
    reconstruction: bool = False,
    check_transaction_boundaries: bool = False,
) -> dict[str, object]:
    if config.database_url is None:
        raise MigrationError("database_url is required")
    migrations = discover_migrations(config.migrations_dir, up_to=up_to)
    before_sql = _read_optional(config.before_each_migration_sql)
    after_sql = _read_optional(config.after_each_migration_sql)
    apply_max_attempts = _positive_attempt_count("apply_max_attempts", config.apply_max_attempts)
    if after_sql:
        _positive_attempt_count("post_max_attempts", config.post_max_attempts)
    if not reconstruction and not check_transaction_boundaries:
        dry_run(config, up_to=up_to)
    applied_names: list[str] = []

    with psycopg.connect(config.database_url, row_factory=dict_row, prepare_threshold=None) as conn:
        _ensure_table(conn, config)
        with conn.cursor() as cur:
            if not skip_advisory_lock:
                cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (config.advisory_lock_name,))
            rows = _applied(conn, config)
            existing = {str(row["version"]): row for row in rows}

            incomplete_hooks = _incomplete_after_hooks(conn, config)
            if incomplete_hooks:
                if after_sql is None:
                    raise MigrationError(
                        "Post-migration hooks are incomplete, but after_each_migration_sql is not configured"
                    )
                for version in incomplete_hooks:
                    _run_after_hook(conn, cur, config, after_sql, version)

            if reconstruction:
                pending = []
                for migration in migrations:
                    row = existing.get(migration.version)
                    if row is not None:
                        if row["checksum"] != migration.checksum:
                            raise MigrationError(
                                f"Applied migration {migration.version} differs from {migration.filename}; "
                                "run repair-checksums only after proving schema equivalence"
                            )
                        continue
                    pending.append(migration)
                applied_names = _apply_reconstruction_batch(conn, config, pending, before_sql, after_sql)
                if not skip_advisory_lock:
                    cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (config.advisory_lock_name,))
                    conn.commit()
                return {
                    "applied": applied_names,
                    "applied_count": len(applied_names),
                }

            for migration in migrations:
                row = existing.get(migration.version)
                if row is not None:
                    if row["checksum"] != migration.checksum:
                        raise MigrationError(
                            f"Applied migration {migration.version} differs from {migration.filename}; "
                            "run repair-checksums only after proving schema equivalence"
                        )
                    continue

                for attempt in range(apply_max_attempts):
                    try:
                        cur.execute(
                            "SELECT set_config('lock_timeout', %s, true)", (f"{config.apply_lock_timeout_seconds}s",)
                        )
                        cur.execute(
                            "SELECT set_config('app.operation_name', %s, true)", (f"migration.{migration.version}",)
                        )
                        if before_sql:
                            cur.execute(before_sql)
                        if check_transaction_boundaries:
                            transaction_id = cur.execute("SELECT pg_current_xact_id()").fetchone()[0]
                        cur.execute(migration.sql)
                        if check_transaction_boundaries:
                            after_transaction_id = cur.execute("SELECT pg_current_xact_id()").fetchone()[0]
                            if after_transaction_id != transaction_id:
                                raise MigrationError(
                                    f"Migration {migration.filename} changed its transaction "
                                    f"({transaction_id} to {after_transaction_id})"
                                )
                        cur.execute(
                            sql.SQL(
                                "INSERT INTO {} (version, filename, checksum, post_hook_completed) VALUES (%s, %s, %s, %s)"
                            ).format(
                                _identifier(config.migration_table)
                            ),
                            (migration.version, migration.filename, migration.checksum, after_sql is None),
                        )
                        conn.commit()
                        break
                    except psycopg.errors.LockNotAvailable:
                        conn.rollback()
                        if attempt == apply_max_attempts - 1:
                            raise
                        time.sleep(config.retry_sleep_seconds)

                if after_sql:
                    _run_after_hook(conn, cur, config, after_sql, migration.version)
                applied_names.append(migration.filename)

            if not skip_advisory_lock:
                cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (config.advisory_lock_name,))
            conn.commit()
    return {
        "applied": applied_names,
        "applied_count": len(applied_names),
    }


def dry_run(config: Config, *, up_to: str | None = None) -> dict[str, object]:
    from dataclasses import replace

    from .test_database import temporary_database

    with temporary_database(config) as database_url:
        return apply(
            replace(config, database_url=database_url),
            skip_advisory_lock=True,
            up_to=up_to,
            check_transaction_boundaries=True,
        )


def apply_to_database(config: Config, database_url: str, *, up_to: str | None = None) -> dict[str, object]:
    from dataclasses import replace

    return apply(
        replace(config, database_url=database_url),
        skip_advisory_lock=True,
        up_to=up_to,
        reconstruction=True,
    )
