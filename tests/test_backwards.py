from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import subprocess
import sys

import pytest

from coloph_migrations import backwards
from coloph_migrations.config import Config
from coloph_migrations.migrations import MigrationError


def _run(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _repo(tmp_path: Path) -> Config:
    _run(tmp_path, "init")
    _run(tmp_path, "config", "user.email", "parity@example.com")
    _run(tmp_path, "config", "user.name", "Parity")
    migrations = tmp_path / "migrations"
    tests = tmp_path / "tests"
    migrations.mkdir()
    tests.mkdir()
    (migrations / "0001_base.sql").write_text("SELECT 1;\n", encoding="utf-8")
    (tests / "conftest.py").write_text("TEST_DATABASE_URL = True\n", encoding="utf-8")
    (tests / "test_smoke.py").write_text("def test_smoke(): pass\n", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "deployed")
    _run(tmp_path, "tag", "deployed")
    (migrations / "0002_new.sql").write_text("SELECT 2;\n", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "new migration")
    return Config(
        root=tmp_path,
        migrations_dir=migrations,
        schema_snapshot=migrations / "schema.sql",
        deployed_ref="deployed",
        backwards_bootstrap_file=tests / "conftest.py",
        backwards_bootstrap_marker="TEST_DATABASE_URL",
        backwards_test_globs=("tests/test_smoke*.py",),
        backwards_test_args=(),
    )


@contextmanager
def _database():
    yield "postgresql://disposable"


def test_old_code_new_schema_failure_is_loud(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = replace(_repo(tmp_path), backwards_test_command=(sys.executable, "-c", "raise SystemExit(7)"))
    monkeypatch.setattr(backwards, "temporary_database", lambda _config: _database())
    monkeypatch.setattr(backwards, "apply_to_database", lambda *_args, **_kwargs: None)

    with pytest.raises(MigrationError, match="Deployed code failed"):
        backwards.check_backwards(config)


def test_old_code_new_schema_success_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = replace(_repo(tmp_path), backwards_test_command=(sys.executable, "-c", "pass"))
    monkeypatch.setattr(backwards, "temporary_database", lambda _config: _database())
    monkeypatch.setattr(backwards, "apply_to_database", lambda *_args, **_kwargs: None)

    assert backwards.check_backwards(config)["status"] == "passed"


def test_missing_deployed_bootstrap_support_skips(tmp_path: Path) -> None:
    config = replace(_repo(tmp_path), backwards_test_command=(sys.executable, "-c", "pass"))
    config.backwards_bootstrap_file.write_text("# no marker\n", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "remove support")
    _run(tmp_path, "tag", "-f", "deployed")
    (config.migrations_dir / "0003_newer.sql").write_text("SELECT 3;\n", encoding="utf-8")
    _run(tmp_path, "add", ".")
    _run(tmp_path, "commit", "-m", "newer migration")
    assert backwards.check_backwards(config)["status"] == "skipped"
