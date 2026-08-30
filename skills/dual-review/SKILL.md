---
name: dual-review
description: Bound dual review by evidence, scope, material risk, and a fixed round budget, and run its single-agent challenge-only mode when a systemic or critical plan needs an independent constraint check. Runs latest Claude Opus and latest non-mini/non-codex GPT in parallel for normal review, with finding-level verification only for disputed blockers. Use when a non-trivial diff needs review before landing, a systemic or critical design and its guards need pre-implementation review, or a governing workflow says a constraint challenge is due.
---

# dual-review

Run two independent reviewers against the same change, then use evidence and
risk to decide what actually blocks landing. The goal is **no verified,
in-scope, material defects**, not zero comments and not perfect code.

This protocol follows four review principles:

- A change may land when it definitely improves the codebase, even if optional
  improvements remain.
- Risk is a combination of impact and likelihood.
- Problems outside the current change do not become mandatory work merely
  because a reviewer noticed them.
- Re-review verifies fixes; it is not an invitation to restart an unbounded
  repository audit every round.

## When to invoke

Use for a non-trivial diff involving multiple files, behavior changes, error
paths, shared state, persistence, concurrency, security, or domain logic.

Use the standalone challenge-only mode in
[`references/constraint-challenge-lens.md`](./references/constraint-challenge-lens.md)
when `design-doc`, `development-loop`, or `unattended-run` says a systemic or
critical plan needs an independent constraint challenge. That mode launches
one fresh read-only challenger and does not run the normal two-family review.
Its own record and verdict are its completion contract.

Do not use for typo-only, formatting-only, generated-only, dependency-only, or
other trivial changes already covered by a deterministic check. Use a security
specialist in addition to this skill when the user explicitly requests a
security review.

## Reviewer pair

| Slot | Model family |
|---|---|
| A | latest Claude Opus |
| B | latest full GPT, preferring **Terra** |

Resolve the highest-numbered available model in each family at session start.
Prefer Terra for routine cost and latency. Sol and Luna are valid fallbacks;
exclude only mini and codex variants. The scope and execution budgets, not the
GPT tier, bound the review. Launch both reviewers with medium reasoning effort
and default context. They run in parallel and receive the same scope contract.

If one reviewer fails, retry it once. If the retry fails, stop and report the
dual review as incomplete. Never call a single-family result a dual review.

## Transport

Both families are reachable from any of these hosts; only the dispatch differs,
and the protocol is identical whichever runtime carries it. Resolve the host at
session start and use its row.

| Host | Slot A (Claude) | Slot B (GPT) |
|---|---|---|
| Copilot CLI | `code-review` agent, `background` | `code-review` agent, `background` |
| Claude Code | `Agent` tool, model `opus`, background | `codex exec -m <model> --sandbox read-only`, or the `codex` plugin's `codex-companion.mjs task --model <model> --effort medium` |
| Codex CLI | `claude -p --model <model>` | native subagent, `background` |

A host lacking a native agent type for the other family still satisfies the
protocol through that family's own CLI, so a missing agent type is a dispatch
detail rather than grounds to report the review as single-family.

Run slot B read-only wherever the transport offers it. `--sandbox read-only`
converts the static-review rule in the prompt contract from an instruction the
reviewer can drift from into a mechanical guarantee.

Model identifiers move between generations, so discover them rather than
trusting a written example: query the host's model list for the current
`gpt-5.x-terra` and Opus releases at session start, and treat any identifier
quoted here as illustrative.

## Review packet

Before dispatch, prepare a packet containing:

- repository and base commit;
- the complete review subject and its path;
- current diff path and changed-file list;
- the user-visible objective and acceptance criteria;
- explicit non-goals;
- the governing skill or process contract when it supplies review or
  completion rules;
- directly relevant design/invariant documents;
- directly relevant discovery evidence, such as a `scout` report, issue
  decisions, or repository conventions that constrained the chosen direction;
- for a design review, its constraint-provenance record and recorded revisit
  conditions;
- latest targeted tests and live proof, when available;
- prior kept findings for round 2 or 3;
- for later rounds, the delta since the preceding review round.

Keep the packet small. Do not paste unrelated roadmaps, historical PR
descriptions, or broad repository context. Reviewers may inspect a directly
called dependency to prove a claim, but must not recursively audit adjacent
subsystems without evidence that the changed path reaches them.

If the human-written diff exceeds roughly 400 lines or mixes independent
behaviors, split it into reviewable slices before dispatch where practical.

### Design review branch

