# Skill Evaluation Project Dashboard Constraint Challenge

**Evidence packet:** `design/skill-evaluation-ui-project-evidence.json`  
**Evidence revision:** `skill-evaluation-ui-project-evidence-r1`  
**Work order:** `design/skill-evaluation-ui-project-dashboard.md`  
**Challenger:** `project-ui-two-pass`  
**Agent ID:** `9a8f7194-f1c4-4947-a2f8-49643a4af3ca`

## Pass 1: evidence only

**Provisional decision:** `NARROW`

The minimum justified design was:

- explicit project, task, case, and run identity at supported evaluator
  boundaries;
- a read-only project hierarchy built from append-only events and immutable
  evaluator results;
- evaluator-owned lifecycle rather than agent-session liveness;
- separate task result and workflow phase;
- safe typed progress, covered accounting, aggregate holdout qualification,
  per-task minimization, and conditional whole-skill minimization;
- compact run history;
- one browser opening per project and service generation;
- refresh-safe tab-scoped capabilities; and
- visible but unassigned legacy evidence.

The challenger rejected inferred migration, arbitrary launch discovery,
dashboard execution controls, mutable result storage, hidden evidence, and new
coordination without evidenced conflicting writers.

The three highest-leverage assumptions were:

1. supported launchers cover the automatic-monitoring boundary;
2. existing source artifacts contain enough authority for the promised
   rollups; and
3. explicit identity can use evaluator-owned declarations without a second
   synchronization system.

## Pass 2: proposal review

**Decision:** `NARROW`

The challenger independently confirmed that both questioned surfaces were
supported:

- conditional whole-skill ablation follows the governing hill-climb and
  ablation procedures; and
- an unassigned legacy view is the smallest way to preserve existing readable
  history without forbidden inference or backfill.

The work order was required to:

- define field-level project merge and conflict behavior;
- reuse lineage for exact revision selection;
- extend existing task progress instead of adding a phase event family;
- restrict safe progress to typed data readers;
- preserve source-owned local and distributed lifecycle authority;
- remove unsupported cancellation;
- name a concrete private holdout suite writer;
- reuse experiments and snapshots for ablation;
- define atomic project-open state;
- define the capability scope matrix and unassigned transition;
- remove fixed merge and install mechanics from product correctness; and
- narrow proof to the changed properties.

## Focused reconciliation

The first reconciliation found six remaining ambiguities:

1. complete declaration merge and conflict effects;
2. cross-corpus lineage reconciliation;
3. project-index navigation authority;
4. complete-scope `sessionStorage` keys;
5. startup intent versus later captured exact identity; and
6. stale generic-lifecycle wording.

The work order was revised to resolve all six.

## Final gate

**Decision:** `CONTINUE`

**Permitted scope:** The complete current work order, including canonical
declaration and conflict effects, reconciled cross-corpus lineage selection,
existing-progress phase mapping, source-owned startup and failure truth, atomic
open-once claims, child project capabilities, complete-scope tab storage, and
revalidated unassigned access.

**Blocked scope:** None from this challenge. Implementation remains subject to
dual design review and the work order's reframe gate.

**Remaining must-edit items:** None.

**Dual design review:** The exact current work order may proceed.

## Security conclusion

Deliberate owner grants remain allowed. An owner may use supported evaluator
commands and explicitly open dashboard scopes. The dashboard cannot turn that
grant into execution, publication, cross-project, hidden-evidence, or holdout
detail authority.

No external organizational or regulatory policy was evidenced. The retained
controls protect the user-approved read-only product boundary, result
integrity, evaluation secrecy, and truthful accounting.

## Event-triggered reconciliation after dual-review findings

Round 1 of dual design review identified gaps in task qualification, task-phase
authority and reduction, local liveness, holdout producer authenticity, legacy
opt-in history, and declaration evolution.

The first event-triggered challenge returned `NARROW` and required:

- exact declaration, snapshot, campaign, binding, case-revision, and terminal
  attempt identity for task qualification;
- dashboard-recorded-time phase reduction;
- startup-bound lease generations with fail-closed renewal;
- an owner-only create-once holdout trust registry;
- a canonical signed started-to-terminal receipt chain; and
- additive declaration revisions with explicit supersession.

After those edits, the same challenger returned:

**Decision:** `CONTINUE`

**Permitted scope:** Typed exact-identity task qualification,
dashboard-recorded-time phase reduction, startup-bound renewable local leases,
owner-only create-once holdout authorities, canonical Ed25519 receipt
verification and deterministic import, additive supersedes-chained schema-v1
declarations, and the previously approved project-dashboard scope.

**Blocked scope:** None.

**Remaining must-edit items:** None.

**Dual design review round 2:** The exact current revision may proceed.
