#!/usr/bin/env python3
import json
import os
import re
import subprocess
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "coloph-migrations"
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def run(*command, capture=False):
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=capture)
    return result.stdout.strip() if capture else ""


def version():
    with (ROOT / "pyproject.toml").open("rb") as stream:
        value = tomllib.load(stream)["project"]["version"]
    match = SEMVER.fullmatch(value)
    if not match:
        raise SystemExit(f"package version must be MAJOR.MINOR.PATCH: {value}")
    return value, tuple(map(int, match.groups()))


def published_versions():
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{PACKAGE}/json", timeout=30) as response:
            return set(json.load(response)["releases"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return set()
        raise


def remote_tag(tag):
    output = run("git", "ls-remote", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}", capture=True)
    rows = [line.split() for line in output.splitlines()]
    peeled = next((sha for sha, ref in rows if ref.endswith("^{}")), None)
    return peeled or (rows[0][0] if rows else None)


def release_run(tag):
    deadline = time.time() + 60
    while time.time() < deadline:
        output = run(
            "gh",
            "run",
            "list",
            "--workflow",
            "publish.yml",
            "--branch",
            tag,
            "--limit",
            "1",
            "--json",
            "databaseId,status,conclusion",
            capture=True,
        )
        runs = json.loads(output)
        if runs:
            return runs[0]
        time.sleep(2)
    raise SystemExit(f"no publication run found for {tag}")


def finish_release(tag):
    item = release_run(tag)
    if item["status"] != "completed":
        run("gh", "run", "watch", str(item["databaseId"]), "--exit-status")
    elif item["conclusion"] != "success":
        raise SystemExit(f"publication run {item['databaseId']} ended with {item['conclusion']}")
    for _ in range(30):
        if tag[1:] in published_versions():
            return
        time.sleep(2)
    raise SystemExit(f"{tag[1:]} is not visible on PyPI after publication")


def main():
    target = os.environ.get("COLOPH_SYNC_COMMIT")
    if not target:
        raise SystemExit("COLOPH_SYNC_COMMIT is required")
    remote_main = run("git", "ls-remote", "origin", "refs/heads/main", capture=True).split()
    if not remote_main or remote_main[0] != target:
        raise SystemExit("delivery target is not the current origin/main")

    current, numeric = version()
    tag = f"v{current}"
    tagged = remote_tag(tag)
    releases = published_versions()
    if tagged:
        run("git", "merge-base", "--is-ancestor", tagged, target)
        if current not in releases:
            finish_release(tag)
        print(f"Verified {target[:10]}; {tag} is already published")
        return

    if current in releases:
        raise SystemExit(f"PyPI already contains untagged version {current}")
    published = [tuple(map(int, match.groups())) for item in releases if (match := SEMVER.fullmatch(item))]
    if published and numeric <= max(published):
        raise SystemExit(f"new version {current} must be greater than the published versions")

    run("gh", "release", "create", tag, "--target", target, "--title", tag, "--generate-notes")
    finish_release(tag)
    print(f"Published {tag} from {target[:10]}")


if __name__ == "__main__":
    main()
