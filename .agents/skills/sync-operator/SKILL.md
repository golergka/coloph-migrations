---
name: sync-operator
description: Operate and continuously supervise the sync coordinator in its designated checkout, including recovery and operator reminders. Contributors use sync-contributor or sync-finish.
---

Operate only the checkout where the sync coordinator runs, with repository authorization.
That checkout is reserved for merging branches, running checks, and delivery.
A feature or bug-fix request does not authorize contributor edits there.
If asked to make such a change there, explain its role and ask the user to assign the task to a contributor checkout.
Proceed there only if the user explicitly authorizes contributor edits in that checkout; then use `sync-contributor`.
Invoking this skill in that checkout authorizes normal coordinator operations, including starting or resuming it.
Do not ask for additional approval for operations within these worktree boundaries.
Explicit user authorization is required only for an exception to those boundaries.
Contributor worktrees belong to their assigned agents. Never inspect, modify, enter, or operate their files or processes.
Use branch refs, coordinator status, and merge results to integrate their work. A conflict belongs to the worktree owner.
Do not create or switch worktrees. Access to another checkout requires explicit user authorization.
Approval for the integration checkout does not grant access to contributor worktrees.

## Start and supervise

On invocation, start or resume continuous operation unless the user requests inspection, stopping, or a single cycle.
Check the current checkout, configured main branch, clean working tree, and project prerequisites before starting.
Read the project's check and delivery instructions. Do not substitute weaker checks or deployment procedures.
Check for an existing coordinator in this checkout before starting another instance.
Keep a healthy existing instance. The shared repository lock prevents concurrent coordinators.
Never start a separate deployment alongside the coordinator.

Run `uv run coloph-sync run` as the foreground child of a known supervisor. The supervisor can be an attached terminal, a detached terminal multiplexer, or a service manager.
Keep the exact terminal session or service identity so you can supervise that instance.
If a tool wait times out, check the same instance before restarting. A tool timeout does not prove process exit.
For detached operation, use the project's launcher or a terminal multiplexer without attaching to it.
Use the project's sleep-prevention mechanism on hosts that can sleep. Do not duplicate an existing sleep assertion.

## Operator reminder

Before ending a turn with continuous operation active, create or reuse a recurring operator reminder on this task.
Use the host's automation tool. Default to every 15 minutes unless the user specifies another interval.
Check existing reminders first. Keep only one operator reminder for this task and checkout.
Check the saved reminder's task destination, checkout, schedule, and instructions after creation or update.
If reminders are unavailable, keep supervising the foreground session and report that limitation.
Do not end supervision merely because one cycle succeeded or delivery is still pending.

Include these instructions in the reminder, with the actual task, checkout, and process or service identity:

> Created for agent/task: <operator task and checkout>.
> Load `sync-operator` at every wakeup. Supervise only this checkout's coordinator.
> Check the owned instance, `uv run coloph-sync status --all`, and `uv run coloph-sync logs`.
> If the instance is absent unexpectedly or has a new failure, follow the recovery instructions in this skill.
> Respect the latest user stop request. Never restart after that request.
> Preserve worktree boundaries and existing repair authorization.
> Report state changes and actionable failures. Stay quiet while healthy or while an unchanged repair continues.
> Continue until the user stops operation or a concrete blocker prevents recovery.

An operator reminder supervises the service continuously. It does not expire after an individual branch deploys.
If a wakeup targets another task or checkout, do not operate that checkout.
Report the routing mismatch instead of executing unrelated instructions.

## Stop and recover

Use `uv run coloph-sync stop` to finish the current cycle and prevent another cycle.
On a user stop request, delete the operator reminder so it cannot restart the loop.
Check that the saved reminder is gone. Wait for the owned process to exit before reporting it stopped.

While the coordinator owns the checkout you must not:

- edit, create, or delete ANY file in the repo
- run `git checkout`, `git reset`, `git merge`, `git rebase`, `git commit`, `git push`, `git pull`, `git restore`, `git stash`, or any other state-changing Git command
- run another coordinator cycle or a standalone delivery command
- run scripts that mutate project configuration, coordination refs, reports, logs, locks, or any other file the coordinator writes

Read-only inspection (`git status`, `git log`, `ls`, `cat`, `ps`) is fine; mutation is not.
If you need to do ANYTHING that violates the above (fix a bug, edit a doc, commit a change, even something small), stop the coordinator, wait for the owned process to exit, and verify that it has exited before doing the work.
There is no "I'll be quick" exception. Stop, work, restart.
Read `uv run coloph-sync logs` and `uv run coloph-sync status --all` for evidence.

