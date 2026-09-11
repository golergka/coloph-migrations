---
name: coloph-sync-operator
description: Start, stop, inspect, or recover the coloph-sync coordinator. Use only when assigned to operate the designated integration checkout; contributors use coloph-sync-contributor or coloph-sync-finish.
---

Operate only the designated integration checkout with repository authorization.
Run `coloph-sync run` in the foreground. A terminal multiplexer or service manager can host it.
Use `coloph-sync stop` to finish the current cycle and prevent another cycle.
Do not edit the checkout while the coordinator owns it. Wait for its process to exit.
Read `coloph-sync logs` and `coloph-sync status --all` for evidence.

A failed cycle stops the loop. Investigate its recorded phase and output.
Branch conflicts and invalid metadata leave that branch out; other eligible branches continue.
Check failures stop the cycle. Contributor conflicts belong to their branch owners.
An interrupted external operation may already have taken effect. Resume through the same coordinator so the configured project command can reconcile it; do not start a competing delivery operation or move coordinator-owned refs manually.
Use `coloph-sync run --once` for recovery. Use `coloph-sync run --push-deploy-only` only to check and deliver the current integration branch without admitting worktree branches.
The coordinator does not resolve conflicts or perform automatic rollback.
