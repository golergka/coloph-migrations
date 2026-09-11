from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from coloph_migrations.config import Config
from coloph_migrations.migrations import MigrationError, apply, check_current, discover_migrations, dry_run, plan, statuses
from coloph_migrations.repair import repair_checksums
from coloph_migrations.schema import canonical_schema, validate, verify


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


def test_gap_fails_before_connecting(tmp_path: Path) -> None:
    config = _config(tmp_path, "postgresql://unused")
    _write(config, "0001_first.sql", "SELECT 1;\n")
    _write(config, "0003_gap.sql", "SELECT 3;\n")
    with pytest.raises(MigrationError, match="sequence gap"):
        discover_migrations(config.migrations_dir)



@pytest.mark.parametrize("transaction_command", ["END;", "ABORT;", "COMMIT AND CHAIN;"])
def test_dry_run_rejects_transaction_control_without_changing_target(
    tmp_path: Path, database_url: str, transaction_command: str
) -> None:
    config = _config(tmp_path, database_url)
    _write(
        config,
        "0001_transaction_alias.sql",
        f"CREATE TABLE alias_committed(id integer);\n{transaction_command}\n",
    )

    with pytest.raises(MigrationError, match=r"0001_transaction_alias.sql changed its transaction"):
        dry_run(config)
    assert _regclass(database_url, "alias_committed") is None
    assert _regclass(database_url, "schema_migrations") is None


