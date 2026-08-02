---
name: review
description: Bound dual review by evidence, scope, material risk, and a fixed round budget. Runs latest Claude Opus and latest non-mini/non-codex GPT in parallel, with finding-level verification only for disputed blockers. Use when a non-trivial diff needs review before landing, or a systemic or critical design and its guards need pre-implementation review.
---

# review

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

Do not use for typo-only, formatting-only, generated-only, dependency-only, or
other trivial changes already covered by a deterministic check. Use a security
specialist in addition to this skill when the user explicitly requests a
security review.

## Reviewer pair

| Slot | Model family | Agent type | Mode |
|---|---|---|---|
| A | latest Claude Opus | `code-review` | `background` |
| B | latest GPT **Terra** tier (balanced), excluding mini and codex | `code-review` | `background` |

Resolve the highest-numbered available model in each family at session start.
For slot B prefer the Terra (balanced) tier over the Sol (flagship) tier: it
keeps almost all of Sol's coding/reasoning accuracy while being faster and
cheaper, which suits a parallel reviewer. Avoid the Luna tier here — its lower
reasoning capacity misses subtle logic bugs. If no Terra-tier model exists in
the current build, fall back to the highest non-mini, non-codex GPT.
Dispatch the bare model id; put effort labels in the prompt, not the model id.
Both reviewers run in parallel and receive the same scope contract.

If one reviewer fails, retry it once. If the retry fails, stop and report the
dual review as incomplete. Never call a single-family result a dual review.

## Review packet

Before dispatch, prepare a packet containing:

- repository and base commit;
- current diff path and changed-file list;
- the user-visible objective and acceptance criteria;
- explicit non-goals;
- directly relevant design/invariant documents;
- latest targeted tests and live proof, when available;
- prior kept findings for round 2 or 3;
- for later rounds, the delta since the preceding review round.

Keep the packet small. Do not paste unrelated roadmaps, historical PR
descriptions, or broad repository context. Reviewers may inspect a directly
called dependency to prove a claim, but must not recursively audit adjacent
subsystems without evidence that the changed path reaches them.

If the human-written diff exceeds roughly 400 lines or mixes independent
behaviors, split it into reviewable slices before dispatch where practical.

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
6. **Bounded investigation.** Review the diff and direct interaction surfaces,
   with a target budget of at most 60 tool calls or 60 minutes. If responsible
   coverage is impossible, return `review_complete: false`; do not keep
   searching indefinitely.
7. **Round discipline.**
   - Round 1 is the broad discovery pass.
   - Round 2 verifies prior fixes and reviews the fix delta plus directly
     affected paths.
   - Round 3 may verify unresolved material findings only. It must not introduce
     unrelated latent issues from untouched code.

## Finding schema

```json
{
  "reviewer": "claude-opus-latest",
  "round": 1,
  "review_complete": true,
  "incomplete_reason": null,
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

The reviewer-side time/tool budget is not sufficient by itself. When the
runtime exposes elapsed time, tool-call count, or cancellation:

- inspect status no later than 30 minutes for a reviewer that has not returned;
- request immediate conclusion or cancel at 60 minutes or 60 tool calls;
- discard partial prose as an incomplete review;
- split/narrow before retrying rather than granting more search time.

When the runtime cannot cancel a running reviewer, do not treat its eventual
over-budget output as authoritative. Mark it incomplete and use a narrowed
retry. Prevent this case up front by splitting large/mixed diffs and keeping the
review packet bounded.

## Bounded iteration loop

Default budget: **two substantive rounds plus one resolution-only round**.

For pre-implementation review of a systemic/critical design and its guards, use
a narrower budget: **one discovery round plus one fix-verification round only**.
There is no third pre-build round. Remaining non-material suggestions become
follow-ups; unresolved material design defects enter the autonomous completion
ladder below before implementation.

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

The protocol is complete when:

1. both model families completed the required round;
2. every kept finding has verified evidence and diff causality;
3. no `must-fix` finding remains;
4. any verifier was finding-scoped and introduced no new issue;
5. the review and autonomous closure budgets were respected.
