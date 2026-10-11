# Skill Evaluation UI Slice 4 constraint challenge

## Scope

Two-pass independent challenge of the systemic Slice 4 experiment and
distributed-activity boundary.

- Sealed pass-1 packet:
  `design/skill-evaluation-ui-slice4-evidence.json`
- Pass-2 work order:
  `design/skill-evaluation-ui-slice4.md`
- Exact user authority:
  `design/skill-evaluation-ui-slice4-decisions.json`

## Pass 1

**Decision:** `NARROW`.

### Minimum design

Retain only:

1. a versioned experiment/activity record family reusing the existing
   writer-scoped append-only extension model;
2. additive campaign and task projections over exact evaluator, distributed
   campaign, and exact-known Actions identities;
3. explicit separation of experiment design, transport, stage, evaluator,
   first-outcome, recovery, effective-result, and cost-coverage state.

The minimum does not require local evaluator format changes. Existing local
activity already carries task, skill, treatment, model, platform, and
correctness identity. Slice 4 experiment membership may remain limited to the
distributed attempt contract.

### Required boundaries

- The dashboard remains a read-only projection and never receives GitHub
  credentials.
- Existing evaluator artifacts remain correctness authority.
- Existing distributed receipts remain stage and effective-result authority.
- Existing Actions observation snapshots prove only that exact bindings were
  observed.
- First outcomes remain immutable; recovery is separate source lineage.
- Missing cost remains unknown rather than inferred from model, timeout, byte,
  workflow, or runner fields.
- Malformed and conflicting records are isolated without hiding valid siblings.

### Removed machinery

- dashboard-side cloud API client or broad cloud discovery;
- generic importer or copied second source of evaluator truth;
- mutable database;
- execution, retry, cancel, dispatch, promotion, or recovery controls;
- arbitrary artifact, repository, release, log, candidate, or judge browsing;
- a new endpoint without measured payload evidence;
- ablation qualification or raw evidence drill-down.

### Coordination evidence

Concurrent workflow sessions, local evaluators, a distributed coordinator, and
the bounded cloud observer are distinct evidenced writers. Each keeps
non-overlapping ownership and publishes immutable or writer-scoped records.
The dashboard has no write authority.

### Security classification

Trusted owner-controlled tools may deliberately publish the bounded records
they own. Candidate output, treatment prose, workflow output, browser input,
and session summaries must not expand authority, alter immutable identity,
replace first outcomes, create PASS, qualify a treatment, or broaden cloud
observation. No external policy narrows deliberate owner grants beyond the
user's read-only browser and no-hidden-evidence boundaries.

## Pass 2

**Decision:** `NARROW`

The proposal survives with these corrections:

1. remove local evaluator flags, `attempt.json`, lifecycle, and history changes;
2. bind the immutable experiment plan before dispatch by carrying its exact
   fingerprint through the existing distributed matrix, stages, receipts, and
   reconciliation;
3. publish one complete Actions observation snapshot record rather than
   independently publishing per-attempt fragments;
4. derive pending selection, attempt totals, and repetition totals instead of
   storing mutable or redundant fields;
5. retain deterministic experiment selection only as explicit
   non-authoritative state, with incompatible terminal records surfaced as
   conflicts;
6. permit global counts only inside the existing explicit global-overview
   capability and omit private repository, workflow, experiment, and source
   detail;
7. keep distributed cost unknown unless a canonical accounting artifact exists;
8. use direct owner-selected validator-backed publishers, never a generic
   importer, scanner, copy layer, poller, or database.

### Deliberate owner grants

Trusted owners may deliberately give the existing observer GitHub credentials
and give a trusted publisher read access to one explicit local artifact. The
restriction applies to authority expansion into the dashboard service, browser,
candidate output, or generic discovery. No external policy fixes a stricter
ceiling.

### Writer counts

- at least two workflow sessions may publish experiment declarations; only the
  deterministic experiment evaluator may publish selection records;
- one observer exclusively writes each complete Actions snapshot;
- one coordinator owns each distributed receipt;
- one publisher invocation emits each bounded journal record; and
- the dashboard and browser have zero write authority.

No new lock, transaction service, queue, coordinator, or mutable database is
justified.

## Current gate

`CLEAR`

- **Trigger:** round-1 dual review proved the prior design lacked an
  authoritative dispatch-to-run/job binding and did not bind candidate model,
  treatment bytes, target-skill identities, or platform through execution.
  The work order now proposes exact-known job observation and versioned
  distributed matrix/package/runtime identities.
- **Delta challenge:** `NARROW`. Keep the immutable dispatch binding,
  exact-known complete job observation, versioned distributed execution
  identity, package/runtime/carrier validation, and terminal-only selection.
  Define one canonical identity, one planner-owned complete job-name set,
  explicit binding uniqueness, v1 unavailability, owner-scoped writers,
  selection precedence, and publisher-side private metadata.
- **Corrections applied:** the work order now defines the canonical v2 identity
  at every boundary, planner-owned job generation and exact set validation,
  immutable binding keys and conflicts, explicit v1 behavior, terminal
  selection precedence, and direct security checks.
- **Resolution:** focused closure verified the remaining variant-specific writer
  enforcement and publisher-side-only private metadata checks. No correction
  remains.
- **Selection-authority delta:** round-2 review proved that accepting a
  session-authored terminal result could bypass declared eligibility and
  coverage. A focused challenge returned `NARROW`: retain the separate
  `experiment_evaluator`, but close eligibility and ranking over enumerated
  evaluator-owned fields, coverage predicates, disqualifiers, metric names,
  value types, and directions. Treat selected/eliminated treatment IDs, metric
  values, and reasons as evaluator outputs only.
- **Selection corrections applied:** unknown fields, formulas, arbitrary paths,
  display identities, session prose, and selection-record inputs are refused;
  ties yield `no_selection`; incomplete coverage yields
  `selection_incomplete` and no terminal record. The challenge gate is clear
  for finding-scoped reviewer closure.
- **Permitted:** dual-review fix verification of the exact finding delta,
  followed by implementation only when both reviewer families close every
  material finding.
- **Blocked until fix-verification review clears:** implementation; local evaluator experiment binding; partial
  observation publication; new endpoints; cloud clients or discovery;
  generic import/copy infrastructure; mutable databases; inferred distributed
  cost; latest-wins selection; private source metadata; raw artifacts; and
  execution controls.
