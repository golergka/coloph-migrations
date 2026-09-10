#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)["project"]["version"]


def check_tag(tag: str | None) -> None:
    if tag is not None and tag != f"v{version()}":
        raise SystemExit(f"release tag {tag!r} does not match package version v{version()}")


def artifacts() -> list[Path]:
    package_version = version()
    wheel = list(DIST.glob(f"coloph_migrations-{package_version}-*.whl"))
    source = list(DIST.glob(f"coloph_migrations-{package_version}.tar.gz"))
    if len(wheel) != 1 or len(source) != 1:
        raise SystemExit(f"expected one wheel and one source distribution for {package_version}")
    return [*wheel, *source]


def build(tag: str | None) -> None:
    check_tag(tag)
    run("uv", "build", "--no-sources")
    for artifact in artifacts():
        run(
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--with",
            str(artifact),
            "python",
            "-c",
            "from importlib.metadata import version; import coloph_migrations; "
            "assert coloph_migrations.__version__ == version('coloph-migrations')",
        )
        run(
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--with",
            str(artifact),
            "coloph-migrate",
            "--help",
        )


def publish(tag: str | None) -> None:
    check_tag(tag)
    run("uv", "publish", *(str(artifact) for artifact in artifacts()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "publish"))
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.command == "build":
        build(args.tag)
    else:
        publish(args.tag)


if __name__ == "__main__":
    main()
