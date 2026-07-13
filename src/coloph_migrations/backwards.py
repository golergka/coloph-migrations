from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .config import Config
from .migrations import MigrationError, apply_to_database
from .test_database import temporary_database


def _git(config: Config, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=config.root,
        capture_output=True,
        text=True,
        timeout=60,
    )


def check_backwards(config: Config) -> dict:
    if not config.backwards_test_command:
        raise MigrationError("backwards_test_command must be configured")
    resolve = _git(config, "rev-parse", config.deployed_ref)
    if resolve.returncode != 0:
        return {"status": "skipped", "reason": f"ref {config.deployed_ref} does not exist"}
    deployed_sha = resolve.stdout.strip()

    if config.backwards_bootstrap_file and config.backwards_bootstrap_marker:
        relative_bootstrap = config.backwards_bootstrap_file.relative_to(config.root)
        bootstrap = _git(config, "show", f"{deployed_sha}:{relative_bootstrap}")
        if bootstrap.returncode != 0:
            raise MigrationError(bootstrap.stderr.strip() or f"Unable to read {relative_bootstrap} at deployed ref")
        if config.backwards_bootstrap_marker not in bootstrap.stdout:
            return {"status": "skipped", "reason": "deployed code lacks backwards-test database support"}
    head = _git(config, "rev-parse", "HEAD")
    if head.returncode != 0:
        raise MigrationError(head.stderr.strip() or "Unable to resolve HEAD")
    if deployed_sha == head.stdout.strip():
        return {"status": "skipped", "reason": "HEAD equals deployed ref"}

    relative = str(config.migrations_dir.relative_to(config.root))
    changed = _git(config, "diff", "--name-only", "--diff-filter=A", deployed_sha, "HEAD", "--", relative)
    if changed.returncode != 0:
        raise MigrationError(changed.stderr.strip() or "Unable to compare migration files")
    if not any(line.endswith(".sql") for line in changed.stdout.splitlines()):
        return {"status": "skipped", "reason": "no new migration files"}

    worktree = Path(tempfile.mkdtemp(prefix="coloph-migrations-backwards-"))
    with temporary_database(config) as database_url:
        apply_to_database(config, database_url)
        added = _git(config, "worktree", "add", "--detach", str(worktree), deployed_sha)
        if added.returncode != 0:
            shutil.rmtree(worktree, ignore_errors=True)
            raise MigrationError(added.stderr.strip() or "Unable to create deployed worktree")
        try:
            if config.backwards_setup_command:
                subprocess.run(config.backwards_setup_command, cwd=worktree, check=True)
            env = {**os.environ, config.backwards_database_url_env: database_url}
            test_command = list(config.backwards_test_command)
            if config.backwards_test_globs:
                targets = sorted(
                    str(path.relative_to(worktree))
                    for pattern in config.backwards_test_globs
                    for path in worktree.glob(pattern)
                )
                if not targets:
                    raise MigrationError(
                        "No backwards-compatibility test files matched: " + ", ".join(config.backwards_test_globs)
                    )
                test_command.extend(targets)
            test_command.extend(config.backwards_test_args)
            result = subprocess.run(
                test_command,
                cwd=worktree,
                env=env,
                capture_output=True,
                text=True,
                timeout=1500,
            )
            if result.returncode != 0:
                raise MigrationError(
                    "Deployed code failed against the new schema:\n" + result.stdout[-3000:] + result.stderr[-1500:]
                )
        finally:
            removed = _git(config, "worktree", "remove", "--force", str(worktree))
            if removed.returncode != 0:
                shutil.rmtree(worktree, ignore_errors=True)
    return {"status": "passed", "deployed_sha": deployed_sha}
