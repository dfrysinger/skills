# Skill Evaluation Project Dashboard Dual Design Review

**Subject:** `design/skill-evaluation-ui-project-dashboard.md`  
**Constraint record:** `design/skill-evaluation-ui-project-constraint-challenge.md`  
**Reviewer A:** Claude Opus 5.5  
**Reviewer B:** GPT-5.6 Terra  
**Result:** Passed with no unresolved material finding

## Round 1: discovery

Both reviewers completed static design review within budget and applied the
architecture and scope lens.

Verified findings:

1. Session-authored phase could claim qualification or publication without
   authoritative evidence.
2. Local run interruption had no evaluator-owned liveness contract.
3. Holdout aggregates had no authenticated isolated producer.
4. Opting a legacy corpus into a project could hide its fingerprint-less runs.
5. Task PASS, regression, and time-to-pass had no typed qualification rule.
6. Case-scoped progress had no deterministic task-phase reduction.
7. Declaration edits had no revision or removal semantics.

The work order was revised to add typed exact qualification, intent-only
session phase, authority-derived completion phases, local leases, isolated
signed holdout receipts, pre-project history, and additive supersedes-chained
declarations.

## Event-triggered constraint reconciliation

The new holdout authentication boundary and related fixes were returned to the
same independent constraint challenger. After one narrowed correction round,
the current gate became `CONTINUE` with no blocked scope or remaining edit.

## Round 2: fix verification

Both reviewers completed the bounded fix-verification round and closed five
root causes. Two material findings remained:

1. A lease-renewal storage failure could later look like a definite
   interruption without durable evidence.
2. Whole-declaration SHA matching would erase unchanged task evidence after
   unrelated additive revisions and could not qualify cross-corpus tasks.

The work order was narrowed:

- an expired lease without a terminal artifact is now `liveness_lost`; only an
  explicit artifact may claim interruption; and
- qualification now matches canonical task and binding definition
  fingerprints resolved through archived declarations, while the whole
  declaration SHA remains provenance.

## Round 3: resolution only

Both reviewers verified only the two remaining findings.

- Claude Opus 5.5: both resolved; zero findings.
- GPT-5.6 Terra: both resolved; zero findings.

Both outputs recorded:

- `review_complete: true`;
- `design_scope_lens.applicable: true`;
- `design_scope_lens.applied: true`; and
- no unresolved material finding.

## Final gate

The reviewed work order may proceed to implementation under
`development-loop`. Follow-up architecture work is not required before Slice A.
