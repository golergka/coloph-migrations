from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from coloph_migrations.config import Config
from coloph_migrations.migrations import MigrationError, apply, discover_migrations, statuses
from coloph_migrations.repair import repair_checksums
from coloph_migrations.schema import validate


def _config(tmp_path: Path, database_url: str, **changes) -> Config:
    migrations = tmp_path / "migrations"
    migrations.mkdir(exist_ok=True)
    base = Config(
        root=tmp_path, migrations_dir=migrations, schema_snapshot=migrations / "schema.sql", database_url=database_url
    )
    return replace(base, **changes)


def _write(config: Config, name: str, body: str) -> Path:
    path = config.migrations_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def _regclass(database_url: str, name: str):
    with psycopg.connect(database_url) as conn:
        return conn.execute("SELECT to_regclass(%s)", (name,)).fetchone()[0]


def test_gap_and_explicit_transaction_control_fail_before_connecting(tmp_path: Path) -> None:
    config = _config(tmp_path, "postgresql://unused")
    _write(config, "0001_first.sql", "SELECT 1;\n")
    _write(config, "0003_gap.sql", "SELECT 3;\n")
    with pytest.raises(MigrationError, match="sequence gap"):
        discover_migrations(config.migrations_dir)

    (config.migrations_dir / "0003_gap.sql").unlink()
    _write(config, "0002_bad.sql", "BEGIN;\nSELECT 2;\n")
    with pytest.raises(MigrationError, match="explicit BEGIN"):
        discover_migrations(config.migrations_dir)


def test_migration_error_rolls_back_body_and_history(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_broken.sql", "CREATE TABLE should_rollback(id integer);\nSELECT missing_column;\n")
    with pytest.raises(psycopg.errors.UndefinedColumn):
        apply(config)

    assert _regclass(database_url, "should_rollback") is None
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 0


def test_checksum_drift_fails_loud(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    migration = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    migration.write_text("CREATE TABLE widgets(id bigint);\n", encoding="utf-8")

    with pytest.raises(MigrationError, match="differs"):
        apply(config)
    assert statuses(psycopg.connect(database_url), config)[0].status == "checksum_mismatch"


def test_before_hook_failure_rolls_back_migration(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    before = tmp_path / "before.sql"
    before.write_text("SELECT missing_column;\n", encoding="utf-8")
    config = replace(config, before_each_migration_sql=before)

    with pytest.raises(psycopg.errors.UndefinedColumn):
        apply(config)
    assert _regclass(database_url, "widgets") is None


def test_after_hook_failure_keeps_committed_migration_but_rolls_back_hook(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    after = tmp_path / "after.sql"
    after.write_text("CREATE TABLE hook_should_rollback(id integer);\nSELECT 1 / 0;\n", encoding="utf-8")
    config = replace(config, after_each_migration_sql=after)

    with pytest.raises(psycopg.errors.DivisionByZero):
        apply(config)

    assert _regclass(database_url, "widgets") == "widgets"
    assert _regclass(database_url, "hook_should_rollback") is None
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 1


def test_validate_detects_schema_drift(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    with psycopg.connect(database_url) as conn:
        conn.execute("ALTER TABLE widgets ADD COLUMN drift text")
        conn.commit()

    result = validate(config)
    assert result["identical"] is False
    assert "drift" in result["diff"]


def test_checksum_repair_requires_schema_equivalence(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    migration = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)

    migration.write_text("-- harmless edit\nCREATE TABLE widgets(id integer);\n", encoding="utf-8")
    repaired = repair_checksums(config)
    assert repaired["repaired"] == ["0001_widgets.sql"]

    migration.write_text("CREATE TABLE widgets(id integer, divergent text);\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="schemas differ"):
        repair_checksums(config)
