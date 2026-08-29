# Architecture invariants

These invariants are enforced mechanically. When a guard fails, restore the
stated rule or follow the guardrails amendment process before changing its
scope.

| ID | Invariant | Source | Owner | Guard |
| --- | --- | --- | --- | --- |
| INV-001 | Runtime skills, scripts, and extensions never submit Copilot messages or slash commands through the FIFO queue; they use direct command invocation or immediate SDK delivery and reject observed queued delivery. | `skills/mailbox/SKILL.md` immediate wakeup contract; `skills/unattended-run/references/cli-autopilot.md` native autopilot contract | `extensions/session-inbox/` | `scripts/check-no-enqueue.mjs`, run by `.github/workflows/no-enqueue.yml` and the repository pre-commit hook |
