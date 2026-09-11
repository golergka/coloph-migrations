---
name: coloph-sync-finish
description: Finish an implemented change end to end in a repository managed by coloph-sync. Use for closeout after branch work; it owns waiting, delivery confirmation, manual test guidance, and remaining-scope review.
---

Start from the original request in this chat and the work you directly performed. Identify every requested outcome before checking delivery.

Run `coloph-sync status` for the current branch, or select the intended commit explicitly. Distinguish integrated from delivered. A successful local commit is not completed work.
Repair actionable branch failures through `coloph-sync-contributor`, then return here. If the coordinator has not checked the repaired tip, wait; do not treat the older failure as current.

Use `coloph-sync wait --commit <sha>` for a short foreground wait. For a long or externally timed wait, use sparse host reminders: check once per wakeup, stay quiet while unchanged, and stop the reminder when delivery completes, waiting expires, or work is blocked. Expiry ends passive waiting; it does not cancel an already authorized repair.

After delivery, follow the repository's relevant validation procedure. Always tell the user how to test the delivered behavior manually, with concrete steps and expected results, whether or not you could perform that test yourself. A delivery record proves historical success, not current health.

Inspect the whole chat and the branch history for remaining work. Include later commits held behind a delivery barrier: delivery of the prerequisite does not complete its successors.

Report exactly these four parts:

1. Work directly completed, including verification and delivery state.
2. How the user can test it manually, including expected results.
3. Original scope of the chat and material changes to that scope.
4. Work still remaining, including blocked tests, barrier-held work, and the next action.

Do not claim completion while any requested outcome, required validation, or barrier-held successor remains unresolved.
