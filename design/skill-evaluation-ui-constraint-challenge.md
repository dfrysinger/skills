# Skill Evaluation UI Constraint Challenge

**Evidence revision:** `skill-evaluation-ui-evidence-r1`
**Decision record:** `skill-evaluation-ui-decisions-r1`
**Pass 1 proposal visibility:** none
**Pass 1 decision:** `NARROW`
**Pass 2 decision:** `NARROW`
**Closure decision:** `CONTINUE`
**Trust refresh decision:** `CONTINUE`
**Current gate:** `CLEAR`

## Pass 1 minimum design

The minimum design is a token-gated loopback-only, read-only presentation
surface over:

1. existing immutable evaluator artifacts for completed history; and
2. a minimal evaluator-owned live status contract for campaigns, sessions,
   assignments, attempts, progress, and artifact references.

Completed evaluator artifacts remain authoritative. Live records cannot turn a
workflow, candidate, or task green. The UI must retain exact identity,
completeness, unavailable-state, and evidence-boundary semantics.

## Highest-cost additions challenged

### Shared persistent service

Keep one shared local presentation service only because the user explicitly
approved one service and requires many simultaneous sessions to be visible.
Do not let it own execution, final results, cloud discovery, or a second copy
of completed history. Service lifetime, stale registration, and port ownership
must remain implementation details rather than result authority.

### Live progress journal

Keep the minimum evaluator-owned append-oriented contract. Do not create a
shared append file, global event ordering, or a mutable result database.
Concurrent writers require write-once event envelopes or single-writer atomic
records, explicit writer identity, idempotent event identity, and
reconciliation where immutable run artifacts supersede live claims.

Evidenced writers are many Copilot sessions, local evaluator processes, and a
bounded cloud observer. Their operations do not require a shared lock when
each writes its own immutable event or session-owned atomic status file.

### Cloud and portfolio observation

Keep only registered campaigns and exact known cloud-run bindings. Do not add
general workflow discovery or infer task success from workflow color.

## Highest-leverage assumptions

1. Campaign, session, attempt, case revision, and skill-set revision identities
   can join without accidental pooling or duplicate cost.
2. Live records can survive concurrency and crashes without becoming
   authoritative completed results.
3. Loopback alone is insufficient protection against a same-machine candidate;
   data access needs an unguessable capability plus a projection that never
   reads hidden evidence.

## Authority and security

Deliberate owner grants permit read-only local observability, a shared service,
a progress contract, one-time opening, and safe non-hidden drill-down. No
external policy was supplied. The hidden-evidence control governs authority
expansion by candidate-controlled actors; it does not restrict the owner from
viewing their own evaluation artifacts through an authenticated local UI.

## Pass 1 gate

**Decision: `NARROW`.**

Keep:

- read-only local observability;
- immutable artifacts as completed-result authority;
- a minimal live contract;
- campaign-first and multi-session views;
- exact identity, coverage, lineage, ablation, and unavailable states;
- token-gated loopback access with structural hidden-evidence exclusion; and
- one-time opening.

Remove or defer:

- execution controls;
- broad cloud discovery;
- rich duplicate telemetry;
- a mutable result database;
- arbitrary filesystem browsing; and
- any hidden judge or grader content.

## Smallest next step

Specify the exact identity and event contract, then prove every UI claim
reverse-traces to either one immutable artifact or one explicitly non-final
live event. Pass 2 reviews that exact work order.

## Pass 2

The runtime could not resume the one-shot pass-1 agent. A fresh read-only
challenger received the exact persisted pass-1 record, evidence packet,
decision record, and proposal. This transport limitation is disclosed; pass 1
was not regenerated.

**Decision: `NARROW`.**

### Permitted scope

- One read-only loopback presentation service with explicit lifecycle.
- Completed-history Slice 1 and live-local Slice 2.
- Exact identity joins, immutable-result authority, coverage-aware cost,
  unavailable states, and one-time opening.
- Session-owned status, evaluator-owned attempt events, write-once envelopes,
  and structural hidden-evidence exclusion.
- Structured safe artifact references.

### Blocked scope

- Execution controls, mutable result storage, broad cloud discovery, arbitrary
  paths, raw logs, and hidden evidence.
- Implementing lineage, experiment, cloud/distributed, ablation, or raw
  drill-down surfaces without their own focused design review.
- Treating loopback as authentication.

### Required edits

1. Approve only two foundation slices and make later requested slices explicit
   gated follow-on work.
2. Define token entropy, scope, rotation, revocation, logging, referrer, and
   candidate-isolation rules.
