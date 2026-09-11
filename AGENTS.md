# Agent instructions

## Correctness

- OPERATIONS MUST EITHER COMPLETE FULLY AND CORRECTLY OR FAIL LOUDLY.
- MIGRATIONS MUST EITHER APPLY COMPLETELY OR CRASH THE RUN. NEVER SKIP A FAILED MIGRATION.
- DO NOT SILENTLY EAT ERRORS.
- ALWAYS COMMIT YOUR CHANGES.
- `coloph-migrations` is a project-local development dependency. Keep all documentation, examples, skills, and generated guidance consistent with `uv run coloph-migrate`.

## Installed user skills

- `src/coloph_migrations/skills/` contains package assets installed into a host project's `./skills/` by `uv run coloph-migrate init`. They are not instructions for work inside this repository.
- Every change to public CLI, configuration, migration, snapshot, validation, repair, or backwards-compatibility behavior must update every affected installed user skill in the same commit.
- Keep skill descriptions centered on the user's goal, such as changing or repairing a database schema. Keep package reference details in the skill body or README.

## Versioning

- `[project].version` in `pyproject.toml` is the sole package-version source. Runtime versions must derive from installed package metadata; do not add version literals elsewhere.
- Before every release, classify each user-visible change and bump exactly one SemVer component: MAJOR for incompatible public CLI, configuration, or migration-behavior changes; MINOR for backward-compatible features; PATCH for backward-compatible bug or security fixes.
- Do not publish a version without a qualifying public change. Documentation, tests, CI, and behavior-preserving refactors do not require a bump.
- A release tag must be exactly `vX.Y.Z`, matching `[project].version`. Released versions are immutable.
- Reset lower-order components when bumping (`X+1.0.0` or `X.Y+1.0`) and update `uv.lock` whenever `pyproject.toml` changes.
- Before release, run `uv lock --check`, `uv run pytest -q`, and `python scripts/release.py build --tag vX.Y.Z`.
