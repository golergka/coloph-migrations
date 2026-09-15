---
name: sync-release
description: Prepare and propose a versioned release from the main-branch coordinator. Use only when deliberately releasing a project managed by sync coordination.
---

# Prepare a release

Use this skill only in the clean main checkout operated by the main-branch coordinator. Do not use it in a contributor worktree, and do not ask a contributor to choose or bump a release version.

## Prepare, do not publish

Stop the sync loop with `uv run coloph-sync stop`. If it has an operator reminder, delete that reminder and verify the loop has exited. Do not start another coordinator while preparing the release.

Verify that the current branch is the configured `main` branch, the working tree is clean, and no deploy attempt is unfinished. Bring main to a deployable state: resolve any recorded coordinator failure through the established coordinator recovery procedure, run the project's required checks, and ensure the current commit is eligible for deployment. Do not repair contributor branches from this workflow.

Find the most recent versioned release and read every change from that release through `HEAD`, including merge commits and the relevant diffs. Use the project’s documented SemVer rules to determine whether the changes require a major, minor, patch, or no version change. Check the declared package version and published versions so the proposed version is valid and new.

Before editing a version, creating a release commit or tag, pushing, or running deployment, report to the user:

- the last release and the changes since it;
- the proposed SemVer change and resulting version, or why no release is warranted;
- the checks and deployment steps that will follow.

Ask for confirmation. This confirmation is the boundary for all release mutations. Do not infer it from a request merely to prepare or inspect a release.

## After confirmation

Make the approved version change on main, run the project’s required pre-release checks and build, commit the checked release change, then use the coordinator's normal `uv run coloph-sync run --push-deploy-only` path to push and deploy it. Verify the project-defined publication result before reporting completion.

If the release cannot proceed, leave the loop stopped and report the concrete blocker. Do not roll back, force-push, or select a different version without fresh user direction.
