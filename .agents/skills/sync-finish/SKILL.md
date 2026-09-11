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
- If the provided worktree is detached, create a descriptive `codex/` branch at its current HEAD. This is the only automatic branch operation.
- Setting a tool's working directory outside the current worktree does not bypass this boundary. Approval for one worktree does not grant access to another worktree.
- Saving work means creating a commit. A WIP or failed checkpoint must have an ordinary passed successor before closeout.
- Run `uv run coloph-sync status` as the sole routine merge and deployment status check. Use its branch, tip, checks, phase, reason, merged, and deployed fields directly. Do not reconstruct or second-guess routine status with Git containment, tags, process inspection, or coordinator logs.
- Do not report completion while work is only locally clean or checks have only passed. Wait for both `Merged: yes` and `Deployed: yes` unless the user explicitly stops waiting.
- Do not operate or diagnose the coordinator from this skill. The operator workflow owns the designated integration checkout and coordinator process.
- A repairable failure is not a reporting boundary. Follow `sync-contributor`, repair and commit the branch in the same turn, then restart this workflow. Stop only when repair requires new user authority or unavailable external input.
- If the branch tip changes unexpectedly, investigate and repair that problem. Do not select or continue tracking an older commit.
- If HEAD is an intentional `wip` checkpoint, create a normal checked commit after completing the work. Do not treat WIP state as a user-confirmation boundary.
- Report only this work's merge, deployment, and delivered-validation state. Keep hashes and internal deployment details out unless they explain a blocker.

## Status and repair

Run:

```sh
uv run coloph-sync status
```

Then act on the current result:

- If checks failed or status reports `action needed`, repair the stated problem now through `sync-contributor`, then return here.
- If a merge failed, timed out, or the branch needs the current main branch for conflict resolution or validation, follow the repository's merge procedure through `sync-contributor`, then return here.
- If the coordinator has not observed the current branch tip, keep waiting. This is ordinary pickup delay.
- If the last merge attempt was skipped or unchanged and `Merged: no`, stop waiting, repair the stated branch problem, then restart this workflow.
- If the coordinator reports an error while the branch is not both merged and deployed, stop passive waiting and report the recorded phase and error. Do not operate the coordinator.
- If the branch is already merged and deployed, a later unrelated coordinator error does not cancel delivered validation. A failed check for this branch still takes priority.

For passive waiting, a successful merge or a concrete failure changes the state. An unchanged pending result does not.

## Bounded reminders

Do not keep a foreground wait command running. Use a heartbeat attached to this task:

- Check every 5 minutes for the first 30 minutes.
- If still pending, update the same reminder to check every 30 minutes.
- Stop after 4 hours total unless the user gives fresh instructions to continue.
- Put the absolute expiry time and current branch/task scope in the reminder.
- Stay quiet while state is unchanged and non-actionable.

Each wakeup must:

1. Load this skill and run `uv run coloph-sync status` once.
2. If the deadline passed without both merge and deployment, delete the reminder and report expiry.
3. If the branch needs repair, perform the repair in the same turn, then resume this workflow.
4. If the current tip remains pending without a failure, leave the reminder active and stay quiet.
5. If merge and deployment are complete, perform delivered validation and closeout in the same turn, then delete the reminder.
6. If validation finds follow-up work, delete this reminder before reporting it. New implementation needs a separately scoped task or reminder.

Delete reminders by calling the automation API. Do not merely say that a reminder should stop. A wakeup after successful closeout is stale and must delete its reminder without repeating validation.

## Validate delivery

After both merge and deployment, follow the repository's relevant validation procedure. Test the changed behavior through the closest safe real user or operator path, not merely a health check or another local test. Examples include exercising the deployed UI, calling the supported deployed CLI or API, or observing the real runtime behavior and logs.

The validation must prove the requested behavior. If a real delivered test is unsafe or unavailable, state why and run the closest safe equivalent. Include a concrete manual test with its expected result. Include the exact review URL when a meaningful user-visible URL exists; otherwise say why there is none.

Run performance measurements only when the change affects performance-sensitive paths or the request requires them. Treat unrelated production failures as separate evidence, not failures of this work.

If the work is tied to an issue, follow the repository's issue-closeout rules after validation. Do not close an issue merely because deployment completed.

## Final report

Inspect the whole task and branch history for remaining scope, including later commits held behind a deployment barrier. Report exactly:

1. Work directly completed, checks, merge state, deployment state, and delivered validation.
2. How the user can test it manually, with expected results and any relevant review URL.
3. The original requested scope and every material expansion, narrowing, superseded decision, or explicit deferral.
4. Work still remaining, blocked validation, barrier-held successors, and the next responsible action.

Reconcile every major requested outcome as delivered, partially delivered, blocked, deferred, superseded, or intentionally out of scope. Do not claim completion while any requested outcome, required validation, or barrier-held successor remains unresolved.

End with either `Next action: ...` or `Everything requested here is implemented, there are no follow-ups, and this chat is safe to close.`