When the subject is a design document or work order, load and give both
reviewers
[`references/design-scope-lens.md`](./references/design-scope-lens.md).
For a systemic or critical design, first ensure there is one current focused
independent challenge from
[`references/constraint-challenge-lens.md`](./references/constraint-challenge-lens.md).
Use a fresh read-only agent context that did not author the design. First give
it the user's relevant exact words and only the verified product, policy,
platform, compatibility, and observed-failure evidence so it derives a minimum
design without anchoring on the proposal. It classifies top-level needs,
scoped product choices, tactical approvals, and ambiguous statements; it
starts from the end user's job to be done and escalates contradictions among
top-level goals. Then give the same challenger the work order and current work
graph for comparison. Run its challenge-only mode rather than the normal
two-family review. If the packet already contains a current accepted record
bound to this exact work-order revision and work graph, reuse it instead of
running the challenger twice. Persist the record and include it in both
reviewers' evidence packet.

This is not a third full-diff reviewer. It examines only product-goal and
security provenance, effective written or unwritten constraints, the three
most load-bearing assumptions, and the gap from the minimum design. A
`NARROW`, `REFRAME`, `ESCALATE`, or security-relevant `UNKNOWN` verdict blocks
normal design review until its required action is reflected in the work order.

Architecture and scope are reviewed before implementation detail. The lens is
the single source of truth for supported-caller, inherited-constraint,
duplication, simplification, enforcement, and reframe questions; do not copy
its checklist into each reviewer prompt. Put its complete contents in the
reviewer template's authoritative `<DESIGN_SCOPE_LENS>` slot. For non-design
reviews, fill that slot with `Not applicable: this is not a design review.`

If the architecture/scope pass finds a material defect, fix that defect before
reviewing lower-level implementation choices. A later round verifies the prior
finding and its fix delta rather than restarting design discovery.

## Reviewer prompt contract

Use [`references/reviewer-prompt-template.md`](./references/reviewer-prompt-template.md).
The prompt must enforce:

1. **Skeptical, evidence-focused review.** The reviewer finds defects, not
   compliments, but zero findings is valid. Never tell a reviewer that a clean
   result is a failure; that instruction rewards invention.
2. **Diff causality.** A blocking candidate must be introduced or materially
   worsened by the diff, or directly violate an acceptance criterion or
   load-bearing invariant the diff claims to satisfy.
3. **Reachability.** State the supported input, state, event sequence, or caller
   that reaches the defect. Pure speculation is not a blocking finding.
4. **Impact and likelihood.** Every finding carries severity and likelihood.
5. **Verbatim evidence.** Every code claim includes a quote of at least 12
   source tokens from the cited range.
6. **Static review.** Read, search, and reason from the candidate and supplied
   evidence. Reviewers never build, test, lint, install, format, generate,
   launch, or mutate. Missing runtime evidence produces
   `review_complete: false` plus the smallest requested check; it does not
   authorize reviewer-side execution.
7. **Round budget.**
   - discovery: at most 30 tool calls or 25 minutes;
   - fix-verification: at most 12 tool calls or 10 minutes;
   - resolution-only: at most 8 tool calls or 8 minutes.
   Returning incomplete is correct when the budget cannot cover the slice.
   These are reviewer instructions and landing gates, not guaranteed runtime
   kill switches.
8. **Round discipline.**
   - Round 1 is the broad discovery pass.
   - Round 2 verifies prior fixes and reviews the fix delta plus directly
     affected paths.
   - Round 3 may verify unresolved material findings only. It must not introduce
     unrelated latent issues from untouched code.
9. **Design-lens acknowledgement.** Every output carries
   `design_scope_lens`. Design reviewers set `applicable` and `applied` to
   `true` and summarize the areas checked; other reviewers keep both false.

## Finding schema

```json
{
  "reviewer": "claude-opus-latest",
  "round": 1,
  "review_complete": true,
  "incomplete_reason": null,
  "design_scope_lens": {
    "applicable": false,
    "applied": false,
    "summary": "Not applicable: this is not a design review."
  },
  "findings": [
    {
      "file": "path/to/file.ts",
      "line_range": [10, 20],
      "severity": "blocker | high | medium",
      "likelihood": "likely | possible | hypothetical",
      "scope": "introduced | contract-regression | adjacent-preexisting",
      "category": "security | correctness | data-integrity | error-handling | concurrency | resource-management | auth | ux | other",
      "title": "Short defect title",
      "trigger": "Concrete supported input, state, caller, or event sequence",
      "body": "Explanation with a verbatim quote of at least 12 source tokens.",
      "suggested_fix": "Specific bounded fix"
    }
  ],
  "acknowledgements": [
    "Important suspected risk checked and ruled out, with a short reason."
  ]
}
```

Round 2 and 3 also include `prior_resolution`, with one evidence-backed entry
for every previously kept finding.

## Merger: verify, classify, then act

The main agent is the adjudicator by default. Reviewer output is evidence, not
an instruction to edit code.

For every finding:

