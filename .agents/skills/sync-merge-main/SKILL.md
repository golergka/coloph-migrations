---
name: sync-merge-main
description: Merge local main into the current contributor branch after a sync conflict, with history review, semantic conflict resolution, and validation.
---

Use this skill when a contributor branch must integrate the configured local main branch, especially after `uv run coloph-sync status` reports an actionable merge conflict for the current tip.
A recorded conflict does not resolve through waiting. The branch owner must advance the branch with a real merge before the coordinator can retry it.

Work only in the current worktree and branch. Never inspect another worktree or operate the coordinator checkout.
Do not create another worktree or switch branches unless the user explicitly requests that operation.
If the checkout is detached, create a descriptive `codex/` branch at its current HEAD.
Never merge a remote-tracking branch. Read `main_ref` from `coloph-sync.toml` and merge that local branch.
Do not rebase, force-push, bypass hooks, or select a whole conflicted file with `--ours` or `--theirs`.

## Prepare

1. Read the repository's Git, check, and delivery instructions.
2. Run `git branch --show-current` and `git status --short --branch`.
3. Finish and commit current work before merging. A `wip` or `failed` tip needs an ordinary passed successor before it can be merged.
4. Resolve the configured local main ref and compute the shared parent with `git merge-base HEAD <main-ref>`.
5. If `<main-ref>` is already an ancestor of `HEAD`, do not create a no-op merge.

## Read both histories

Before changing files, read both lines from their shared parent:

- `git log --oneline --reverse <base>..HEAD`
- `git log --oneline --reverse <base>..<main-ref>`

Identify the intent of each side, the modules both sides changed, and any refactor or interface that incoming work may affect.

## Merge and resolve

Run `git merge <main-ref> --no-edit`.
If it conflicts, list unresolved files with `git diff --name-only --diff-filter=U`.
For each file, inspect its commits on both sides and the relevant introducing diffs.

Resolve behavior, not only conflict markers:

- Preserve compatible requirements from both sides.
- Port branch features onto newer interfaces introduced by main.
- Update adjacent callers, tests, configuration, or migrations when the resolved contract changes.
- Escalate only when product behavior, data policy, permissions, or another material decision cannot be inferred safely.

After textual resolution, search for semantic drift in both directions. Check that incoming commits did not restore concepts removed on the branch and that branch work uses replacements introduced on main.

## Validate and save

Run focused checks for affected behavior and the repository's required commit checks.
Review `git status --short --branch`, stage the resolved files, and complete the merge with Git's generated merge subject.
Do not replace the generated subject or hand-edit hook-managed commit metadata.

After the passed merge commit, run `uv run coloph-sync status` for the new tip. An old conflict recorded for an ancestor can be ignored while the coordinator has not checked the new tip. A new conflict recorded for the new tip starts this workflow again.

Report the shared base, the important commits and intent on each side, any semantic risk, the chosen resolution, checks run, and any decision that still requires the user.
