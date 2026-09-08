import subprocess

from coloph_migrations import schema
from coloph_migrations.schema import normalize_schema, restore_schema_doc_comments, strip_top_level_comments


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


def test_pg_dump_preserves_url_options_and_decodes_password(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout="-- schema\n", stderr="")

    monkeypatch.setattr(schema.subprocess, "run", fake_run)

    schema._pg_dump(
        "postgresql://user:pa%40ss@database.example/app%2Fname?sslmode=require&application_name=snapshot",
        17,
        [],
    )

    command = captured["command"]
    assert "PGPASSWORD=pa@ss" in command
    assert "PGSSLMODE=disable" not in command
    assert (
        "--dbname=postgresql://user@database.example:5432/app%2Fname?sslmode=require&application_name=snapshot"
        in command
    )
