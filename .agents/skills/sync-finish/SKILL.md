---
name: sync-finish
description: Finish implemented work end to end in a repository managed by the sync coordinator. Use after branch work to own repair, integration, delivery validation, and complete closeout.
---

# Finish synchronized work

Start from the original request and the work performed in this task. The goal is to make the current branch merged into the configured main branch, delivered through the project's deployment command, and validated through the closest real user or operator path.

Keep closeout scoped to this branch's work. The latest user instructions and active issue are authoritative. Do not carry old reminder scope, unrelated branches, unrelated deployment failures, or earlier test targets into the result. When scope changes, update or delete any existing reminder before waiting again.

## Non-negotiable rules

- Start every closeout turn and reminder wakeup by loading this skill from the beginning.
- Work only in the current worktree and branch. Never inspect another worktree or the integration checkout.
- Do not create another worktree or switch branches unless the user explicitly requests that operation.
- If the provided worktree is detached, create a descriptive `codex/` branch at the current HEAD. This is the only automatic branch operation.
- Setting a tool's working directory outside the current worktree does not bypass this boundary. Approval for one worktree does not grant access to another worktree.
- Saving work means creating a commit. A failed checkpoint must have an ordinary passed successor before closeout.
- Run `uv run coloph-sync status` as the sole routine merge and deployment status check. Use its branch, tip, checks, phase, reason, merged, and deployed fields directly. Do not reconstruct or second-guess routine status with Git containment, tags, process inspection, or coordinator logs.
- Do not report completion while work is only locally clean or checks have only passed. Wait for both `Merged: yes` and `Deployed: yes` unless the user explicitly stops waiting.
- Do not operate or diagnose the coordinator from this skill. The operator workflow owns the designated integration checkout and coordinator process.
- A repairable failure is not a reporting boundary. Do not end the turn merely because status reports `merge failed`, `merge timed out`, invalid metadata, failed checks, or another concrete repairable failure. Follow the named repair workflow immediately, repair and commit the branch in the same turn, then restart this workflow. In particular, a merge failure or timeout means load and follow `sync-merge-main` in full now, resolve and validate the merge, then return here. Stop only for a genuinely unrepairable blocker that requires new user authority or unavailable external input, after exhausting safe in-scope repairs.
- If the branch tip changes unexpectedly, investigate and repair that problem. Do not select or continue tracking an older commit.
- If HEAD is an intentional `wip` checkpoint and the work is complete, create a normal reviewed empty commit on top (`git commit --allow-empty ...`) so the WIP diff is bundled into the check, then continue this workflow. Do not treat WIP state as a user-confirmation boundary.
- Report only this work's merge, deployment, and delivered-validation state. Keep hashes and internal deployment details out unless they explain a blocker.
- Do not inspect coordinator processes or logs, and do not run status with a wait, interval, or timeout option. Passive waiting happens through the reminder routine below, not a foreground process.

## Status and repair

Run:

```sh
uv run coloph-sync status
```

Then act on the current result:

- If checks failed or status reports `action needed`, repair the stated problem now through `sync-contributor`, then return here.
- Before waiting, use `sync-merge-main` whenever the configured main branch is needed for validation, compatibility, conflict repair, or closeout. If it is not needed, let the coordinator be the first merger; do not merge main merely for freshness.
- If a merge failed, timed out, or the branch needs the current main branch for conflict resolution or validation, load and follow `sync-merge-main` in full now, then return here after its validation and merge commit are complete.
- If the coordinator has not observed the current branch tip, keep waiting. This is ordinary pickup delay.
- If the last merge attempt was skipped or unchanged and `Merged: no`, stop waiting, repair the stated branch problem, then restart this workflow.
- If the coordinator reports an error while the branch is not both merged and deployed, stop passive waiting and report the recorded phase and error. Do not operate the coordinator.
- If the branch is already merged and deployed, a later unrelated coordinator error does not cancel delivered validation. A failed check for this branch still takes priority.
- If status reports a failure recorded for an ancestor after the branch tip changed, do not apply that old result to the new tip. Wait for the coordinator to observe the current tip; a failure newly recorded for that tip starts the relevant repair workflow again.