1. Verify the quote in the cited range. If the citation is wrong or missing,
   inspect the cited code and direct context yourself. Keep the finding at the
   severity proved by the code and replace the citation, or drop it when the
   claim cannot be proved. Citation quality does not change product risk.
   Multiple bad citations make that reviewer result unreliable and require one
   corrected response.
2. Verify diff causality. Keep `introduced` and genuine `contract-regression`
   findings. `adjacent-preexisting` findings are non-blocking unless the diff
   makes them newly reachable or materially worse.
3. Verify the trigger is supported today. A future architecture, unsupported
   caller, or purely theoretical sequence is `hypothetical`.
4. Assign one disposition:

| Disposition | Rule |
|---|---|
| `must-fix` | Blocker with likely/possible reachability; high + likely; any verified violation of an explicit acceptance criterion; or a verified security, auth, data-loss, corruption, or common-path contract regression |
| `verify` | High + possible, reviewer disagreement on a potential blocker, unclear causality, or a finding whose fix would materially expand scope |
| `follow-up` | Medium; high + hypothetical; adjacent/pre-existing; or a real improvement not required for the stated objective |
| `drop` | Hallucinated, duplicate, style-only, unsupported, or below the signal threshold |

A medium finding may be fixed opportunistically only when it is likely, clearly
inside scope, low-risk, and does not broaden the architecture. It never forces
another review round by itself unless it is a verified violation of an explicit
acceptance criterion.

The existing disposition table remains authoritative for design reviews. A
lens finding is an acceptance-criterion violation only when it directly
contradicts the work order's stated criteria or the governing `design-doc`
completion rubric; otherwise medium simplification findings remain
non-blocking follow-ups.

For security, authentication, authorization, and data integrity, difficulty of
reproduction does not make a finding hypothetical. Use `hypothetical` only when
the path is demonstrably unreachable in the supported system, such as dead code
or an impossible input/state combination.

Do not automatically file an issue for every follow-up. Record one only when the
repository workflow expects it, the user asked for it, or the risk is important
enough that losing it would be irresponsible.

## Structural merge

Two findings collapse only when all are true:

- same file;
- overlapping ranges;
- same category;
- at least 12 shared verbatim source tokens within the overlap.

Highest severity and likelihood win inside a collapsed bucket. Single-reviewer
findings remain candidates, but unlike the old protocol they do not
automatically become mandatory work; they pass through the disposition gate.

If the other reviewer explicitly ruled the same area acceptable, mark the
candidate disputed and use the selective verifier only if it could be
`must-fix`.

## Selective finding verifier

Do **not** add a third full-diff reviewer. That increases cost and creates
another source of novel findings.

Use the prompt in
[`references/finding-verifier-prompt.md`](./references/finding-verifier-prompt.md)
only when:

- one reviewer alone raises a potential `must-fix` finding and the main agent
  cannot verify it deterministically;
- reviewers explicitly disagree on a potential `must-fix`;
- causality or likelihood is unclear;
- the proposed fix would expand beyond the stated objective; or
- round 3 surfaces a supposedly new material defect.

The verifier receives only the finding, cited code, smallest necessary direct
dependency context, diff hunk, and acceptance/non-goal contract. It cannot
search for new defects. Its output is `must-fix`, `follow-up`, or `drop` plus a
confidence score and evidence.

Before dispatch, copy the `must-fix` rule from the merger disposition table
verbatim into the verifier prompt's `<DISPOSITION_GATE>` placeholder. That
table is authoritative; the verifier may apply it but may not relax or replace
it.

Prefer a fast, cheaper model from a different family when available. Skip the
verifier when tests, code tracing, or a minimal reproduction already settle the
claim more cheaply.

## Incomplete or runaway reviewers

`review_complete: false` blocks the review gate. Split the diff or narrow the
assigned slice, then rerun that reviewer once. If the narrowed retry remains
incomplete, split once more or use the next-highest available model in the same
family. Land only slices completed by both families. A complete safe slice may
land independently while an unreviewable slice is deferred. Continue recovery
under the autonomous completion budget below when the deferred slice is
required for the acceptance criteria.

Reviewers are static consumers of evidence, never validation workers. A queued
compiler, unavailable runner, or missing dependency is therefore irrelevant to
their execution: they report the missing evidence and return.

When the runtime exposes elapsed time, tool-call count, or cancellation:

- inspect discovery reviewers at 15 minutes and focused reviewers at 7;
- request immediate conclusion at the round limit;
- discard over-budget output as incomplete;
- split or narrow before one retry rather than granting more search time.

