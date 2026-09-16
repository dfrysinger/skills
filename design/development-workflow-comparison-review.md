# Development Workflow Comparison Design Review

**Subject:** `design/development-workflow-comparison.md`  
**Review type:** Systemic design review  
**Constraint gate:** `CONTINUE / CLEAR`  
**Final review result:** `PASS`

## Reviewers

- Claude Opus 5
- GPT-5.6 Sol Fast

Both reviewers applied the required design-scope lens.

## Round 1

The reviewers identified these material defects:

1. The durable challenge record did not yet contain the final gate bound to the
   revised design.
2. The external runner contract was broader than the one admitted Sandcastle
   treatment.
3. The report acceptance criterion lacked a report-projection check.
4. Rollback could allow a pre-change history reader to pool new treatment
   populations.
5. The public/private publication boundary lacked a complete check.

The work order was narrowed and the same constraint challenger issued a current
`CONTINUE / CLEAR` gate.

## Round 2

The reviewers confirmed the challenge binding, Sandcastle-only runner,
report-projection check, and treatment-aware rollback direction.

Two bounded issues remained:

1. The publication gate did not include staged non-secret or untracked intended
   paths.
2. The rollback text attributed refusal/quarantine behavior to pre-change
   readers that cannot recognize new treatment fields.

The publication gate was expanded to the union of committed, staged, and
untracked non-ignored paths. Rollback now retains or restores the
treatment-aware reader and explicitly declares pre-change readers unsupported
for new-format runs.

The same constraint challenger re-gated these exact changes as
`CONTINUE / CLEAR`.

## Round 3

Both reviewers verified the two remaining fixes and returned no findings.

- `must-fix`: 0
- `verify`: 0
- `follow-up`: 0
- `drop`: 0

The design review gate is closed.
