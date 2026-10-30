# Design incubation continuity

Revision: `design-incubation-continuity-v3`

## Objective

Keep a new systemic or critical task moving through design drafting and review
when the session starts without a compatible autopilot objective or progress
reminder.

## Non-goals

- Do not start implementation before `design-doc` completes.
- Do not create a scheduler, service, extension, or second objective transport.
- Do not arm the normal hourly and four-hour unattended reminders before an
  approved work order exists.
- Do not replace an unrelated active objective or stop unrelated schedules.
- Do not launch duplicate challenge or review attempts while their current
  owners are still active.
- Do not repeatedly ask the user for the same genuine user-only decision.

## Lane

**Systemic.** This changes the shared lifecycle between `design-doc` and
`unattended-run`, including native objective state and recurring schedule
ownership.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit when |
|---|---|---|---|
| `design-doc` remains the governing skill until approval | Existing skill ownership boundary | Scope and architecture gates | Another workflow becomes the design authority |
| `unattended-run` owns objective delivery and schedules | Existing SDK helper and schedule lifecycle | One implementation of session continuity | The CLI provides a simpler native design-phase API |
| Use one temporary reminder | The gap is design progress, not full run governance | Cost and duplicate-work prevention | Evidence shows design work also needs periodic charter reconciliation |
| Use a 30-minute default | User requested a 20-30 minute push; 30 minutes is the lower-cost end | Timely recovery without excessive turns | Measured review latency shows a different cadence is better |
| Do not overwrite unrelated objective state | Existing replace-don't-accumulate rule | The task already in progress | The user explicitly redirects or cancels that task |
| Stop or replace temporary state at a terminal design event | Existing schedule cleanup contract | No stale reminders after approval or abandonment | Native objectives gain scoped child lifetimes |

## Reframe gate

`CLEAR`.

The existing objective handoff and schedule manager can provide this behavior.
No new runtime component or authority is required. Reframe before adding a
service, background daemon, second objective store, or parallel review
coordinator.

## Reuse contract

`design-doc` owns when the temporary phase starts and what counts as design
approval. `unattended-run` owns how the current session receives a native
objective and how the reminder is created, recorded, reconciled, and stopped.
The existing `enqueue-autopilot.sh` helper remains the only objective transport.
The existing `manage_schedule` tool remains the only reminder mechanism.

The change adds a design-incubation mode to these existing skills. It does not
add executable runtime code.

The native design objective is the primary progress loop. The 30-minute
reminder is a liveness and recovery backstop for failed objective delivery,
stalled continuation, or stale design state, not a second primary loop.
Thirty minutes is the selected lower-cost end of the user-authorized 20-30
minute range, not an externally mandated interval.

## Durable design status

The work order carries exactly one current `design_status`:

- `active`
- `waiting_user`
- `handoff_pending`
- `approved`
- `abandoned`
- `redirected`
- `reframed`

The `design-doc` owner persists every status transition before changing
objectives or schedules. The reminder checks this status before advancing work.
`waiting_user` suspends the current incubation cycle. `handoff_pending` keeps
the design reminder responsible for repairing or completing an authorized
handoff until replacement continuity is confirmed. A terminal status stops the
recorded design reminder, verifies its absence, and records it as stopped. The
current status is `approved`.

## Lifecycle

### Start

After the decision record and design-document path exist, inspect the current
native objective and active schedules.

- Reuse each compatible objective or design reminder independently.
- If the design reminder is missing, create one 30-minute reminder and persist
  its returned ID in the design document.
- If the design objective is missing, write a design-only objective and deliver
  it with the existing SDK helper as the final action of the turn.
- If an unrelated objective is active, do not replace it automatically. Follow
  its governing process or an explicit user redirect.

The design-only objective points to the decision record and design document.
It requires completion of `design-doc` through the current challenge and
two-family design review. It explicitly forbids implementation. Its current
cycle finishes when the design is approved or when `design_status` becomes
`waiting_user` because no independent action remains. Each activation includes
a persisted monotonic `design_cycle` identifier in the objective text.

### Continue

