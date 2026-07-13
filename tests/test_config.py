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