Runtime counters are authoritative. Reviewer-reported counters are telemetry,
not proof of compliance. When the runtime cannot expose or enforce tool-call
limits, the call ceiling remains a review-acceptance rule rather than a hard
spend cap. When it cannot cancel a running reviewer, do not launch competing
reviewers or builds behind it. Mark its eventual over-budget output incomplete,
then use one narrowed retry.

The default ceilings assume a review slice of at most roughly 400 human-written
lines. Keep the ceilings and split an incomplete slice rather than raising
them. Use completed review telemetry to recalibrate downward when both families
consistently finish below half a ceiling; do not claim the ceilings are hard
enforcement unless runtime counters and cancellation prove it.

## Bounded iteration loop

Default budget: **two substantive rounds plus one resolution-only round**.

Design documents use the default budget. For an executable guard that must
exist before implementation, use a narrower budget: **one discovery round plus
one fix-verification round only**. There is no third pre-build guard round.
Remaining non-material suggestions become follow-ups; unresolved material
guard defects enter the autonomous completion ladder below before
implementation.

```text
round 1: broad independent review
         -> verify and disposition findings
         -> fix must-fix only

round 2: verify prior fixes + inspect fix delta
         -> verify and disposition findings
         -> fix remaining must-fix only

round 3: resolution-only, if material findings remain
         -> no new adjacent audit
         -> stop
```

Exit successfully as soon as there are no `must-fix` findings. Follow-ups may
remain and should be reported as non-blocking.

Round 3 ends broad reviewer discovery, not the responsibility to finish. At its
end:

- medium, hypothetical, and adjacent findings become non-blocking follow-ups;
- high possible findings use deterministic investigation or the selective
  verifier;
- verified blocker/high likely findings enter autonomous completion.

## Autonomous completion

For each remaining `must-fix` finding:

1. Prove or disprove it with code tracing, a targeted test, or a minimal
   reproduction. Drop disproved findings.
2. Apply the smallest fix that preserves the objective and non-goals.
3. Run affected validation, then ask both reviewer families for a
   finding-scoped closure check over that fix only. The check may report only
   the unresolved prior finding or a material regression introduced by the fix
   delta; it cannot restart unrelated discovery.
4. If it remains open, make one more bounded repair attempt.
5. If a direct fix still fails, simplify, revert, or split the risky behavior
   and land the safe slice when it still satisfies the acceptance criteria.

The autonomous completion budget covers reviewer recovery and finding closure.
It allows two repair attempts per finding, one redesign restart, and up to 120
additional minutes or 120 tool calls after the normal review budget is
exhausted, when the runtime exposes those counters. A finding-scoped closure
check does not reopen broad review.

Continue autonomously while a safe path remains inside that budget. Escalate
only when at least one hard boundary is reached:

- a verified blocker survives both repair attempts and scope reduction;
- the next fix requires a new subsystem or public contract, more than roughly
  200 additional human-written lines, or a second redesign restart;
- post-round-3 closure exceeds 120 minutes or 120 tool calls;
- acceptance criteria conflict, required authority or credentials are
  unavailable, or the next action is destructive or irreversible.

Escalation must state the remaining concrete risk, attempted fixes, safe
fallbacks, and estimated additional effort. Reaching round 3 alone is never a
reason to escalate.

If a review fix materially redesigns the change, end the current reviewable
slice. First simplify or split it. When the core acceptance criteria require
the redesign and it fits the closure budget, define one new slice and run one
fresh bounded review budget. A second redesign restart crosses the escalation
threshold.

## Out-of-scope findings

Adjacent issues are useful information, not free scope. Keep them out of the
current fix loop. A nearby issue becomes in scope only when the diff:

- introduces it;
- worsens it;
- relies on the broken behavior;
- makes it newly reachable; or
- claims to repair that exact contract.

Otherwise label it `follow-up` and continue.

## Reporting

After each round, report:

- reviewer completion status and elapsed time;
- counts by `must-fix`, `verify`, `follow-up`, and `drop`;
- prior finding resolution;
- whether another round is actually required.

Lead with the landing decision: `blocked by N material findings`, `verification
needed for N disputed findings`, or `review gate passed with N non-blocking
follow-ups`.

## Verification

The normal dual-review protocol is complete when:

1. both model families completed the required round;
2. every kept finding has verified evidence and diff causality;
3. no `must-fix` finding remains;
4. any verifier was finding-scoped and introduced no new issue;
5. the review and autonomous closure budgets were respected.
6. for a design review, both reviewers applied the architecture and scope lens
   and their output records `design_scope_lens.applied: true`; and
7. for a systemic or critical design, a fresh-context constraint challenge
   produced an accepted current verdict and is included in the review packet.

The standalone challenge-only mode is complete when the challenger stays
within its own budget, persists the record required by
`constraint-challenge-lens.md`, and returns one of that lens's five verdicts.
It does not require either normal reviewer family or a dual-review finding
round.
