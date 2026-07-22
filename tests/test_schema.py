import subprocess

import pytest

from coloph_migrations.migrations import MigrationError
from coloph_migrations.schema import (
    _pg_dump,
    _pg_dump_command,
    normalize_schema,
    restore_schema_doc_comments,
    strip_top_level_comments,
)


def test_normalize_schema_sorts_blocks_and_preserves_function_body_comments() -> None:
    raw = """-- dump header
CREATE TABLE z (id integer);

CREATE FUNCTION f() RETURNS void AS $$
BEGIN
  -- body comment
  NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE a (id integer);
"""
    result = normalize_schema(raw)
    assert result.index("CREATE FUNCTION") < result.index("CREATE TABLE a") < result.index("CREATE TABLE z")
    assert "  -- body comment" in result


def test_restore_schema_doc_comments() -> None:
    generated = "CREATE TABLE public.widgets (\n    id integer\n);\n"
    previous = "-- schema-doc: code: widgets.py\nCREATE TABLE public.widgets (\n    id integer\n);\n"
    restored, count = restore_schema_doc_comments(generated, previous)
    assert count == 1
    assert restored.startswith("-- schema-doc: code: widgets.py\n")
    assert strip_top_level_comments(restored) == generated


def test_pg_dump_command_keeps_local_dump_without_ssl() -> None:
    command = _pg_dump_command("postgresql://test:secret@localhost:5432/widgets", 17, [])

    assert "PGSSLMODE=disable" in command
    assert "--network=host" not in command


def test_pg_dump_command_preserves_remote_sslmode_and_root_cert(tmp_path, monkeypatch) -> None:
    rootcert = tmp_path / ".postgresql" / "root.crt"
    rootcert.parent.mkdir()
    rootcert.write_text("certificate", encoding="utf-8")
    monkeypatch.setattr("coloph_migrations.schema.Path.home", lambda: tmp_path)

    command = _pg_dump_command("postgresql://test:secret@example.test:5432/widgets?sslmode=verify-full", 17, [])

    assert "PGSSLMODE=verify-full" in command
    assert "--volume" in command
    assert f"{rootcert}:/root/.postgresql/root.crt:ro" in command


def test_pg_dump_failure_reports_image_without_name_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "coloph_migrations.schema.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, stdout="", stderr="pg_hba rejects connection"),
    )

    with pytest.raises(MigrationError, match="pg_dump failed using pgvector/pgvector:pg17: pg_hba rejects connection"):
        _pg_dump("postgresql://test:secret@example.test/widgets?sslmode=verify-full", 17, [])
