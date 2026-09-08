# Legacy schedule rollback

**Rollback only.** These retired templates exist solely to reverse a completed
event-driven governance migration. Do not use them for a new charter or as the
normal unattended-run default.

Create and confirm the prior schedules before stopping the four-hour liveness
schedule. Restore their registry entries with the returned identifiers. If
either prior schedule cannot be confirmed, leave the liveness schedule live.

The former two-hour charter recovery schedule was:

```text
manage_schedule action=create interval=2h \
  prompt="If you are currently making a user-directed edit to the plan, design
  doc, brief, or charter, finish the current coherent edit and persist it first.
  Then re-read your autopilot charter at <charter-path> and its current plan
  baton. Never replace an in-flight revision with the older persisted version.
  List active schedules and reconcile them against the charter registry. Stop
  duplicate charter reminders. For systemic or critical work, a missing,
  duplicated, or replacing challenge schedule makes the challenge due before
  the registry reset transaction repairs it.
  Follow the charter's Required process skills protocol exactly and reconcile
  the current work against it; execute any skill invocation or compaction
  action the charter says is due now rather than merely acknowledging it. Run
  /dfrysinger-skills:development-loop's critical-path audit: rebuild ready work
  and dependencies, reconcile every delegated owner and blocker from that
  agent's session or coordination channel rather than its worktree, consume
  completed handoffs, record silent owners as unknown and request status once,
  assign every independent ready scope that can run safely in parallel, batch
  work before expensive gates, and advance another ready item during waits.
  Confirm the workspace, push policy, objective, current phase, proof gates,
  and any open constraint revisit or reframe condition, and correct any drift
  before continuing. For systemic or critical work, inspect the persisted
  constraint-challenge record, persist relevant user statements in the durable
  decision record or baton quote ledger with stable event IDs, exact quotes,
  and context, and compare the exact next action with gate_status,
  permitted_scope, and blocked_scope. Do not advance under a BLOCKED gate or
  outside a PARTIAL gate's permitted scope. If development-loop reports an
  event-triggered challenge due, run it rather than merely acknowledging it.
  After it returns, use the registry reset transaction to replace the
  eight-hour constraint schedule once, compare the new gate with the exact next
  action again, and stop if it no longer permits that action. During active
  live proof, remain read-only and advance only work that cannot mutate the
  candidate, its worktree, its fixture, or its running process. Stop this
  schedule once the charter's referenced Definition of Done is verifiably met
  by stopping every schedule identifier in the charter registry plus any live
  schedule pointed at this charter, then verifying their absence."
```

For systemic or critical work, the former eight-hour independent challenge
schedule was:

```text
manage_schedule action=create interval=8h \
  prompt="Re-read the unattended-run charter at <charter-path> and its current
  plan baton. If a user-directed edit to the plan, design doc, brief, or charter
  is in flight, finish and persist that coherent edit first. If active live
  proof is in progress, do not mutate its candidate, worktree, fixture, or
  process; complete that proof, then service this challenge before further
  mutating work. If the referenced Definition of Done is already met, stop
  every schedule identifier in the charter registry plus any live schedule
  pointed at this charter, then verify their absence. Otherwise collect
  relevant user statements since the prior review as exact contextual quotes,
  invoke /dfrysinger-skills:constraint-challenge now, and persist its complete
  durable record. Compare the exact next action with the new gate and stop work
  that it blocks. This is the periodic challenge tick; leave this recurring
  schedule in place."
```

Restore the former registry shape:

```yaml
schedule_registry:
  charter_rebrief:
    id: <RETURNED_2H_ID>
    interval: 2h
    status: live
  constraint_challenge:
    id: <RETURNED_8H_ID>
    interval: 8h
    status: live
    armed_at: <CREATED_AT>
    generation: <PRIOR_OR_NEXT_GENERATION>
    reset_after_reviewed_at: null
```

Omit `constraint_challenge` for a run that was not systemic or critical.