3. Define service lifetime, stop authority, replacement, stale sessions,
   unavailable roots, and old-browser behavior.
4. Make campaign identity immutable and remove arbitrary skill-tree snapshots
   from foundation state.
5. Define session versus evaluator writer ownership and strict Slice-2 event
   payloads.
6. Add source and authority metadata to every material projected claim.
7. Remove raw drill-down from foundation scope.
8. Define exact minimum identity tuples and unavailable behavior.
9. State actor, asset, operation, and control rather than relying on loopback.
10. Run a focused closure check before dual design review.

The current proposal incorporates edits 1 through 9.

## Focused closure

**Decision:** `CONTINUE`
**Gate status:** `CLEAR`

All ten pass-2 edits are resolved. No design-blocking fact remains for the
foundation scope.

### Permitted scope

- One authenticated read-only loopback service.
- Completed-history Slice 1.
- Live-local Slice 2.
- Exact identity joins, immutable-result precedence, coverage-aware cost, and
  explicit unavailable or stale states.
- Session-owned status, evaluator-owned attempt events, write-once envelopes,
  safe structured projections, and one-time opening.

### Blocked scope

- Execution or mutation controls.
- Mutable result storage.
- Broad cloud discovery.
- Arbitrary paths, raw logs, or hidden evidence.
- Slices 3 through 6 without their own focused design review.

### Remaining edits

None. Implementation must prove the work order's acceptance and security
checks; that is downstream validation, not an unresolved design premise.

## Focused trust-boundary refresh

**Trigger:** dual review asserted that a default same-user prose candidate
could use shell activity to acquire and exercise dashboard authority.

**New deciding evidence:** the exact candidate launcher in
`skills/skill-evaluation/scripts/skill_eval.py` supplies only `skill,view`,
disables built-in MCPs and remote operation, validates every invoked tool
against the allowlist, and rejects a successful prose `view` outside the staged
evaluation workdir. It supplies no shell, browser, HTTP, or MCP operation.

**Decision:** `CONTINUE`
**Gate status:** `CLEAR`

The candidate-shell premise is false for the supported caller. The user outcome
does not require a candidate-safe projection subsystem, protected transition
file, global disclosure mode, or recovery protocol.

### User outcome and authority

The user authorized a read-only local dashboard, one shared service for many
sessions, and safe non-hidden evidence. The protected assets are completed
history, other attempts, judgments, costs, identities, and browser read
capabilities. The untrusted actor is the prose candidate model. It must not
issue dashboard reads or acquire authority beyond its exact evaluation tool
grant.

No external policy was supplied. Deliberate owner grants remain allowed. The
retained controls govern authority expansion by the candidate, not
owner-approved local viewing.

### Keep

- Browser read capabilities remain unguessable, generation-scoped, and present
  only in service and browser memory.
- The root secret remains an owner-file input to the local `open` command and
  is accepted only by authenticated control-only loopback health and mint
  endpoints. Browser and projection routes reject it, and it is not treated as
  same-user isolation.
- The exact `skill,view` candidate tool allowlist and existing successful-view
  boundary audit remain part of the installed-plugin proof.
- A dashboard-state boundary violation fails the attempt and rotates the
  service generation before candidate output is accepted or judged.
- Any future candidate shell, browser, HTTP, unaudited filesystem, or MCP
  capability blocks automatic exposure and reopens the design gate.

The denied projection-read operation has no direct or indirect API available
to the candidate. The control endpoints require a root secret but the candidate
has no HTTP operation; a boundary-violating view rotates that secret before
output admission. The simplest bounded grant is the existing `skill,view`
allowlist; adding a projection-state subsystem would not remove an evidenced
capability and is therefore unsupported.

### Remove

- Candidate-safe projection mode.
- `projection-mode.json`.
- Transition ownership, generation binding, global safe-mode coordination,
  terminal-receipt recovery, and same-user capability adversarial checks that
  assumed candidate shell or HTTP access.

### Unresolved

None for the supported candidate caller. A future tool-grant change is a
reframe trigger, not an unresolved foundation premise.

### Coordination check

The retained live-state machinery still has at least two evidenced conflicting
writers: multiple Copilot sessions write session status, and multiple evaluator
invocations write attempt events. Session-generation locking remains justified
only for concurrent same-session emits; immutable per-writer envelopes avoid a
shared global append lock.

### Smallest next step

Run dual-review round 2 against the exact fix delta and runner evidence. Do not
start implementation until both review families report no must-fix finding.
