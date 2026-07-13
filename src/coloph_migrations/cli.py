from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import psycopg

from .backwards import check_backwards
from .config import load_config, override_config
from .git_checks import check_chain
from .migrations import MigrationError, apply, check_current, statuses
from .repair import repair_checksums
from .schema import snapshot, validate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coloph-migrate", description="Agent-friendly PostgreSQL migrations")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--database-url")
    parser.add_argument("--migrations-dir", type=Path)
    parser.add_argument("--schema-snapshot", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    sub = parser.add_subparsers(dest="command", required=True)

    apply_parser = sub.add_parser("apply", help="Apply pending migrations")
    apply_parser.add_argument("--up-to")
    apply_parser.add_argument("--dangerously-skip-advisory-lock", action="store_true")
    sub.add_parser("list", help="List applied and pending migrations")
    sub.add_parser("check", help="Fail unless every migration is applied and unchanged")

    snapshot_parser = sub.add_parser("snapshot", help="Write the canonical schema snapshot")
    snapshot_parser.add_argument(
        "--fresh", action="store_true", help="Rebuild from migrations in disposable PostgreSQL"
    )
    snapshot_parser.add_argument("--up-to")

    validate_parser = sub.add_parser("validate", help="Compare target schema with a reconstructed database")
    validate_parser.add_argument("--match-applied", action="store_true")
    validate_parser.add_argument("--up-to")

    repair_parser = sub.add_parser("repair-checksums", help="Repair checksums only after schema equivalence")
    repair_parser.add_argument("--dry-run", action="store_true")
    sub.add_parser("check-chain", help="Check migration numbering against main and deployed refs")
    sub.add_parser("check-backwards", help="Run deployed code against the new schema")
    return parser


def _render(value: object, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(value, default=str, sort_keys=True))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    elif isinstance(value, list):
        for item in value:
            print(item)
    else:
        print(value)


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = override_config(
        load_config(args.config),
        database_url=args.database_url or os.environ.get("COLOPH_MIGRATIONS_DATABASE_URL"),
        migrations_dir=args.migrations_dir,
        schema_snapshot=args.schema_snapshot,
    )
    command = args.command
    if command == "apply":
        result = apply(
            config,
            skip_advisory_lock=args.dangerously_skip_advisory_lock,
            up_to=args.up_to,
        )
    elif command in {"list", "check"}:
        if config.database_url is None:
            raise MigrationError("database_url is required")
        with psycopg.connect(config.database_url) as conn:
            rows = check_current(conn, config) if command == "check" else statuses(conn, config)
        result = [row.__dict__ for row in rows]
    elif command == "snapshot":
        result = snapshot(config, fresh=args.fresh, up_to=args.up_to)
    elif command == "validate":
        result = validate(config, match_applied=args.match_applied, up_to=args.up_to)
        if not result["identical"]:
            _render(result, json_output=args.json_output)
            return 1
    elif command == "repair-checksums":
        result = repair_checksums(config, dry_run=args.dry_run)
    elif command == "check-chain":
        result = check_chain(config)
    elif command == "check-backwards":
        result = check_backwards(config)
    else:
        raise AssertionError(f"Unhandled command: {command}")
    _render(result, json_output=args.json_output)
    return 0


def main() -> None:
    try:
        raise SystemExit(run())
    except (MigrationError, ValueError, psycopg.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