Each 30-minute reminder first reads `design_status`. While it is `active`, the
reminder checks for stalled or stale progress and advances the next ready
recovery action. It may continue drafting, consume a completed owner result,
apply a supported review fix, launch the next required review phase, or update
the durable baton.

It does not interrupt a coherent edit, duplicate an active challenge or review,
infer owner state from files, implement the proposed system, or repeat a
pending human-only question. When a genuine user-only decision leaves no
independent action ready, persist the exact question, set `design_status` to
`waiting_user`, stop the reminder, and let the design objective finish its
current cycle. After a later user turn makes independent work ready, set the
status back to `active`, increment and persist `design_cycle`, re-arm any
missing reminder, and deliver the objective containing that new cycle
identifier. Require the SDK receipt to prove idle or steering activation for
the new objective rather than accepting a receipt deduplicated from the
completed cycle. Do not spend recurring objective or reminder turns returning
at the same gate.

### Finish or hand off

Design incubation has three terminal events:

1. **Approved:** the current constraint challenge permits the design, both
   design reviewers have no material open finding, and the work order is
   presented.
2. **Abandoned or redirected:** the user or governing design decision ends this
   work order.
3. **Reframed:** the current design is replaced by a new task boundary.

For abandonment, redirection, or reframing, the `design-doc` owner persists the
corresponding terminal `design_status` before schedule cleanup. A later
reminder that observes terminal status performs cleanup instead of resuming
design work.

For approval with no existing implementation instruction, persist `approved`,
stop the temporary reminder, verify its absence, record the reminder as
stopped, and present the work order.

For approval with an existing instruction to continue into implementation:

1. persist `handoff_pending`;
2. hand the approved work order to `development-loop`, which owns whether the
   implementation run is attended and every gate through landing;
3. if `development-loop` routes long work to `unattended-run`, create the
   normal charter and implementation objective from the approved work order;
4. arm and confirm the normal hourly progress and four-hour charter reminders;
5. stop the temporary 30-minute reminder and verify that the normal pair for
   this implementation charter is live and its design reminder is absent,
   without disturbing unrelated schedules; and
6. persist `approved`, then replace the completed design objective with the
   implementation objective through the existing SDK helper as the final
   action of the turn.

If `development-loop` keeps the implementation attended, stop the temporary
reminder, persist `approved`, and continue under `development-loop` without
creating the normal unattended pair.

A design reminder that observes `handoff_pending` repairs or completes this
ordered handoff. It does not clean itself up until either the normal unattended
pair is confirmed or `development-loop` has selected the attended path.

This ordered, non-atomic handoff keeps continuity. Its partial-failure rules
provide recovery without locking and prevent both reminder systems from
remaining live.

## Failure model

| Failure | Required behavior |
|---|---|
| Objective delivery fails | Keep the reminder live, preserve the receipt, print the existing manual fallback, and continue the design |
| Reminder creation fails | Continue the current attended turn, report the missing continuity mechanism, and do not claim incubation is armed |
| Review owner is still active | Record the owner as active or unknown from its explicit result channel; do not launch a duplicate |
| Genuine user decision is required | Ask once with full context, set `design_status` to `waiting_user`, stop the reminder, let the current objective cycle finish, and re-arm both mechanisms only after a later user turn makes work ready |
| Resumed design objective is deduplicated from a completed cycle | Increment and persist `design_cycle`, include it in the new objective text, and require a receipt proving idle or steering activation for that cycle |
| Approval handoff partially fails | Keep the confirmed reminder set that still preserves continuity; repair the registry before stopping its predecessor |
| Implementation objective handoff is interrupted after the normal pair is live | Keep the normal pair and leave the design reminder stopped. Persist a unique handoff ID and `prepared` before submission. The next normal tick verifies native state and the request store by deduplication identity, submits a missing prepared request once, and tracks an in-flight request as `submitted`. After terminal failure it records `resolved` only with exact `idle` or `steering` activation proof. Otherwise it persists `fallback_pending` with a notice ID bound to this handoff and receipt, delivers that identified fallback, and records `fallback_delivered` only after a later transcript turn proves delivery of the same notice and digest; it never retries an ambiguous or otherwise terminal failure with the same identity |
| Design is abandoned | Stop the temporary reminder and preserve the design and decision record as historical evidence |

