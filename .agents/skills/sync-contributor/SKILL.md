---
name: sync-contributor
description: Implement and commit contributor work in a repository managed by the sync coordinator, then hand it to sync-finish for integration, delivery, and closeout.
---

Before editing, determine whether the current checkout is the checkout where the sync coordinator runs.
That checkout is reserved for merging branches, running checks, and delivery.
A feature or bug-fix request does not authorize contributor edits there.
If asked to make such a change there, explain its role and ask the user to assign the task to a contributor checkout.
Proceed there only if the user explicitly authorizes contributor edits in that checkout.

Work only in the current worktree and branch. Never inspect another worktree.
Do not create another worktree or switch branches unless the user explicitly requests that operation.
If the provided worktree is detached, create a descriptive `codex/` branch at the current HEAD. This is the only automatic branch operation.
Setting a tool's working directory outside the current worktree does not bypass this boundary.
Never copy configuration or files from another worktree. Never delete a branch that you did not create.
Approval for one worktree does not grant access to another worktree.
Never force-push or use `git reset --hard`. Destructive cleanup requires explicit current user approval.
Read the repository's check and Git instructions.

Saving work means creating a commit. Finish with an ordinary passed commit; a WIP or failed checkpoint is not finished work. The reviewed `dont-merge` scaffold required by `sync-merge-main` is the exception when main must be integrated before the branch can pass.
The commit-msg hook owns check results. An ordinary commit needs no input marker.
Never copy a passed marker to avoid checks. The hook always checks ordinary commits.

For an intentional checkpoint, put `Sync-State: wip` on its own commit-body line.
For a checked scaffold, use `Sync-State: dont-merge`. It permits a later local merge but blocks integration at that tip.
For staged delivery, create an empty commit with `Sync-State: deploy-barrier` after the prerequisite commit.
Use a barrier when later work is safe only after the prerequisite is delivered, such as removing old database use before dropping the column, teaching a reader a new format before producing it, or publishing a package version before updating its consumer.
Do not combine states. The subject describes the change without control prefixes.

A check exit of 1 saves a failed commit. Read its diagnostic, repair the work, and create another ordinary commit.
A rejected hook does not create a commit. Repair the stated error and retry.
Do not bypass the hook or rewrite check results.

Read `uv run coloph-sync status`. A conflict belongs to the branch owner.
Load `sync-merge-main` and follow it completely when the current branch needs the configured local main branch or when the coordinator reports a merge conflict for the current tip. Read both histories from their shared parent, preserve both intended behaviors, resolve the conflict, and run the relevant checks. Use a real merge; do not rebase or recreate selected changes.
Do not operate the coordinator while repairing your branch.
The coordinator attempts merges; it does not resolve conflicts or write repairs.

## Required closeout handoff

After an ordinary passed commit, immediately use `sync-finish` in the same turn.
Do not give a final user handoff from this workflow.

Skip `sync-finish` only when the user explicitly pauses the task, requests a local-only commit, or tells you not to wait for integration or delivery.

If `sync-finish` sent you here for a repair, return to `sync-finish` after the repair commit. Continue the closeout workflow in the same turn.
