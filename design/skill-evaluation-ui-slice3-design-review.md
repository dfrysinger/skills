# Skill Evaluation UI Slice 3 design review

## Review subject

- Work order: `design/skill-evaluation-ui-slice3.md`
- Base commit: `68f289a098286f8980161097e64ee53e21feba53`
- Round: 1 discovery
- Reviewers: Claude Opus 5.5 and GPT 5.6 Terra
- Both reviewers completed static review and applied the architecture/scope
  lens.

## Round 1 disposition

### Must fix: exact evaluator-to-snapshot binding

Both reviewers found the same authority defect. Existing evaluator history
records one effective skill identity per attempt, while Slice 3 snapshots may
contain multiple skills. Per-skill hash overlap cannot prove that passes came
from one combined revision.

**Resolution:** The work order now requires:

- the evaluator's exact file exclusions and per-skill fingerprint algorithm;
- explicit snapshot binding before model execution;
- immutable `lineage-identity.json` in each bound run;
- history exposure of the exact snapshot ID;
- snapshot-level passing only from one validated full-corpus suite report bound
  to that snapshot ID, one complete plugin identity, every current exact case
  revision, and one evaluation contract;
- unbound or mismatched history never creating snapshot-level passing.

### Must fix: Foundation reader compatibility

Claude found that adding new top-level `EVENT_TYPES` would make Foundation
readers reject the journal during rollback or mixed-version operation.

**Resolution:** Slice 3 records now use a versioned extension directory inside
the existing writer journal. They reuse writer identity and atomic conflict
machinery but are not top-level Foundation event files. Foundation readers
ignore them. Slice 3 reads each extension record independently and isolates
malformed siblings.

### Must fix: artifact layout

Claude found that the draft described a journal path that does not exist and
could lead an implementer to create the second journal prohibited by the
constraint challenge.

**Resolution:** The work order now names the exact corpus-local integration:

```text
CORPUS/.skill-evaluation-ui/events/<sha256(canonical-writer)>/
```

Snapshots live under the same corpus-local dashboard root. The global service
state remains registration/service state only.

### Must fix: deterministic progress and role selection

Claude found that an event-ID tie-break contradicted the promised conflict
state and that current task snapshot and role tips were undefined.

**Resolution:** Maximum `observed_at` selects current progress; incompatible
records at that same instant remain conflicted, and event IDs only stabilize
display. Current role tips are role-bearing snapshots with no descendant
carrying the same role. The task uses the unique integrated tip, then the unique
released tip; multiplicity is conflicted and absence is unavailable.

## Current gate

Round 2 verified all four original findings. Claude identified one directly
related remaining authority race: the evaluator binding was specified against
the mutable source plugin rather than the pinned copy that actually runs.

**Resolution:** The evaluator now pins first, verifies every snapshot member
against the pinned bytes, and only then writes the lineage binding or starts
model execution. History independently recomputes each member identity from
the validated pinned `plugin-identity.json`; the dashboard consumes only the
verified history field.

## Round 3 closure

Claude Opus 5.5 and GPT 5.6 Terra both verified the pinned-byte repair and
independent history recomputation. Both completed static resolution-only review,
applied the design scope lens, and reported no findings.

## Final gate

**Passed.** No verified in-scope material design defect remains. The exact
bounded work order may enter implementation.
