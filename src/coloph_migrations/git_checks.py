from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import Config
from .migrations import MigrationError


MIGRATION_RE = re.compile(r"^(?P<version>\d+)_.*\.sql$")


def _names_at_ref(config: Config, ref: str) -> list[str]:
    relative = config.migrations_dir.relative_to(config.root)
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, str(relative)],
        cwd=config.root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise MigrationError(result.stderr.strip() or f"Unable to read migrations at {ref}")
    return [Path(line).name for line in result.stdout.splitlines()]


def _by_version(names: list[str]) -> dict[int, str]:
    result: dict[int, str] = {}
    for name in names:
        match = MIGRATION_RE.fullmatch(name)
        if match:
            result[int(match.group("version"))] = name
    return result


def find_conflicts(main_names: list[str], current_names: list[str], deployed_names: list[str]) -> list[str]:
    main = _by_version(main_names)
    current = _by_version(current_names)
    deployed = _by_version(deployed_names)
    conflicts: list[str] = []
    for version, main_name in sorted(main.items()):
        current_name = current.get(version)
        if current_name is None and deployed.get(version) == main_name:
            conflicts.append(f"Current tree is missing deployed migration {main_name}")
        elif current_name is not None and current_name != main_name:
            conflicts.append(f"Migration {version:04d} conflicts: current={current_name}, main={main_name}")
    for version in sorted(set(current) - set(main)):
        if version < max(main, default=0):
            conflicts.append(f"Migration {current[version]} is inserted before the end of main")
    return conflicts


def check_chain(config: Config) -> dict:
    current = [path.name for path in config.migrations_dir.iterdir() if path.is_file()]
    conflicts = find_conflicts(
        _names_at_ref(config, config.main_ref),
        current,
        _names_at_ref(config, config.deployed_ref),
    )
    if conflicts:
        raise MigrationError("Migration chain conflicts:\n" + "\n".join(f"- {item}" for item in conflicts))
    return {"conflicts": []}
