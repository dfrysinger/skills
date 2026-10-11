# Skill Evaluation UI Slice 3 constraint challenge

## Scope

Two-pass independent challenge of the systemic Slice 3 artifact and trust
boundary.

- Sealed pass-1 packet:
  `design/skill-evaluation-ui-slice3-evidence.json`
- Pass-2 work order:
  `design/skill-evaluation-ui-slice3.md`
- Exact user authority:
  `design/skill-evaluation-ui-slice3-decisions.json`

## Pass 1

**Decision hypothesis:** `NARROW`

Retain only:

1. durable exact revision material limited to explicitly named target-skill
   roots, without raw-byte or whole-plugin browser exposure;
2. bounded immutable lineage declarations with PASS derived only from
   authoritative evaluator history;
3. typed immutable task-progress records and derived attention views without
   attachments or browsing paths.

At least two writers are evidenced by the supported concurrent Copilot
sessions. Collision-safe append-only records with visible conflicts are
justified. Locks, transactions, leader election, a mutable database, and
general synchronization are not.

## Pass 2

**Decision:** `NARROW`

**Gate:** `PARTIAL`

### Permitted scope

- Immutable exact revision material only for explicitly named target-skill
  roots.
- Typed manifests and exact task- or lineage-relevant comparisons.
- Lineage and task-progress variants in the existing dashboard event journal.
- PASS derived only from exact-identity immutable evaluator results.
- Focused task detail and compact attention projection.
- Explicit unavailable, stale, malformed, and conflicted states.

### Blocked scope

- A separate content-addressed blob subsystem or raw-byte namespace.
- Attempt-local whole-plugin snapshots as dashboard-readable lineage state.
- A second lineage/progress journal duplicating publication and conflict
  machinery.
- Arbitrary snapshot comparison or evidence browsing.
- Fixed queue ordering, route topology, or storage topology as acceptance
  requirements.
- Experiment, cloud, orchestration, ablation, mutable result, or execution
  control scope.

### Owner grants and policy

Trusted CLI producers may deliberately read explicitly named target-skill roots
and append validated events. The browser receives no arbitrary file grant.
Symlink, escape, non-regular-file, cross-campaign, and identity controls prevent
authority expansion beyond that bounded owner grant. No external organizational
policy establishes a stricter ceiling; the read-only and no-arbitrary-browsing
boundaries come directly from user and work-order authority.

## Required correction

The work order must:

1. make content-addressed deduplication optional;
2. store bounded immutable snapshot files with a typed manifest;
3. reuse the existing event journal for lineage and progress;
4. limit comparison to task- or lineage-relevant admitted pairs;
5. leave route decomposition and attention ordering as implementation choices;
6. remove arbitrary selectors and evidence browsing;
7. replace blob- and route-specific checks with direct boundary fixtures.

These corrections are applied in the current work order.

## Current gate

`CLEAR` for the exact bounded implementation in the corrected work order.

- **Reconciliation result:** all required narrowing edits are reflected; no
  further work-order correction is required.
- **Review condition:** Claude Opus 5.5 and GPT 5.6 Terra completed the required
  design review with no unresolved material finding.
- **Permitted scope:** source implementation, validation, and review of the
  exact bounded work order.
- **Blocked scope:** the challenge's removed blob subsystem, second journal,
  arbitrary comparison/browsing, fixed route/ordering topology, experiment,
  cloud, orchestration, ablation, mutable-result, and execution-control scope.
