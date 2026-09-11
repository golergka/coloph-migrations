from pathlib import Path

import pytest

from coloph_migrations.config import load_config


def test_load_config_resolves_paths_and_local_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "coloph-migrations.toml").write_text(
        'migrations_dir = "db/migrations"\ndatabase_url = "postgresql://base"\n',
        encoding="utf-8",
    )
    (tmp_path / "coloph-migrations.local.toml").write_text(
        'database_url = "postgresql://local"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.migrations_dir == tmp_path / "db/migrations"
    assert config.schema_snapshot == tmp_path / "migrations/schema.sql"
    assert config.database_url == "postgresql://local"


def test_unknown_configuration_key_fails(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('mystery = "value"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown configuration keys"):
        load_config(path)


@pytest.mark.parametrize(
    "name",
    [
        "legacy_migration_table",
        "fresh_skip_feature_not_supported",
        "fresh_vacuum_after_each_migration",
        "concurrent_ddl_retry_versions",
        "concurrent_ddl_retry_message",
        "concurrent_ddl_max_attempts",
        "concurrent_ddl_retry_sleep_seconds",
    ],
)
def test_removed_configuration_keys_fail_as_unknown(tmp_path: Path, name: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"{name} = false\n", encoding="utf-8")
    with pytest.raises(ValueError, match=rf"Unknown configuration keys: {name}"):
        load_config(path)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_retry_counts_must_be_positive_integers(tmp_path: Path, value: object) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"apply_max_attempts = {str(value).lower()}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="apply_max_attempts must be a positive integer"):
        load_config(path)
