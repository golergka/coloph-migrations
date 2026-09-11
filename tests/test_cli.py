from pathlib import Path
import subprocess

from coloph_migrations import cli
from coloph_migrations.cli import _database_url_from_environment, run


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
        "\nNext:\n"
        "1. Set DATABASE_URL in .env.\n"
        "2. Add the initial schema to migrations/0001_init.sql.\n"
        "3. Run coloph-migrate plan.\n"
    )


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


def test_dry_run_command_uses_disposable_database(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "coloph-migrations.toml"
    config_path.write_text('migrations_dir = "migrations"\n', encoding="utf-8")
    observed = []
    monkeypatch.setattr(cli, "dry_run", lambda config, *, up_to: observed.append((config, up_to)) or {"applied": []})

    assert run(["--config", str(config_path), "dry-run", "--up-to", "0002"]) == 0

    assert observed[0][0].database_url is None
    assert observed[0][1] == "0002"
    assert capsys.readouterr().out == "applied: []\n"


def test_init_warns_when_env_is_not_ignored(tmp_path: Path, monkeypatch, capsys) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)

    run(["init"])

    assert capsys.readouterr().err == "WARNING: .env is not ignored by Git. Add it to .gitignore.\n"
