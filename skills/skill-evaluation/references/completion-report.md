# Skill evaluation completion report

Use this report after a skill-change evaluation finishes, whether or not the
candidate qualifies. Describe an unqualified candidate as an observed or
intended change, not as a released capability.

## Required content

### Evaluation outcome

- Result and exact baseline and candidate identities.
- Qualified claim and important claims that were not tested.

### What changed

| Area | Baseline behavior | Candidate behavior | Evidence |
| --- | --- | --- | --- |

Name the prior user-visible failure, the general rule or behavior that changed,
and the exact case or product check that shows the effect.

Use these labels:

- **Proven capability:** the exact candidate passed the applicable focused and
  maintained gates.
- **Observed improvement:** behavior moved in the desired direction, but the
  release gate did not pass.
- **Intended change:** the implementation changed, but no behavioral result
  establishes the effect.

### What it can do now

List the proven capabilities in user-facing terms. Do not restate
implementation details as capabilities.

### Size change

| Artifact | Bytes before | Bytes after | Delta | Lines before | Lines after | Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

Use the same measurement method for both revisions. Include percentages when
the baseline is nonzero. Separate:

- skill instructions and shipped references;
- evaluator or runtime code;
- frozen cases and generated manifests; and
- project documentation and run artifacts.

Do not call growth bloat or reduction simplification without applicable
ablation or maintained-task evidence.

### Proof and reliability

- Focused results and first-attempt status.
- Maintained regression results and retry-dependent passes.
- Deterministic checks and review gates.
- Preserved genuine stops, abstentions, or other protected behavior.
- Material duration or cost data already captured by the evaluator.

### Remaining uncertainty

Name stochastic outcomes, untested callers, missing accounting, and claims that
still need a separate generalization, transfer, or ablation gate.

## Proportional form

A one-case wording fix may use a few bullets and one size row. A multi-skill
release should include both tables, exact report paths or receipt IDs, retry
dependence, and material cost or duration data. Omit empty sections only when
the omitted information does not apply.