A failed cycle stops the loop. Investigate its recorded phase and output.
Branch conflicts and invalid metadata leave that branch out; other eligible branches continue.
Check failures stop the cycle. Contributor conflicts belong to their branch owners.
The coordinator merges branches into the configured main branch. It never merges main back into contributor worktrees.
The coordinator never creates implementation or repair commits. Its only commits are commits produced by merging ready branches into the configured main branch.
When a failed cycle requires a code, test, documentation, or tooling fix in the integration checkout, stop the coordinator and obtain or confirm contributor-repair authorization before making a normal reviewed commit. Never leave an uncommitted repair for a later cycle to collect: the coordinator does not stage or commit working-tree changes.

For persistent branch failures:

1. **Identify the conflicting commits.** Read all commits from the merge base to the branch tip, not just the tip.
2. **Understand intent.** Read commit messages and diffs. What was each side trying to accomplish?
3. **Check for semantic conflicts.** Two changes can merge cleanly yet be logically incompatible:
   - A function signature changed on main but a new caller on the branch uses the old signature
   - A config key was renamed on one side and referenced on the other
   - A migration depends on a table/column that another migration dropped
   - An import was added for something that was moved/deleted on the other side
4. **Escalate to the agent working in that worktree when possible** — they have context you don't. Do not inspect or modify that worktree; use branch refs, commit history, and confirmed task ownership.

Report the conflict and the evidence from all relevant commits to the branch owner.
A deployment barrier can delay successors while its parent deploys. This is pending work, not a failure.
Do not bypass a barrier or move coordination refs to admit its successors.
If the pre-barrier merge errors, the report records the attempted parent, the barrier SHA, and the original merge error. The branch owner must recreate the repair before the barrier on a new branch; commits after the marker remain ineligible until the pre-barrier phase merges and deploys.

Branches whose tips are `wip`, `failed`, or `dont-merge` are skipped while other eligible branches continue.
WIP and failed tips cannot be used as the starting point of a merge. A checked `dont-merge` scaffold permits a subsequent local merge but cannot itself be integrated at the tip.
Once the branch owner creates a later eligible checked commit, integration resumes automatically. Older `wip`, `failed`, and `dont-merge` commits do not block that later eligible tip.

Diagnose failed checks through the project's prescribed workflow. Never skip or weaken a check to continue.
For an authorized contributor repair here, stop the coordinator and use `sync-contributor`.
Create a normal checked repair commit before resuming. Never leave an uncommitted repair for the loop to collect.
Without that repair authorization, report the required contributor work and the responsible checkout.
After a coordinator repair, keep the continuous loop stopped. Record `uv run coloph-sync --json status --all`, then run exactly one `uv run coloph-sync run --once`. This recovery cycle performs its one delivery attempt before normal looping resumes; do not run another deploy command or start the continuous loop alongside it. If that cycle fails, recover the new recorded failure instead of re-enabling the loop.
After that recovery cycle succeeds, compare `uv run coloph-sync --json status --all` with the saved pre-recovery status. Identify every branch newly reported as deployed, every branch with a newly recorded rejection, and every branch newly reported as `action needed`. When operating in Codex, find the task responsible for each identified branch from its confirmed branch assignment or task history. Send a deployed task `The coordinator failed, but was fixed. Your branch has been deployed.` Send a rejected task `The coordinator failed, but was fixed. Your branch has been rejected.` For `action needed`, report that exact verdict, its reason, and the repair the branch owner must perform; never describe `action needed` as rejection. Do not guess a task-branch association or message an unrelated task; report an unassigned branch instead.
Only after this notification pass, resume normal continuous operation unless the user requested a single cycle or stopped operation.
After three failed repair attempts for the same cause, report the blocker and stop automatic retries.
Delete the operator reminder when recovery requires unavailable input or new authority.

Report push failures, including failures that recover. Retry a transient network failure once.
For authentication failures, report the concrete error immediately.
For a rejected non-fast-forward push, stop and report the exact push error and current local and remote configured-main heads. Never force-push or rewrite history to continue.
Report deployment failures even if recovery is possible. A failed deployment can leave remote changes in place.
Use the project's recovery procedure to reconcile remote work before retrying.
An interrupted external operation may already have taken effect. Resume through the same coordinator so the configured project command can reconcile it; do not start a competing delivery operation or move coordinator-owned refs manually.
Use `uv run coloph-sync run --push-deploy-only` only to check and deliver the current integration branch without admitting worktree branches; it does not replace the one recovery cycle above.
The coordinator does not resolve conflicts or perform automatic rollback.
After each fix, report what broke and how you fixed it before re-launching.
