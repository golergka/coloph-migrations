from __future__ import annotations

import argparse
from importlib.resources import files
import json
import os
from pathlib import Path
import subprocess
import sys

from dotenv import dotenv_values
import psycopg

from .backwards import check_backwards
from .config import DEFAULT_CONFIG_NAME, load_config, override_config
from .git_checks import check_chain
from .migrations import MIGRATION_RE, MigrationError, apply, check_current, plan, statuses
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

    sub.add_parser("init", help="Create configuration, migrations, and host-project skills")
    apply_parser = sub.add_parser("apply", help="Apply pending migrations")
    apply_parser.add_argument("--up-to")
    apply_parser.add_argument("--dangerously-skip-advisory-lock", action="store_true")
    apply_parser.add_argument(
        "--reconstruction",
        action="store_true",
        help="Apply disposable-database policies configured for schema reconstruction",
    )
    sub.add_parser("list", help="List applied and pending migrations")
    sub.add_parser("plan", help="List pending migrations; fail on invalid applied history")
    sub.add_parser("check", help="Fail unless every migration is applied and unchanged")

    snapshot_parser = sub.add_parser("snapshot", help="Write the canonical schema snapshot")
    snapshot_parser.add_argument(
        "--fresh", action="store_true", help="Rebuild from migrations in disposable PostgreSQL"
    )
    snapshot_parser.add_argument("--up-to")
    snapshot_parser.add_argument("--no-preserve-doc-comments", action="store_true")

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


def _database_url_from_environment(root: Path) -> str | None:
    dotenv = dotenv_values(root / ".env")
    return (
        os.environ.get("COLOPH_MIGRATIONS_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or dotenv.get("COLOPH_MIGRATIONS_DATABASE_URL")
        or dotenv.get("DATABASE_URL")
    )


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "init":
        config_path = (args.config or Path(DEFAULT_CONFIG_NAME)).resolve()
        skill_files = {
            config_path.parent / "skills" / name / "SKILL.md":
            files("coloph_migrations").joinpath("skills", name, "SKILL.md").read_text(encoding="utf-8")
            for name in ("change-database-schema", "repair-database-schema")
        }
        for path, content in skill_files.items():
            if path.exists() and path.read_text(encoding="utf-8") != content:
                raise MigrationError(f"Skill file differs: {path}; reconcile or move it before running init")
        env_path = config_path.parent / ".env"
        created: list[Path] = []
        if not config_path.exists():
            config_path.write_text(
                'migrations_dir = "migrations"\nschema_snapshot = "migrations/schema.sql"\n',
                encoding="utf-8",
            )
            created.append(config_path)
        migrations_dir = load_config(config_path).migrations_dir
        migration_path = migrations_dir / "0001_init.sql"
        migrations_existed = migrations_dir.exists()
        migrations_dir.mkdir(parents=True, exist_ok=True)
        if not migrations_existed:
            created.append(migrations_dir)
        has_migrations = any(MIGRATION_RE.fullmatch(path.name) for path in migrations_dir.glob("*.sql"))
        if not has_migrations:
            migration_path.write_text("-- Add the initial database schema here.\n", encoding="utf-8")
            created.append(migration_path)
        if not env_path.exists():
            env_path.write_text("DATABASE_URL=\n", encoding="utf-8")
            created.append(env_path)
        for path, content in skill_files.items():
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                created.append(path)
        try:
            ignore_check = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", ".env"],
                cwd=config_path.parent,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            ignore_check = None
        if ignore_check is not None and ignore_check.returncode == 1:
            print("WARNING: .env is not ignored by Git. Add it to .gitignore.", file=sys.stderr)
        created_display = [os.path.relpath(path) for path in created]
        migrations_display = os.path.relpath(migrations_dir)
        if args.json_output:
            _render({"created": created_display}, json_output=True)
        else:
            for path in created_display:
                suffix = "/" if Path(path).is_dir() else ""
                print(f"Created {path}{suffix}")
            if not created:
                print("All initialization files already exist.")
            print("\nNext:")
            print("1. Set DATABASE_URL in .env.")
            if migration_path.exists():
                print(f"2. Add the initial schema to {os.path.relpath(migration_path)}.")
            else:
                print(f"2. Review the migration files in {migrations_display}/.")
            print("3. Run coloph-migrate plan.")
        return 0
    config = load_config(args.config)
    config = override_config(
        config,
        database_url=args.database_url or _database_url_from_environment(config.root),
        migrations_dir=args.migrations_dir,
        schema_snapshot=args.schema_snapshot,
    )
    command = args.command
    if command == "apply":
        result = apply(
            config,
            skip_advisory_lock=args.dangerously_skip_advisory_lock,
            up_to=args.up_to,
            reconstruction=args.reconstruction,
        )
    elif command in {"list", "plan", "check"}:
        if config.database_url is None:
            raise MigrationError("database_url is required")
        with psycopg.connect(config.database_url) as conn:
            if command == "check":
                rows = check_current(conn, config)
            elif command == "plan":
                rows = plan(conn, config)
            else:
                rows = statuses(conn, config)
        result = [row.__dict__ for row in rows]
    elif command == "snapshot":
        result = snapshot(
            config,
            fresh=args.fresh,
            up_to=args.up_to,
            preserve_doc_comments=not args.no_preserve_doc_comments,
        )
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
