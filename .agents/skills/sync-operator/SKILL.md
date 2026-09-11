---
name: sync-operator
description: Start, stop, inspect, or recover the sync coordinator. Use only when assigned to operate the designated integration checkout; contributors use sync-contributor or sync-finish.
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
Run `uv run coloph-sync run` in the foreground. A terminal multiplexer or service manager can host it.
Use `uv run coloph-sync stop` to finish the current cycle and prevent another cycle.
Do not edit the checkout while the coordinator owns it. Wait for its process to exit.
Read `uv run coloph-sync logs` and `uv run coloph-sync status --all` for evidence.

A failed cycle stops the loop. Investigate its recorded phase and output.
Branch conflicts and invalid metadata leave that branch out; other eligible branches continue.
Check failures stop the cycle. Contributor conflicts belong to their branch owners.
An interrupted external operation may already have taken effect. Resume through the same coordinator so the configured project command can reconcile it; do not start a competing delivery operation or move coordinator-owned refs manually.
Use `uv run coloph-sync run --once` for recovery. Use `uv run coloph-sync run --push-deploy-only` only to check and deliver the current integration branch without admitting worktree branches.
The coordinator does not resolve conflicts or perform automatic rollback.
