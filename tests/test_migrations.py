from pathlib import Path

import pytest

from coloph_migrations import migrations
from coloph_migrations.migrations import Migration, MigrationError, checksum_sql, create_migration, discover_migrations


def _write(path: Path, text: str = "SELECT 1;\n") -> None:
    path.write_text(text, encoding="utf-8")


def test_discover_migrations_requires_sequential_numbers(tmp_path: Path) -> None:
    _write(tmp_path / "0001_first.sql")
    _write(tmp_path / "0003_third.sql")
    with pytest.raises(MigrationError, match="sequence gap"):
        discover_migrations(tmp_path)


def test_discover_migrations_sorts_unpadded_versions_numerically(tmp_path: Path) -> None:
    for version in range(1, 11):
        _write(tmp_path / f"{version}_migration.sql")

    assert [int(item.version) for item in discover_migrations(tmp_path)] == list(range(1, 11))


def test_discover_migrations_rejects_duplicate_numeric_versions(tmp_path: Path) -> None:
    _write(tmp_path / "1_first.sql")
    _write(tmp_path / "01_duplicate.sql")

    with pytest.raises(MigrationError, match="Duplicate migration version: 0001"):
        discover_migrations(tmp_path)


def test_discover_migrations_allows_transaction_keywords_inside_function_bodies(tmp_path: Path) -> None:
    _write(
        tmp_path / "0001_first.sql",
        "CREATE FUNCTION noop() RETURNS void LANGUAGE plpgsql AS $$ BEGIN NULL; END; $$;\n",
    )
    assert [migration.filename for migration in discover_migrations(tmp_path)] == ["0001_first.sql"]


def test_discover_migrations_returns_checksum_and_exclusive_up_to(tmp_path: Path) -> None:
    _write(tmp_path / "0001_first.sql")
    _write(tmp_path / "0002_second.sql", "SELECT 2;\n")
    migrations = discover_migrations(tmp_path, up_to="0002")
    assert [item.version for item in migrations] == ["0001"]
    assert migrations[0].checksum == checksum_sql("SELECT 1;\n")


def test_create_migration_never_overwrites_a_concurrent_target(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "0001_init.sql"
    source.write_text("SELECT 1;\n", encoding="utf-8")
    target = tmp_path / "0002_accounts.sql"

    def discover_with_concurrent_creation(_: Path) -> list[Migration]:
        target.write_text("original\n", encoding="utf-8")
        return [Migration("0001", source, "SELECT 1;\n", checksum_sql("SELECT 1;\n"))]

    monkeypatch.setattr(migrations, "discover_migrations", discover_with_concurrent_creation)

    with pytest.raises(MigrationError, match="already exists"):
        create_migration(tmp_path, "accounts")

    assert target.read_text(encoding="utf-8") == "original\n"