If status reports `metadata guard failed: ...`, treat the listed commits as the authoritative reason. The merge gate checks every commit in the range from the merge base with the configured main branch through the branch tip, not only HEAD. Every commit in that range must contain exactly one valid `Sync-State:` line. An older `wip` or `failed` commit in the range is not rejected solely because of that state, and a later passed commit does not repair missing or invalid metadata on an earlier commit. Repair the listed metadata without rewriting history when possible. If repair requires replacing branch history, preserve the current tip and get explicit same-turn user approval before doing it.

For passive waiting, a successful merge or a concrete failure changes the state. An unchanged pending result does not.

## Bounded reminders

Do not keep a foreground wait command running. Use a heartbeat attached to this task:

- Check every 5 minutes for the first 30 minutes.
- If still pending, update the same reminder to check every 30 minutes.
- Stop after 4 hours total unless the user gives fresh instructions to continue.
- Put the absolute expiry time and current branch/task scope in the reminder.
- Stay quiet while state is unchanged and non-actionable.

Never create or extend a finish reminder beyond that four-hour expiry unless the user gives fresh same-turn instructions to keep waiting. Every reminder instruction must start with this operational contract, adapted only by replacing the placeholders with concrete values:

> START BY LOADING AND FOLLOWING `sync-finish` FROM THE BEGINNING. Run exactly
> `uv run coloph-sync status`. Reminder expiry: `<absolute ISO timestamp>`. IF
> CURRENT TIME IS AT OR AFTER THAT EXPIRY AND THIS CHECK DOES NOT REPORT
> `Merged: yes` AND `Deployed: yes`, DELETE THIS REMINDER NOW, REPORT THAT THE
> PASSIVE WAIT WINDOW EXPIRED, AND DO NOT CONTINUE WAITING. IF IT REPORTS ANY
> FAILURE OR `action needed` BEFORE EXPIRY,
> DO NOT END THE TURN AND DO NOT JUST REPORT IT. FOLLOW `sync-finish`'s REPAIR
> WORKFLOW IMMEDIATELY (`merge failed` => RUN `sync-merge-main` NOW),
> FIX THE FAILURE, THEN RETURN TO `sync-finish`. IF THE OUTPUT SAYS `Sync loop
> phase: error` WHILE THIS BRANCH IS NOT BOTH `Merged: yes` AND `Deployed:
> yes`, DELETE THIS REMINDER, ALERT THE USER WITH THE RECORDED ERROR, AND STOP.
> IF BOTH ARE YES, CONTINUE THROUGH DELIVERED VALIDATION AND DO NOT OPERATE THE
> COORDINATOR, UNLESS THE PRINTED ACTION IS A CHECKS FAILURE; REPAIR THAT BRANCH
> FAILURE FIRST. IF THE CURRENT BRANCH TIP HAS NOT BEEN OBSERVED, CONTINUE
> WAITING. IF THE CURRENT TIP WAS SKIPPED OR UNCHANGED AND `Merged: no`, DELETE
> THIS REMINDER, REPAIR THE STATED BRANCH BLOCKER, THEN RESTART `sync-finish`
> FROM THE BEGINNING.

After that contract, state the current branch and task scope, validation instructions, time window, and explicit exclusions. When scope changes, update or delete the reminder before waiting again. Do not tell a reminder to stop and report a concrete repairable failure.

Each wakeup must:

1. Load this skill and run `uv run coloph-sync status` once.
2. If the clock is at or after the reminder expiry and status is not both `Merged: yes` and `Deployed: yes`, delete the reminder immediately, report that the passive wait window expired, and stop. Do not create another reminder or continue passive waiting without fresh same-turn user instructions.
3. If status reports a top-level coordinator error while this branch is not both merged and deployed, delete the reminder, alert the user with the recorded phase and error, and stop. If the branch is already merged and deployed, continue delivered validation unless checks failed.
4. If status reports another concrete failure or `action needed`, perform the repair in the same turn, then resume this workflow. Do not delete the reminder merely because repair is required; delete it only if the repair is genuinely blocked on new user authority or unavailable external input.
5. If the current tip remains pending without a failure, leave the reminder active and stay quiet. This is the only state in which the reminder may remain active.
6. If merge and deployment are complete, perform delivered validation and closeout in the same turn, then delete the reminder.
7. If validation finds follow-up work, delete this reminder before reporting it. New implementation needs a separately scoped task or reminder.

Delete reminders by calling the automation API. Do not merely say that a reminder should stop. A wakeup after successful closeout is stale and must delete its reminder without repeating validation.

When the current tip was skipped or unchanged with `Merged: no`, delete the reminder, repair the stated blocker, and restart this workflow from the beginning. When a merge failure is repairable, this transition happens inside the current turn: follow `sync-merge-main` in full, return after validation and the merge commit, and continue closeout. Never replace the real merge with copying, restoring, cherry-picking, or recreating selected files or commits.

When a reminder wakeup observes `Merged: yes` and `Deployed: yes`, it is not
done. In that same wakeup it must continue through Step 5 production smoke, then
Step 6 final executive summary. If the work is tied to an issue, follow the repository's issue-closeout rules after validation. Do not close an issue merely because deployment completed. Delete the reminder automation only after merge,
deploy, production smoke, and any in-scope issue closeout are complete. A
completion wakeup must not answer with only a terse scheduler status such as
“complete”; include the concise Step 6 handoff first.

## Step 5: Validate delivery

After both merge and deployment, follow the repository's relevant validation procedure. Test the changed behavior through the closest safe real user or operator path, not merely a health check or another local test. Examples include exercising the deployed UI, calling the supported deployed CLI or API, or observing the real runtime behavior and logs.

The validation must prove the requested behavior. If a real delivered test is unsafe or unavailable, state why and run the closest safe equivalent. Include a concrete manual test with its expected result. Include the exact review URL when a meaningful user-visible URL exists; otherwise say why there is none.

Run performance measurements only when the change affects performance-sensitive paths or the request requires them. Treat unrelated production failures as separate evidence, not failures of this work.

If the work is tied to an issue, follow the repository's issue-closeout rules after validation. Do not close an issue merely because deployment completed.

## Step 6: Final Executive Summary

Keep the final handoff concise and assume the reader has no prior chat context. Inspect the whole task and branch history for remaining scope, including later commits held behind a deployment barrier. Report exactly:

1. `Requested scope:` Start with the earliest user-stated outcome in the continuous workstream, then trace every material expansion, narrowing, superseded decision, and explicit deferral in causal order. Do not substitute the final commit, selected issue, configuration change, final authorization, or latest implementation slice for the earlier problem the user asked to solve. Explain it in product or business terms; identifiers are traceability only.
2. `Delivered scope:` State what was implemented and delivered, including checks, `MERGED` / `NOT MERGED`, `DEPLOYED` / `NOT DEPLOYED`, delivered validation, and anything intentionally not implemented, deferred, superseded, or out of scope.
3. How the user can test it manually, with expected results and any relevant review URL.
4. Work still remaining, blocked validation, barrier-held successors, the responsible follow-up, and the next safe action.

Reconcile every major requested outcome as delivered, partially delivered, blocked, deferred, superseded, or intentionally out of scope. Include the initial objective, decisions and discoveries that changed the route, and what the latest work changed in business terms. Do not claim completion while any requested outcome, required validation, or barrier-held successor remains unresolved. Avoid long commit lists, hash-heavy status, internal deployment mechanics, and repetition of completed subtasks.

End with either `Next action: ...` or `Everything requested here is implemented, there are no follow-ups, and this chat is safe to close.`
