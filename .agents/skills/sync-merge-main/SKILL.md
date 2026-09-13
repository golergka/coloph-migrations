---
name: sync-merge-main
description: Merge configured local main into the current contributor branch with merge-base history review, semantic conflict diagnosis, validation, and return to sync-finish.
---

# Merge Main

Use this skill whenever a contributor branch needs to integrate the configured local main branch, including for validation, compatibility, closeout, or a coordinator merge failure.
Before starting, read the repository's Git, check, and delivery instructions.

A coordinator `merge failed` result is actionable for the branch tip the coordinator checked, not a state to wait through. The coordinator will not merge that branch tip as-is. The branch owner must immediately use this skill, integrate the configured local main branch, resolve every textual and semantic conflict, validate the result, and leave the branch mergeable. Do not keep a passive reminder running while repeatedly reporting the same merge failure.

After that repair advances the branch tip, `uv run coloph-sync status` suppresses an old failure recorded for an ancestor of the current branch. A pending result saying the coordinator has not reached the current branch tip yet is a passive wait or reminder state, not another `sync-merge-main` instruction. If the coordinator later checks the new tip and records `merge failed` again, the failure becomes actionable again.

DO NOT END THE TURN OR JUST REPORT THE FAILURE. A merge failure is the command to perform this workflow now, then return to `sync-finish`. Escalate only when the semantic resolution genuinely requires new user authority or unavailable external input after all safe in-scope diagnosis and repair are exhausted.

If the goal is end-to-end closeout after implementation, use `sync-finish` first; it will call into this skill only when the branch needs the configured local main branch merged in or a coordinator merge blocker resolved.

## Non-Negotiables

- Merge the configured **local** main branch, never its remote-tracking branch.
- After the coordinator reports `merge failed` for the current branch tip, restoring branch mergeability is the branch owner's responsibility; exhaust all safe branch-side diagnosis and repair before escalating.
- Use `git merge "$MAIN_REF" --no-edit` only after reading both sides from the shared merge-base.
- Do not auto-abort on merge failure. Diagnose first.
- Do not resolve conflicts by "making git green" only; resolve behavior and data-model intent.
- Keep hook-managed commit metadata intact; never hand-edit it during merge work.
- Do not rebase, force-push, or bypass hooks.

## Preflight

1. Work only in the current worktree and branch. Never inspect another worktree or operate the coordinator checkout.
2. Confirm branch state:
   - `git branch --show-current`
   - `git status -sb`
3. If detached HEAD, create a descriptive `codex/` branch at the current HEAD and continue.
4. Otherwise, remain on the current branch. Do not create a worktree or switch branches. Read `main_ref` from `coloph-sync.toml`, set `MAIN_REF` to that value, and verify that it resolves to a local branch. If the current branch is that ref, stop; this skill is for contributor branches.
5. If the tree is dirty, finish and commit the work first.
6. If `git merge-base --is-ancestor "$MAIN_REF" HEAD` passes, the branch already includes configured local main; do not create a no-op merge.
7. If `HEAD` is `Sync-State: wip` or `Sync-State: failed`, do not attempt the merge or bypass its guard. First create a reviewed `Sync-State: dont-merge` scaffolding commit, then merge the configured local main branch; this is the path for a branch that cannot pass before main is integrated.

## Step 1: Read Both Histories From Shared Parent

1. Compute base:
   - `BASE=$(git merge-base HEAD "$MAIN_REF")`
2. Read branch intent first:
   - `git log --oneline --reverse "$BASE"..HEAD`
3. Read incoming main intent:
   - `git log --oneline --reverse "$BASE".."$MAIN_REF"`
4. Build a short intent map before touching files:
   - What broad refactors happened on branch?
   - What broad refactors happened on main?
   - Which shared modules are touched by both sides?

## Step 2: Merge

- Run: `git merge "$MAIN_REF" --no-edit`
- If merge succeeds cleanly, still run a semantic drift sweep (Step 4).
- If merge conflicts, continue to Step 3.

## Step 3: Semantic Conflict Workflow

1. List unresolved files:
   - `git diff --name-only --diff-filter=U`
2. For each conflict file, inspect both sides since base:
   - `git log --oneline "$BASE"..HEAD -- <file>`
   - `git log --oneline "$BASE".."$MAIN_REF" -- <file>`
3. Inspect introducing commits for intent:
   - `git show <sha> -- <file>`
4. Classify conflict type:
   - **Trivial**: formatting/import-order/same invariant, no behavioral divergence.
   - **Refactor-coupled**: one side changed architecture/contracts and the other added features on old assumptions.
   - **Human escalation**: ambiguous product behavior, incompatible migration order/data policy, or security/permission semantics you cannot infer safely.
5. Resolve by meaning, not by hunk:
   - Preserve required invariants from both sides.
   - Port new feature logic onto the current architecture.
   - Update adjacent call sites/tests if a resolved API contract changed.
   - Update configuration or migrations if another resolved contract changed.
   - Do not use `git checkout --ours`, `git checkout --theirs`, or `git checkout -- <file>` to select a whole-file side or discard content. Edit conflict markers explicitly with a patch and then `git add <file>`.

## Step 4: Refactor Drift Sweep (Both Directions)

After conflicts are text-resolved, check for semantic leftovers:

1. If branch refactored `X -> Y`, verify merged-in main commits did not reintroduce `X`.
2. If main refactored `A -> B`, verify branch-specific additions are migrated to `B`.
3. Use targeted `rg` searches for old symbols, deprecated tables/columns, old helper names, and old route/CLI contracts.
4. Fix drift immediately; do not defer obvious refactor fallout.

## Step 5: Validate and Commit

1. Run focused checks for touched areas.
2. Run the repository's required commit checks.
3. Re-check merge state:
   - `git status -sb`
4. For a merge commit, keep Git's generated `Merge branch ...` or `Merge
   branches ...` subject. Put semantic decisions in the commit body or required
   report, not `-m`. For a no-commit merge, run `git commit` without `-m` to
   accept the generated message.
5. Do not replace the generated subject or hand-edit hook-managed commit metadata.
6. After the passed merge commit, run `uv run coloph-sync status` for the new tip. A new conflict recorded for the new tip starts this workflow again.
7. If `sync-finish` sent you here, return to it after the repair commit.

## Step 6: Report (Required)

Report complex conflicts first, with commit evidence:

- Shared merge-base SHA.
- Branch-side commits that created the local intent.
- Main-side commits that created incoming intent.
- Why conflict was semantic (not only textual).
- Resolution chosen and why.
- Any escalation decisions.

Use this format:

- `Complex conflict: <area>`
- `Branch intent commits: <sha list>`
- `Main intent commits: <sha list>`
- `Semantic risk: <brief>`
- `Resolution: <brief>`
- `Escalation: <none|reason>`

Return to `sync-finish` in the same turn. Do not give a final user handoff from this workflow.