def test_dry_run_allows_transaction_keywords_in_quoted_plpgsql(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(
        config,
        "0001_function.sql",
        "CREATE FUNCTION noop() RETURNS text LANGUAGE plpgsql AS $$ BEGIN RETURN 'END; ABORT;'; END; $$;\n",
    )

    assert dry_run(config)["applied"] == ["0001_function.sql"]
    assert _regclass(database_url, "noop") is None


def test_apply_dry_run_failure_does_not_change_target(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_transaction_alias.sql", "CREATE TABLE committed(id integer);\nABORT;\n")

    with pytest.raises(MigrationError, match=r"0001_transaction_alias.sql changed its transaction"):
        apply(config)
    assert _regclass(database_url, "committed") is None
    assert _regclass(database_url, "schema_migrations") is None


def test_migration_error_rolls_back_body_and_history(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_broken.sql", "CREATE TABLE should_rollback(id integer);\nSELECT missing_column;\n")
    with pytest.raises(psycopg.errors.UndefinedColumn):
        apply(config)

    assert _regclass(database_url, "should_rollback") is None
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None


def test_apply_result_has_no_skipped_migration_contract(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")

    assert apply(config) == {"applied": ["0001_widgets.sql"], "applied_count": 1}


def test_checksum_drift_fails_loud(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    migration = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    migration.write_text("CREATE TABLE widgets(id bigint);\n", encoding="utf-8")

    with pytest.raises(MigrationError, match="differs"):
        apply(config)
    with psycopg.connect(database_url) as conn:
        assert statuses(conn, config)[0].status == "checksum_mismatch"


def test_apply_rejects_zero_attempts_before_changing_database(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url, apply_max_attempts=0)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")

    with pytest.raises(MigrationError, match="apply_max_attempts must be a positive integer"):
        apply(config)

    assert _regclass(database_url, "widgets") is None
    assert _regclass(database_url, "schema_migrations") is None


def test_plan_reports_pending_but_fails_checksum_drift_and_releases_lock(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    migration = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    _write(config, "0002_pending.sql", "CREATE TABLE pending(id integer);\n")

    with psycopg.connect(database_url) as conn:
        assert [item.status for item in plan(conn, config)] == ["applied", "pending"]

    migration.write_text("CREATE TABLE widgets(id bigint);\n", encoding="utf-8")
    with psycopg.connect(database_url) as conn:
        with pytest.raises(MigrationError, match="checksum differs"):
            plan(conn, config)
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (config.advisory_lock_name,)).fetchone()[0]
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (config.advisory_lock_name,))


@pytest.mark.parametrize("history_check", [check_current, plan])
def test_history_checks_reject_renamed_migration(tmp_path: Path, database_url: str, history_check) -> None:
    config = _config(tmp_path, database_url)
    migration = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    migration.rename(config.migrations_dir / "0001_renamed.sql")

    with psycopg.connect(database_url) as conn:
        with pytest.raises(MigrationError, match=r"version 0001.*renamed from 0001_widgets\.sql to 0001_renamed\.sql"):
            history_check(conn, config)


@pytest.mark.parametrize("history_check", [check_current, plan])
def test_history_checks_reject_rename_with_checksum_drift(tmp_path: Path, database_url: str, history_check) -> None:
    config = _config(tmp_path, database_url)
    migration = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    migration.rename(config.migrations_dir / "0001_renamed.sql")
    (config.migrations_dir / "0001_renamed.sql").write_text("CREATE TABLE widgets(id bigint);\n", encoding="utf-8")

    with psycopg.connect(database_url) as conn:
        with pytest.raises(MigrationError, match=r"version 0001.*renamed.*checksum differs"):
            history_check(conn, config)


@pytest.mark.parametrize("history_check", [check_current, plan])
def test_history_checks_reject_orphaned_migration(tmp_path: Path, database_url: str, history_check) -> None:
    config = _config(tmp_path, database_url)
    first = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    _write(config, "0002_valid.sql", "SELECT 2;\n")
    apply(config)
    first.unlink()

    with psycopg.connect(database_url) as conn:
        with pytest.raises(MigrationError, match=r"version 0001 \(0001_widgets\.sql\): file is missing"):
            history_check(conn, config)


def test_before_hook_failure_rolls_back_migration(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    before = tmp_path / "before.sql"
    before.write_text("SELECT missing_column;\n", encoding="utf-8")
    config = replace(config, before_each_migration_sql=before)

    with pytest.raises(psycopg.errors.UndefinedColumn):
        apply(config)
    assert _regclass(database_url, "widgets") is None


def test_after_hook_dry_run_failure_does_not_change_target(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    after = tmp_path / "after.sql"
    after.write_text("CREATE TABLE hook_should_rollback(id integer);\nSELECT 1 / 0;\n", encoding="utf-8")
    config = replace(config, after_each_migration_sql=after)

    with pytest.raises(psycopg.errors.DivisionByZero):
        apply(config)

    assert _regclass(database_url, "widgets") is None
    assert _regclass(database_url, "hook_should_rollback") is None
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0] is None


def test_apply_retries_an_incomplete_after_hook_before_reporting_success(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    after = tmp_path / "after.sql"
    after.write_text("SELECT 1 / 0;\n", encoding="utf-8")
    config = replace(config, after_each_migration_sql=after)

    with pytest.raises(psycopg.errors.DivisionByZero):
        apply(config, check_transaction_boundaries=True)

    after.write_text("CREATE TABLE hook_completed(id integer);\n", encoding="utf-8")
    assert apply(config, check_transaction_boundaries=True)["applied_count"] == 0

    assert _regclass(database_url, "widgets") == "widgets"
    assert _regclass(database_url, "hook_completed") == "hook_completed"
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT post_hook_completed FROM schema_migrations").fetchone()[0] is True


def test_apply_fails_when_an_incomplete_after_hook_file_is_missing(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    after = tmp_path / "after.sql"
    after.write_text("SELECT 1 / 0;\n", encoding="utf-8")
    config = replace(config, after_each_migration_sql=after)

    with pytest.raises(psycopg.errors.DivisionByZero):
        apply(config, check_transaction_boundaries=True)
    after.unlink()

    with pytest.raises(MigrationError, match="hook SQL file is missing"):
        apply(config, check_transaction_boundaries=True)


def test_history_table_adds_hook_state_without_a_user_migration(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, filename TEXT NOT NULL, "
            "checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
        )
        conn.commit()

    apply(config)

    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_name = 'schema_migrations' AND column_name = 'post_hook_completed'"
        ).fetchone() == ("NO", "true")


def test_after_hook_runs_after_each_migration_for_normal_apply(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_hook_runs.sql", "CREATE TABLE hook_runs(id bigserial PRIMARY KEY);\n")
    _write(config, "0002_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    after = tmp_path / "after.sql"
    after.write_text("INSERT INTO hook_runs DEFAULT VALUES;\n", encoding="utf-8")
    config = replace(config, after_each_migration_sql=after)

    apply(config)

    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM hook_runs").fetchone()[0] == 2


def test_reconstruction_after_hook_runs_once_after_selected_schema(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_hook_runs.sql", "CREATE TABLE hook_runs(id bigserial PRIMARY KEY);\n")
    _write(config, "0002_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    after = tmp_path / "after.sql"
    after.write_text(
        """
DO $$
BEGIN
    IF to_regclass('widgets') IS NULL THEN
        RAISE EXCEPTION 'final schema not visible';
    END IF;
    INSERT INTO hook_runs DEFAULT VALUES;
END
$$;
""",
        encoding="utf-8",
    )
    config = replace(config, after_each_migration_sql=after)

    apply(config, reconstruction=True)

    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT count(*) FROM hook_runs").fetchone()[0] == 1


def test_reconstruction_after_hook_can_run_at_configured_checkpoint(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer PRIMARY KEY);\n")
    _write(
        config,
        "0002_requires_checkpoint.sql",
        "INSERT INTO widgets(id, hook_marker) VALUES (1, 'checkpoint');\n",
    )
    after = tmp_path / "after.sql"
    after.write_text("ALTER TABLE widgets ADD COLUMN IF NOT EXISTS hook_marker text;\n", encoding="utf-8")
    config = replace(
        config,
        after_each_migration_sql=after,
        reconstruction_after_hook_versions=("0001",),
    )

    apply(config, reconstruction=True)

    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT hook_marker FROM widgets WHERE id = 1").fetchone()[0] == "checkpoint"


def test_reconstruction_preserves_committed_predecessors_on_later_failure(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    _write(config, "0002_broken.sql", "SELECT missing_column;\n")

    with pytest.raises(psycopg.errors.UndefinedColumn):
        apply(config, reconstruction=True)

    assert _regclass(database_url, "widgets") == "widgets"
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [("0001",)]


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


def test_verify_accepts_matching_schemas_and_schema_docs(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    schema = canonical_schema(config, database_url)
    config.schema_snapshot.write_text("-- schema-doc: owner: platform\n" + schema, encoding="utf-8")
    with psycopg.connect(database_url) as conn:
        history_before = conn.execute("SELECT version, filename, checksum FROM schema_migrations").fetchall()

    result = verify(config)

    assert result["identical"] is True
    assert result["snapshot_identical"] is True
    assert result["target_identical"] is True
    with psycopg.connect(database_url) as conn:
        assert conn.execute("SELECT version, filename, checksum FROM schema_migrations").fetchall() == history_before


def test_verify_reports_snapshot_and_target_differences(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    config.schema_snapshot.write_text("CREATE TABLE stale(id integer);\n", encoding="utf-8")
    with psycopg.connect(database_url) as conn:
        conn.execute("ALTER TABLE widgets ADD COLUMN drift text")
        conn.commit()

    result = verify(config)

    assert result["identical"] is False
    assert result["snapshot_identical"] is False
    assert result["target_identical"] is False
    assert "--- snapshot" in result["snapshot_diff"]
    assert "stale" in result["snapshot_diff"]
    assert "--- target" in result["target_diff"]
    assert "drift" in result["target_diff"]


def test_verify_missing_snapshot_fails_without_creating_it(tmp_path: Path, database_url: str) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)

    result = verify(config)

    assert result["identical"] is False
    assert result["snapshot_exists"] is False
    assert "+++ rebuilt" in result["snapshot_diff"]
    assert not config.schema_snapshot.exists()


def test_verify_rejects_pending_history_before_reconstruction(tmp_path: Path, database_url: str, monkeypatch) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    apply(config)
    _write(config, "0002_pending.sql", "CREATE TABLE pending(id integer);\n")
    monkeypatch.setattr(
        "coloph_migrations.schema.temporary_database",
        lambda _config: pytest.fail("reconstruction must not start"),
    )

    with pytest.raises(MigrationError, match="pending"):
        verify(config)


@pytest.mark.parametrize(
    ("invalid_state", "message"),
    [
        ("checksum", "checksum differs"),
        ("renamed", "renamed from"),
        ("orphan", "file is missing"),
    ],
)
def test_verify_rejects_invalid_applied_history_before_reconstruction(
    tmp_path: Path, database_url: str, monkeypatch, invalid_state: str, message: str
) -> None:
    config = _config(tmp_path, database_url)
    first = _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    if invalid_state == "orphan":
        _write(config, "0002_second.sql", "CREATE TABLE second(id integer);\n")
    apply(config)

    if invalid_state == "checksum":
        first.write_text("CREATE TABLE widgets(id bigint);\n", encoding="utf-8")
    elif invalid_state == "renamed":
        first.rename(config.migrations_dir / "0001_renamed.sql")
    else:
        first.unlink()
    monkeypatch.setattr(
        "coloph_migrations.schema.temporary_database",
        lambda _config: pytest.fail("reconstruction must not start"),
    )

    with pytest.raises(MigrationError, match=message):
        verify(config)


def test_verify_does_not_create_missing_history_table(tmp_path: Path, database_url: str, monkeypatch) -> None:
    config = _config(tmp_path, database_url)
    _write(config, "0001_widgets.sql", "CREATE TABLE widgets(id integer);\n")
    monkeypatch.setattr(
        "coloph_migrations.schema.temporary_database",
        lambda _config: pytest.fail("reconstruction must not start"),
    )

    with pytest.raises(MigrationError, match="tracking table .* does not exist"):
        verify(config)

    assert _regclass(database_url, config.migration_table) is None


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