## Invariants

1. At most one design-incubation reminder covers one design task.
2. The design objective cannot authorize implementation.
3. The normal unattended reminder pair and the design reminder do not remain
   live together after the ordered handoff.
4. An unrelated objective or schedule is never replaced or stopped.
5. Active review and challenge attempts are never duplicated by a timer.
6. Every terminal design event stops or replaces the temporary reminder.
7. A user-only wait produces no recurring objective or reminder turns until a
   later user turn makes independent work ready.
8. A resumed design cycle has a distinct objective identity and confirmed
   native activation.
9. `handoff_pending` never cleans up the design reminder before replacement
   continuity is confirmed.

## Acceptance criteria

1. `design-doc` requires continuity setup at kickoff when the session has no
   compatible objective or reminder and the design is not expected to finish in
   the current attended turn.
2. `unattended-run` defines one 30-minute design reminder and a design-only
   objective using the existing SDK helper, and identifies the objective as the
   primary loop and the reminder as its liveness and recovery backstop.
3. Each mechanism is reconciled independently. The reminder and objective honor
   durable design status and advance recovery work without implementing,
   duplicating active review, or repeating a human-only question.
4. Design approval stops the temporary reminder when implementation is not
   already authorized.
5. An authorized implementation handoff returns to `development-loop`; only a
   run it routes to `unattended-run` confirms the normal hourly/four-hour pair
   before stopping the temporary reminder and replacing the objective.
6. Existing normal unattended-run behavior remains unchanged.

## Check contract

| Claim | Setup | Pass signal | Failure signal |
|---|---|---|---|
| Kickoff closes the continuity gap | Inspect the `design-doc` kickoff contract | It independently reconciles the objective and reminder before drafting continues | Design review can begin with a missing objective or reminder |
| Temporary mode stays bounded | Inspect the design reminder and objective templates | They name their distinct roles, use 30 minutes, forbid implementation, avoid duplicate review, check durable status, and name terminal events | The prompt can implement, relaunch active work, ignore terminal status, or run forever |
| User-only waits do not consume recurring turns | Inspect the reminder and objective contracts | They persist the exact question, enter `waiting_user`, finish the current objective cycle, stop the reminder, and resume with an incremented cycle plus confirmed native activation only after a later user turn makes work ready | The same unresolved question triggers repeated turns or unchanged objective text deduplicates instead of reactivating |
| Terminal status survives interruption | Inspect each terminal transition | Terminal cleanup persists status before stopping; an authorized implementation uses `handoff_pending` until replacement continuity is confirmed | An interrupted terminal transition restarts ended work or cleans up its only recovery reminder |
| Handoff has one owner | Inspect the ordered transition | `development-loop` selects attended or unattended execution; an unattended route confirms its normal pair before the design reminder stops, then replaces the objective without claiming atomicity | Design incubation bypasses `development-loop`, unrelated schedules block verification, or continuity drops silently |
| Objective handoff failure remains recoverable | Inspect the partial-failure contract | The normal pair remains live, the design reminder remains stopped, the failed receipt and manual fallback are preserved, and a later normal tick verifies or retries after receipt resolution | A failed replacement leaves contradictory objective and reminder instructions with no recovery |
| Existing unattended behavior remains intact | Run the existing unattended contract test | Existing hourly, four-hour, objective, and shutdown assertions pass | Any maintained assertion fails |
| New contract is durable | Run the new design-continuity contract test | Required kickoff, prompt, and handoff clauses are present | A required lifecycle clause is absent |

## Definition of Done: design incubation continuity

- The decision record and work order are current.
- A two-pass constraint challenge permits the design.
- Two-family design review has no material open finding.
- `design-doc` and `unattended-run` implement the approved lifecycle.
- A deterministic contract test covers kickoff, bounded continuation, and
  handoff.
- Existing unattended-run tests pass.
- Two-family implementation review has no material open finding.
- The active installed skills match the reviewed source.
