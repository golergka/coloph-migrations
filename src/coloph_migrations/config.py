from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
import tomllib


DEFAULT_CONFIG_NAME = "coloph-migrations.toml"
LOCAL_CONFIG_NAME = "coloph-migrations.local.toml"


@dataclass(frozen=True)
class Config:
    root: Path
    migrations_dir: Path
    schema_snapshot: Path
    database_url: str | None = None
    before_each_migration_sql: Path | None = None
    after_each_migration_sql: Path | None = None
    main_ref: str = "main"
    deployed_ref: str = "deployed"
    deployed_fetch_remote: str | None = None
    postgres_image: str = "pgvector/pgvector:pg17"
    migration_table: str = "schema_migrations"
    advisory_lock_name: str = "schema_migrations"
    legacy_migration_table: str | None = None
    apply_lock_timeout_seconds: int = 2
    apply_max_attempts: int = 3
    post_lock_timeout_seconds: int = 10
    post_statement_timeout_seconds: int = 30
    post_max_attempts: int = 5
    retry_sleep_seconds: float = 2
    concurrent_ddl_retry_versions: tuple[str, ...] = ()
    concurrent_ddl_retry_message: str = "tuple concurrently updated"
    concurrent_ddl_max_attempts: int = 5
    concurrent_ddl_retry_sleep_seconds: float = 0.2
    exclude_index_patterns: tuple[str, ...] = ()
    schema_header: str = ""
    fresh_skip_feature_not_supported: bool = False
    fresh_statement_timeout_seconds: int = 90
    fresh_vacuum_after_each_migration: bool = False
    backwards_test_command: tuple[str, ...] = ()
    backwards_setup_command: tuple[str, ...] = ()
    backwards_test_globs: tuple[str, ...] = ()
    backwards_test_args: tuple[str, ...] = ()
    backwards_database_url_env: str = "TEST_DATABASE_URL"
    backwards_bootstrap_file: Path | None = None
    backwards_bootstrap_marker: str | None = None


_PATH_FIELDS = {
    "migrations_dir",
    "schema_snapshot",
    "before_each_migration_sql",
    "after_each_migration_sql",
    "backwards_bootstrap_file",
}
_TUPLE_FIELDS = {
    "exclude_index_patterns",
    "concurrent_ddl_retry_versions",
    "backwards_test_command",
    "backwards_setup_command",
    "backwards_test_globs",
    "backwards_test_args",
}


def _read_toml(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration must be a TOML table: {path}")
    return raw


def _resolve_path(root: Path, value: object | None) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Path configuration values must be non-empty strings")
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def load_config(path: Path | None = None) -> Config:
    explicit = path.resolve() if path is not None else None
    root = explicit.parent if explicit is not None else Path.cwd().resolve()
    base_path = explicit or root / DEFAULT_CONFIG_NAME
    raw = _read_toml(base_path)
    local_path = root / LOCAL_CONFIG_NAME
    if local_path != base_path:
        raw.update(_read_toml(local_path))

    known = {field.name for field in fields(Config)} - {"root"}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ValueError(f"Unknown configuration keys: {', '.join(unknown)}")

    migrations_dir = _resolve_path(root, raw.pop("migrations_dir", "migrations"))
    schema_snapshot = _resolve_path(root, raw.pop("schema_snapshot", "migrations/schema.sql"))
    assert migrations_dir is not None
    assert schema_snapshot is not None

    values: dict[str, object] = {
        "root": root,
        "migrations_dir": migrations_dir,
        "schema_snapshot": schema_snapshot,
    }
    for name, value in raw.items():
        if name in _PATH_FIELDS:
            values[name] = _resolve_path(root, value)
        elif name in _TUPLE_FIELDS:
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be an array of strings")
            values[name] = tuple(value)
        else:
            values[name] = value
    return Config(**values)


def override_config(
    config: Config,
    *,
    database_url: str | None = None,
    migrations_dir: Path | None = None,
    schema_snapshot: Path | None = None,
) -> Config:
    changes: dict[str, object] = {}
    if database_url is not None:
        changes["database_url"] = database_url
    if migrations_dir is not None:
        changes["migrations_dir"] = migrations_dir.resolve()
    if schema_snapshot is not None:
        changes["schema_snapshot"] = schema_snapshot.resolve()
    return replace(config, **changes)
