---
name: coloph-sync-contributor
description: Commit work, repair a failed check, or resolve an integration conflict in a repository managed by coloph-sync. Use during branch development; use coloph-sync-finish for end-to-end closeout.
---

Keep work in the assigned branch. Read the repository's check and Git instructions.
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

Read `coloph-sync status`. A conflict belongs to the branch owner.
Follow the repository's Git procedure to integrate its local integration branch. Read both sides from their shared parent, preserve both intended behaviors, resolve the conflict, and run the relevant checks. Use a real merge; do not rebase or recreate selected changes.
Do not operate the coordinator while repairing your branch.
The coordinator attempts merges; it does not resolve conflicts or write repairs.
If the finish workflow sent you here, return to it after the repair commit.
