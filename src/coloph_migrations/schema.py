from __future__ import annotations

import difflib
import platform
import re
import subprocess
from urllib.parse import urlparse

import psycopg

from .config import Config
from .migrations import MigrationError, apply_to_database
from .test_database import temporary_database


SCHEMA_DOC_PREFIX = "-- schema-doc:"


def detect_server_version(database_url: str) -> int:
    with psycopg.connect(database_url) as conn:
        row = conn.execute("SHOW server_version").fetchone()
    if row is None:
        raise MigrationError("PostgreSQL did not report a server version")
    return int(str(row[0]).split(".")[0])


def _child_partitions(database_url: str) -> list[str]:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            ORDER BY n.nspname, c.relname
            """
        ).fetchall()
    return [str(row[0]) for row in rows]


def _pg_dump(database_url: str, pg_version: int, exclude_tables: list[str]) -> str:
    parsed = urlparse(database_url)
    host = parsed.hostname or "localhost"
    docker_host = "host.docker.internal" if host in {"localhost", "127.0.0.1", "::1"} else host
    docker_args: list[str] = []
    if platform.system() == "Linux" and host in {"localhost", "127.0.0.1", "::1"}:
        docker_args = ["--network=host"]
        docker_host = host
    image = "pgvector/pgvector:pg17" if pg_version == 17 else f"postgres:{pg_version}"
    exclude_args = [value for table in exclude_tables for value in ("--exclude-table", table)]
    command = [
        "docker",
        "run",
        "--rm",
        *docker_args,
        "-e",
        f"PGPASSWORD={parsed.password or ''}",
        "-e",
        "PGSSLMODE=disable",
        image,
        "pg_dump",
        f"--host={docker_host}",
        f"--port={parsed.port or 5432}",
        f"--username={parsed.username or ''}",
        f"--dbname={parsed.path.lstrip('/')}",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        *exclude_args,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise MigrationError(f"pg_dump timed out using {image}") from exc
    if result.returncode != 0:
        raise MigrationError(f"pg_dump failed using {image}: {result.stderr.strip()}")
    return result.stdout


def normalize_schema(raw: str, exclude_index_patterns: tuple[str, ...] = ()) -> str:
    schema = re.sub(r"^--.*\n", "", raw, flags=re.MULTILINE)
    schema = re.sub(r"^\\(?:un)?restrict\s+.*\n", "", schema, flags=re.MULTILINE)
    schema = re.sub(r"CONSTRAINT \S+ NOT NULL", "NOT NULL", schema)
    schema = re.sub(r"ADD CONSTRAINT \S+ PRIMARY KEY", "ADD PRIMARY KEY", schema)
    for pattern in exclude_index_patterns:
        schema = re.sub(rf"^CREATE INDEX (?:IF NOT EXISTS\s+)?(?:{pattern})\b.*\n", "", schema, flags=re.MULTILINE)
    schema = re.sub(r"\n{3,}", "\n\n", schema)

    tag_re = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")
    blocks: list[str] = []
    current: list[str] = []
    tag: str | None = None
    for line in schema.strip().split("\n"):
        current.append(line)
        for match in tag_re.finditer(line):
            found = match.group(0)
            tag = found if tag is None else None if found == tag else tag
        if tag is None and not line.strip():
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = []
    if current:
        blocks.append("\n".join(current).strip())
    return "\n\n".join(sorted(blocks)) + "\n"


def canonical_schema(config: Config, database_url: str) -> str:
    version = detect_server_version(database_url)
    raw = _pg_dump(database_url, version, _child_partitions(database_url))
    return normalize_schema(raw, config.exclude_index_patterns)


def strip_top_level_comments(schema: str) -> str:
    result = "\n".join(line for line in schema.splitlines() if not line.startswith("--"))
    return re.sub(r"\n{3,}", "\n\n", result).strip() + "\n"


def restore_schema_doc_comments(generated: str, previous: str) -> tuple[str, int]:
    lines = previous.splitlines()
    blocks: dict[str, list[str]] = {}
    index = 0
    while index < len(lines):
        if not lines[index].startswith(SCHEMA_DOC_PREFIX):
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and lines[index].startswith(SCHEMA_DOC_PREFIX):
            block.append(lines[index])
            index += 1
        while index < len(lines) and not lines[index]:
            index += 1
        if index < len(lines):
            blocks[lines[index].strip()] = block

    output: list[str] = []
    restored = 0
    for line in generated.splitlines():
        block = blocks.get(line.strip())
        if block:
            output.extend(block)
            restored += 1
        output.append(line)
    return "\n".join(output) + ("\n" if generated.endswith("\n") else ""), restored


def snapshot(config: Config, *, database_url: str | None = None, fresh: bool = False, up_to: str | None = None) -> dict:
    if fresh:
        with temporary_database(config) as test_url:
            apply_to_database(config, test_url, up_to=up_to)
            schema = canonical_schema(config, test_url)
    else:
        target = database_url or config.database_url
        if target is None:
            raise MigrationError("database_url is required unless --fresh is used")
        schema = canonical_schema(config, target)

    restored = 0
    if config.schema_snapshot.exists():
        schema, restored = restore_schema_doc_comments(
            schema,
            config.schema_snapshot.read_text(encoding="utf-8"),
        )
    config.schema_snapshot.parent.mkdir(parents=True, exist_ok=True)
    config.schema_snapshot.write_text(schema, encoding="utf-8")
    return {"output": str(config.schema_snapshot), "restored_doc_blocks": restored}


def validate(config: Config, *, match_applied: bool = False, up_to: str | None = None) -> dict:
    if config.database_url is None:
        raise MigrationError("database_url is required")
    target_version = detect_server_version(config.database_url)
    selected_up_to = up_to
    if match_applied:
        with psycopg.connect(config.database_url) as conn:
            row = conn.execute(
                f"SELECT max(version) FROM {config.migration_table}"  # noqa: S608 - identifier is trusted config
            ).fetchone()
        if row and row[0] is not None:
            selected_up_to = str(int(str(row[0])) + 1)

    with temporary_database(config) as test_url:
        apply_to_database(config, test_url, up_to=selected_up_to)
        target = canonical_schema(config, config.database_url)
        rebuilt = canonical_schema(config, test_url)
    identical = target == rebuilt
    result = {"identical": identical, "target_postgres_version": target_version}
    if not identical:
        result["diff"] = "".join(
            difflib.unified_diff(target.splitlines(True), rebuilt.splitlines(True), "target", "rebuilt", n=3)
        )
    return result
