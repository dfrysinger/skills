# Development Workflow Comparison Constraint Challenge

**Evidence revision:** `workflow-comparison-evidence-r1`  
**Admission revision:** `workflow-comparison-challenge-admission-r1`  
**Reviewed proposal:** superseded pre-narrowing revision  
**Decision:** `NARROW`  
**Gate status:** `SUPERSEDED`  
**Reframe status:** `CLEAR AFTER REQUIRED EDITS`

## Pass 1 minimum

The existing repository-task evaluator remains the source of truth for frozen
cases, plugin snapshots, candidate execution, patch capture, grading,
judgments, timing, accounting, and history. Ordinary skill and plugin
treatments need additive identity and entry-skill selection, not a replacement
packaging architecture.

Only Sandcastle proves a new execution need: one bounded external candidate
entrypoint plus child-session observations mapped into existing candidate
measurements. VM provisioning and campaign scheduling remain private and
embarrassingly parallel. Human gates use facts approved before execution or
produce a compatibility result; they do not justify a checkpoint engine.

## Three challenged additions

1. **Generic treatment-package protocol — remove.** Existing plugin, case,
   image, model, harness, and immutable run identities already package normal
   treatments.
2. **General external command and attribution service — narrow.** Retain only a
   fixed contained Sandcastle runner seam. Reuse existing measurement records.
3. **Distributed scheduler/shared campaign state — remove.** One evaluator
   writes each attempt, one collector copies it to a unique destination, and
   one final reader aggregates immutable artifacts.

## Pass 2 gate

### Permitted scope

- Preserve legacy `baseline` and `skill` behavior.
- Add stable treatment ID, source revision, adapter digest, entry skill,
  runner kind, intervention policy, and narrowly consumed compatibility fields
  to attempt identity and history.
- Let a direct plugin entry skill differ from the case's historical target.
- Add one fixed-argv external runner inside the existing repository-task
  candidate boundary.
- Validate child-session declarations and collect available event files as
  ordinary candidate measurements with additive subroles.
- Report missing, malformed, duplicate, wrong-model, and observed undeclared
  sessions as incomplete or contaminated evidence.
- Keep private VM assignments, transfer, lifecycle, and parallel admission
  outside the public repository.

### Blocked scope

- A general treatment-package subsystem or normalized replacement for legacy
  arms.
- Ordered direct-Copilot steps, resumed repository sessions, or a checkpoint
  state machine.
- Candidate-authored declarations or absence of extra files as proof of
  exhaustive child-session accounting.
- A distributed coordinator, mutable ledger, queue, lock service, or cloud
  provider abstraction.
- Public evaluator acceptance gates for provider-specific VM transfer or
  four-VM execution.
- Claims that outer isolation is identical to Sandcastle's upstream nested
  Docker topology.

## Previously unresolved

**Exhaustive Sandcastle child-session ownership:** complete candidate cost is
allowed only if the adapter can force every Copilot launch through an
evaluator-owned session-ID allocation or another exhaustive evaluator-owned
launch hook. Otherwise Sandcastle remains admissible with explicitly partial
or unknown candidate credits.

This fact was subsequently resolved by
`design/sandcastle-session-allocation-feasibility.md` and must be rebound by
the same challenger to the final reviewed design digest before design review
can pass.

## Authority and coordination

Deliberate owner grants are allowed; no external policy fixes a stricter
ceiling. Hidden graders, reference repairs, corpus internals, sibling attempts,
host Copilot state, and the Docker socket remain unavailable to
candidate-controlled actors. These controls prevent untrusted authority
expansion; they do not constrain deterministic owner-approved VM lifecycle or
aggregation.

Writer counts are one candidate per workspace, one writer per child event file,
one evaluator per attempt directory, one collector per unique destination, and
one final report reader. No shared mutable campaign state has two evidenced
writers, so concurrency machinery is not justified.

## Smallest next action

Apply the narrowing edits, then inspect the exact frozen Sandcastle Copilot
provider and orchestration call path for evaluator-owned session allocation.

## Final gate

**Decision:** `CONTINUE`  
**Gate status:** `CLEAR`  
**Reframe status:** `CLEAR`

### Exact reviewed digests

- `design/development-workflow-comparison.md`:
  `764f11f15ee6b6ec704f11c1371db69c2523f4d503dca3641a080c0f9b37f153`
- This challenge record before the final gate was persisted:
  `68f2827e34cce203cb8a49a4694164f7a814b3340255de37eac55e9ed5cc4c53`
- `design/sandcastle-session-allocation-feasibility.md`:
  `8702c8b79932905d035c05be7e49cdd2415e2255670502fd29e49bced770484d`
- `design/development-workflow-comparison-evidence.json`:
  `68311142d0e17dc92596aae85c254c36b7de84e043d23225528f9151997a1341`
- `design/development-workflow-comparison-decisions.json`:
  `d7d901de050427f8fb3efbe89ae9d36a8ab12f72b7e80b2a9defc66a2f0af7b6`

### Permitted scope

- Preserve legacy baseline and skill execution.
- Add minimal direct-treatment identity, compatibility, and entry-skill
  metadata.
- Expose external execution only through the exact Sandcastle-specific CLI
  options and frozen identity.
- Collect evaluator-allocated Sandcastle sessions through existing candidate
  accounting.
- Add treatment-aware history and report projection.
- Retain the treatment-aware reader during execution rollback and declare
  pre-change readers unsupported for new-format artifacts.
- Enforce the public diff scope and secret scan.
- Keep VM lifecycle and campaign admission private.

### Blocked scope

- General external-command descriptors, CLI options, identities, commands,
  models, topologies, or subroles.
- Generic treatment packaging.
- Resumed direct steps or checkpoint machinery.
- Candidate declarations as exhaustive accounting authority.
- Removal of treatment-aware reading while new artifacts exist.
- Use of pre-change readers on new-format runs.
- Public VM or provider infrastructure.
- Shared mutable scheduling, queues, locks, or services.
- Private fixtures, transcripts, graders, credentials, provider scripts, or VM
  artifacts in the public diff.

### Resolved child-session fact

`CLOSED`. The frozen Sandcastle call path has at most one implementer and one
conditional reviewer launch. The public provider command seam can append
evaluator-preallocated UUIDs without changing prompts or phase order. Complete
coverage requires the evaluator-derived expected launch set and terminal
evidence for every expected UUID; declarations or absence of extra files cannot
upgrade incomplete coverage.

### Remaining required edits

None.

## Round-2 review-fix addendum

**Decision:** `CONTINUE`  
**Gate status:** `CLEAR`  
**Reframe status:** `CLEAR`

Exact reviewed inputs:

- `design/development-workflow-comparison.md`:
  `9c03371adcfe11a3b1a2cac996792ffe3c9e4d1b78bf83e95f9eb3986c184ef4`
- This challenge record before this addendum:
  `28b8420d6cd32bf99332cbb95aaf0937a0df6ed5a30627fb305c3726833529de`

The public diff scope gate applies its allowlist and secret scan to the union of
committed changes from the approved base, staged changes, and untracked
non-ignored paths.

Rollback disables new execution options but must retain or restore the
treatment-aware history and report reader before reading new-format artifacts.
Pre-change readers are explicitly unsupported for new-format runs because they
cannot recognize treatment identity and might pool incompatible attempts; no
quarantine capability is attributed to them.

No further edit is required.
