from pathlib import Path

import pytest

from coloph_migrations.migrations import MigrationError, checksum_sql, discover_migrations


def _write(path: Path, text: str = "SELECT 1;\n") -> None:
    path.write_text(text, encoding="utf-8")


def test_discover_migrations_requires_sequential_numbers(tmp_path: Path) -> None:
    _write(tmp_path / "0001_first.sql")
    _write(tmp_path / "0003_third.sql")
    with pytest.raises(MigrationError, match="sequence gap"):
        discover_migrations(tmp_path)


@pytest.mark.parametrize("statement", ["BEGIN;", " commit ;", "ROLLBACK;"])
def test_discover_migrations_rejects_explicit_transaction_control(tmp_path: Path, statement: str) -> None:
    _write(tmp_path / "0001_first.sql", statement)
    with pytest.raises(MigrationError, match="explicit"):
        discover_migrations(tmp_path)


def test_discover_migrations_returns_checksum_and_exclusive_up_to(tmp_path: Path) -> None:
    _write(tmp_path / "0001_first.sql")
    _write(tmp_path / "0002_second.sql", "SELECT 2;\n")
    migrations = discover_migrations(tmp_path, up_to="0002")
    assert [item.version for item in migrations] == ["0001"]
    assert migrations[0].checksum == checksum_sql("SELECT 1;\n")
