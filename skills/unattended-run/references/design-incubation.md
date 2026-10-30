# Design-incubation continuity

Use this only while `design-doc` owns a systemic or critical work order that is
not yet approved and is likely to outlast the current attended turn.

## Durable state

Persist this state in the work order or its linked design baton:

```yaml
design_incubation:
  status: active
  cycle: 1
  objective_file: <design-objective-file>
  reminder:
    kind: design_progress
    id: PENDING_CREATION
    interval: 30m
    status: pending
```

Allowed status values are `active`, `waiting_user`, `handoff_pending`,
`approved`, `abandoned`, `redirected`, and `reframed`. `design-doc` owns status
transitions. The reminder reads status before acting.

## Objective

Persist a concise objective body without a slash-command prefix:

> Continue the design work order at `<DESIGN_DOC>` in `<WORKSPACE>`.
> Read `<DECISION_RECORD>` and preserve its exact user authority.
>
> Design cycle: `<DESIGN_CYCLE>`.
>
> Outcome: finish `design-doc` through the current two-pass constraint
> challenge and two-family design review, then present the approved work order.
> Do not implement the proposed system during this cycle.
>
> Advance every ready design or review action. Consume completed owner results
> through their explicit result channel. Do not duplicate an active owner or
> replace unrelated objective or schedule state.
>
> This cycle is complete when the design is approved, abandoned, redirected,
> reframed, or its durable status becomes `waiting_user` because no independent
> action remains.

Include the persisted integer cycle in the objective text. Each resumed cycle
increments and persists it before delivery, creating a new canonical objective
and deduplication identity.

## Reminder

Create one reminder:

```text
manage_schedule action=create interval=30m \
  prompt="Read <DESIGN_DOC> and its design_incubation state. Finish any
  coherent edit already underway before acting. If status is active, inspect
  explicit challenge and review owner results and advance the next ready
  design action. The native design objective is the primary loop; this reminder
  is only its liveness and recovery backstop. Do not implement, duplicate an
  active owner, infer owner state from files, replace unrelated state, or
  repeat a pending user-only question. If status is waiting_user, remain
  stopped by stopping this recorded reminder, verifying its absence, and
  persisting its stopped status without repeating the question. If status is
  handoff_pending, repair or complete the development-loop handoff and keep
  this reminder until replacement continuity is confirmed. If status is
  approved, abandoned, redirected, or reframed, stop this recorded reminder
  and verify its absence."
```

Persist the returned ID and `live` status immediately. Reuse a matching
objective and reminder independently. Create whichever compatible mechanism is
missing. If an unrelated native objective is active, leave it in place and
follow its governing process or an explicit user redirect.

Deliver the objective through `scripts/enqueue-autopilot.sh` as the final tool
action of the turn. Require its receipt to prove the exact cycle's native
objective and `idle` or `steering` activation. A completed receipt for an older
cycle does not activate the new cycle.

## User-only suspension

When a genuine user-only decision leaves no independent action ready:

1. persist the exact question and set status to `waiting_user`;
2. stop and verify removal of the design reminder;
3. let the current objective cycle finish on `waiting_user`; and
4. ask once with the context needed to answer.

After a later user turn makes work ready, set status to `active`, increment and
persist the cycle, recreate any missing reminder, and deliver the new objective.
Do not accept an older deduplicated receipt as activation.

## Approval and handoff

Persist terminal status before cleanup for abandonment, redirection, or
reframing. On approval without implementation authority, persist `approved`,
stop and verify the reminder, record it stopped, and present the work order.

When an existing instruction authorizes implementation:

1. persist `handoff_pending`;
2. return the approved work order to `development-loop`;
3. let `development-loop` choose attended or unattended execution;
4. for attended work, stop the design reminder, persist `approved`, and
   continue without the normal unattended pair;
5. for unattended work, create and confirm the normal hourly progress and
   four-hour charter reminders before stopping the design reminder;
6. persist an `implementation_objective_handoff` record in the implementation
   charter with a unique `handoff_id`, `status: prepared`, the objective file,
   target session, the SDK request's canonical deduplication identity, and
   `receipt: null`;
7. verify the normal pair for that implementation charter is live and the
   design reminder is absent, leaving unrelated schedules untouched;
8. persist `approved`; and
9. deliver the implementation objective through the existing SDK helper as the
   final action of the turn.

A reminder observing `handoff_pending` repairs or completes this sequence. It
stops only after `development-loop` selects attended execution or the normal
unattended pair is confirmed.

If implementation-objective delivery is interrupted after the normal pair is
live, keep that pair and leave the design reminder stopped. A normal reminder
repairs the handoff from its durable state:

- for `prepared`, first verify native objective state and inspect the SDK
  request store using the recorded deduplication identity. Record a matching
  in-flight request as `submitted`; when no matching request or active
  objective exists, submit it once. The SDK deduplication identity makes a
  concurrent original submission converge on the same request;
- for `submitted`, wait for its receipt to become terminal, then verify native
  objective state; and
- record `resolved` with the terminal receipt when delivery is confirmed.

After a terminal failed receipt, verify the exact canonical objective and
require native activation evidence of `idle` or `steering` before recording
`resolved`. Objective presence without that activation proof is not resolved.
Otherwise preserve the receipt, persist `fallback_pending` with the exact
fallback text, its digest, and a unique `fallback_notice_id` derived from the
handoff ID and terminal receipt digest. Include that notice ID in the printed
fallback and record the pending event or turn identity, then print the fallback
as the final response.

On a later tick, reconcile `fallback_pending` against the session transcript.
Record `fallback_delivered` only when a delivered assistant turn after the
pending event contains the same `fallback_notice_id` and exact fallback digest.
An earlier identical fallback cannot satisfy the current handoff. When delivery
is absent or cannot be proved, print the same identified fallback again and
leave `fallback_pending`; this favors an occasional duplicate over losing the
only recovery instruction. Never
automatically retry a terminal failure with the same deduplication identity;
an `ambiguousSideEffect` receipt permanently blocks that identity. Never wait
for a receipt that was not submitted.
