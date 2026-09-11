from pathlib import Path
import subprocess

import pytest

from coloph_migrations.cli import _database_url_from_environment, run
from coloph_migrations.migrations import MigrationError


def test_init_creates_config_and_migrations_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert run(["init"]) == 0

    assert (tmp_path / "coloph-migrations.toml").read_text(encoding="utf-8") == (
        'migrations_dir = "migrations"\nschema_snapshot = "migrations/schema.sql"\n'
    )
    assert (tmp_path / "migrations").is_dir()
    assert (tmp_path / "migrations/0001_init.sql").read_text(encoding="utf-8") == (
        "-- Add the initial database schema here.\n"
    )
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "DATABASE_URL=\n"
    assert capsys.readouterr().out == (
        "Created coloph-migrations.toml\n"
        "Created migrations/\n"
        "Created migrations/0001_init.sql\n"
        "Created .env\n"
        "Created skills/change-database-schema/SKILL.md\n"
        "Created skills/repair-database-schema/SKILL.md\n"
        "\nNext:\n"
        "1. Set DATABASE_URL in .env.\n"
        "2. Add the initial schema to migrations/0001_init.sql.\n"
        "3. Run coloph-migrate plan.\n"
    )


def test_init_installs_skills_and_is_repeatable(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    run(["init"])
    capsys.readouterr()
    for name in ("change-database-schema", "repair-database-schema"):
        assert f"name: {name}" in (tmp_path / "skills" / name / "SKILL.md").read_text()
    run(["--json", "init"])
    assert capsys.readouterr().out == '{"created": []}\n'


def test_init_rejects_skill_conflict_before_writing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    skill = tmp_path / "skills/change-database-schema/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Host instructions\n")
    with pytest.raises(MigrationError, match="Skill file differs"):
        run(["init"])
    assert skill.read_text() == "Host instructions\n"
    assert not (tmp_path / "coloph-migrations.toml").exists()
    assert not (tmp_path / "skills/repair-database-schema").exists()


def test_init_preserves_existing_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "coloph-migrations.toml"
    config.write_text('migrations_dir = "db/migrations"\n', encoding="utf-8")
    migrations = tmp_path / "db/migrations"
    migrations.mkdir(parents=True)
    migration = migrations / "0001_init.sql"
    migration.write_text("SELECT 1;\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=postgresql://existing\n", encoding="utf-8")

    assert run(["init"]) == 0

    assert config.read_text(encoding="utf-8") == 'migrations_dir = "db/migrations"\n'
    assert migration.read_text(encoding="utf-8") == "SELECT 1;\n"
    assert env.read_text(encoding="utf-8") == "DATABASE_URL=postgresql://existing\n"
    assert not (tmp_path / "migrations").exists()


def test_init_does_not_add_an_initial_file_to_existing_migrations(tmp_path: Path, monkeypatch) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    existing = migrations / "0001_existing.sql"
    existing.write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    run(["init"])

    assert existing.read_text(encoding="utf-8") == "SELECT 1;\n"
    assert not (migrations / "0001_init.sql").exists()


def test_database_url_precedence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("COLOPH_MIGRATIONS_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://dotenv\n"
        "COLOPH_MIGRATIONS_DATABASE_URL=postgresql://coloph-dotenv\n",
        encoding="utf-8",
    )

    assert _database_url_from_environment(tmp_path) == "postgresql://coloph-dotenv"

    monkeypatch.setenv("DATABASE_URL", "postgresql://environment")
    assert _database_url_from_environment(tmp_path) == "postgresql://environment"

    monkeypatch.setenv("COLOPH_MIGRATIONS_DATABASE_URL", "postgresql://coloph-environment")
    assert _database_url_from_environment(tmp_path) == "postgresql://coloph-environment"


def test_init_warns_when_env_is_not_ignored(tmp_path: Path, monkeypatch, capsys) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    run(["init"])

    assert capsys.readouterr().err == "WARNING: .env is not ignored by Git. Add it to .gitignore.\n"
