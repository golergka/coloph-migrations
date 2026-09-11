from pathlib import Path
import subprocess

import pytest

from coloph_migrations import cli
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


def test_new_creates_the_next_normalized_migration(tmp_path: Path, monkeypatch) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_init.sql").write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert run(["new", "Add accounts"]) == 0

    assert (migrations / "0002_add_accounts.sql").read_text(encoding="utf-8") == "-- Add migration SQL here.\n"


def test_new_uses_the_configured_directory_and_template(tmp_path: Path, monkeypatch) -> None:
    migrations = tmp_path / "db/migrations"
    migrations.mkdir(parents=True)
    (migrations / "0001_init.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (migrations / "0002_accounts.sql").write_text("SELECT 2;\n", encoding="utf-8")
    template = tmp_path / "migration.sql"
    template.write_text("CREATE TABLE example ();\n", encoding="utf-8")
    (tmp_path / "coloph-migrations.toml").write_text('migrations_dir = "db/migrations"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert run(["new", "events", "--template", str(template)]) == 0

    assert (migrations / "0003_events.sql").read_text(encoding="utf-8") == "CREATE TABLE example ();\n"


@pytest.mark.parametrize("name", ["", "123_accounts", "accounts/old", "accounts.sql"])
def test_new_rejects_invalid_names(tmp_path: Path, monkeypatch, name: str) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_init.sql").write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MigrationError, match="Migration name"):
        run(["new", name])

    assert sorted(migrations.iterdir()) == [migrations / "0001_init.sql"]


def test_new_rejects_an_invalid_sequence_without_creating_a_file(tmp_path: Path, monkeypatch) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_init.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (migrations / "0003_skipped.sql").write_text("SELECT 3;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MigrationError, match="sequence gap"):
        run(["new", "accounts"])

    assert not (migrations / "0004_accounts.sql").exists()


def test_new_does_not_create_a_file_when_the_template_is_missing(tmp_path: Path, monkeypatch) -> None:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_init.sql").write_text("SELECT 1;\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MigrationError, match="Unable to read migration template"):
        run(["new", "accounts", "--template", "missing.sql"])

    assert not (migrations / "0002_accounts.sql").exists()


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


def test_verify_json_reports_both_comparisons(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "verify",
        lambda _config: {
            "identical": False,
            "snapshot_identical": False,
            "target_identical": False,
            "snapshot_diff": "snapshot diff",
            "target_diff": "target diff",
        },
    )

    assert run(["--json", "verify"]) == 1
    output = capsys.readouterr().out
    assert '"snapshot_diff": "snapshot diff"' in output
    assert '"target_diff": "target diff"' in output
