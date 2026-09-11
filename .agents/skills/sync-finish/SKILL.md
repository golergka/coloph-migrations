---
name: sync-finish
description: Finish an implemented change end to end in a repository managed by the sync coordinator. Use for closeout after branch work; it owns waiting, delivery confirmation, manual test guidance, and remaining-scope review.
---

Start from the original request in this chat and the work you directly performed. Identify every requested outcome before checking delivery.

Work only in the current worktree and branch. Never inspect another worktree or the integration checkout.
Do not create another worktree or switch branches unless the user explicitly requests that operation.
If the provided worktree is detached, create a descriptive `codex/` branch at the current HEAD. This is the only automatic branch operation.
Setting a tool's working directory outside the current worktree does not bypass this boundary.
Approval for one worktree does not grant access to another worktree.
Saving work means creating a commit. A WIP or failed checkpoint must have an ordinary passed successor before closeout.
Do not operate the coordinator from this workflow.

Run `uv run coloph-sync status` for the current branch, or select the intended commit explicitly. Distinguish integrated from delivered. A successful local commit is not completed work.
Repair actionable branch failures through `sync-contributor`, then return here. If the coordinator has not checked the repaired tip, wait; do not treat the older failure as current.

Use a sparse host reminder when integration or delivery is pending. Check once per wakeup and stay quiet while the state is unchanged. Stop the reminder when delivery completes, waiting expires, or work is blocked. Expiry ends passive waiting; it does not cancel an already authorized repair.

After delivery, follow the repository's relevant validation procedure. Always tell the user how to test the delivered behavior manually, with concrete steps and expected results, whether or not you could perform that test yourself. A delivery record proves historical success, not current health.

Inspect the whole chat and the branch history for remaining work. Include later commits held behind a delivery barrier: delivery of the prerequisite does not complete its successors.

Report exactly these four parts:

1. Work directly completed, including verification and delivery state.
2. How the user can test it manually, including expected results.
3. Original scope of the chat and material changes to that scope.
4. Work still remaining, including blocked tests, barrier-held work, and the next action.

Do not claim completion while any requested outcome, required validation, or barrier-held successor remains unresolved.
