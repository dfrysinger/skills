---
name: design-doc
description: Write and review the durable work order for a systemic or critical change before code exists. Use when asked for a design or architecture document for work that alters shared state, persistence, a public contract, cross-component architecture, security, or a fail-closed boundary, or when `development-loop` triages work as more than bounded. Send bounded fixes and small features to `development-loop`.
---

# design-doc

A design document is a **work order**: it says what to build without the
conversation that produced it. Someone who was not in the room — a future
agent, a compacted context, you next month — can build from it.

That is the bar. A document that only makes sense to whoever wrote it has
failed, however thorough it looks.

This skill owns the scope and architecture call. It ends when the document is
written and reviewed. It does not build anything; `development-loop` owns
forward motion.

## 0. Align with the user

Invoke `/dfrysinger-skills:grill-me` before fixing scope. Interview the user one
question at a time, give a recommended answer with each question, and explore
the codebase instead of asking anything the repository can answer. Walk the
decision tree until the end user's job, success condition, boundaries, and
load-bearing assumptions are mutually understood.

Persist the resulting decisions as exact user quotes with enough context to
classify their authority in a durable pre-proposal evidence packet. Record the
decision-record path returned by `grill-me`, give the packet a revision
identifier, and pass both to each challenge phase. A prior interview may be
reused only when its objective, users, constraints, and non-goals still match
this work. A material scope change returns here before the document is revised.

**Complete when** the user need, observable success condition, boundaries, and
unresolved decisions are explicit, and no answer obtainable from the codebase
remains a question for the user.

## 1. Fix the scope

State the objective in one sentence, then write the non-goals.

Non-goals do more work than the objective. They are the boundary a later
reviewer is held to, and the defence against a bounded fix growing into a
speculative framework. Name the code, behavior, and callers explicitly outside
this change, including generalizations you considered and rejected.

Ask what a supported caller needs **today**. A generalization required by a
hypothetical future caller belongs in the non-goals, not the design.

**Complete when** the objective is one sentence and at least one non-goal names
something a reasonable person would otherwise have assumed was in scope.

## 2. Classify: systemic or critical

**Systemic** — the change intentionally alters shared state or concurrency,
persistence or version authority, a public API, schema, migration, or protocol,
cross-component architecture, a reusable framework or central data-access
boundary, or multiple independent user flows.

**Critical** — security, authentication, authorization, data loss or
corruption, privacy or compliance, production infrastructure, audited controls,
or fail-closed enforcement.

Critical wins when both apply. A critical document additionally carries an
explicit rollback path and states what evidence proves the boundary fails
closed.

Work that turns out to be bounded — localized, reusing established architecture,
touching none of the boundaries above — does not need this document. Say so and
send it to `development-loop`, even when the document was what you were asked
for.

Record the lane in the document. `development-loop` reads it back to size its
later gates, so a lane left unstated silently downgrades review, specialist
coverage, and the final end-to-end run.

**Complete when** the document names one lane; for critical, a rollback path
and the evidence that proves the boundary fails closed.

## 3. Record constraint provenance and prepare the challenge packet

Architecture is shaped by constraints, so record the ones that materially
narrow the design before selecting mechanisms. For each hard constraint, write:

- the constraint;
- its provenance: user outcome, policy, platform behavior, measured capacity,
  compatibility promise, or implementation default;
- the evidence or owner that makes it binding;
- the outcome or invariant it protects;
- the condition that requires it to be revisited.

Every hard numeric limit needs measured demand, platform evidence, or a named
policy owner. Prior configuration and earlier implementation are provenance,
not proof that the limit must remain.

Do not accept the author's provenance table as self-proving. Assemble the exact
user decisions, boundaries, existing capabilities, failures, and constraint
evidence into a closed, architecture-neutral packet with its own revision
identifier. Do not include proposed mechanisms. Section 6 gives this packet to
a fresh challenger before revealing the completed proposal.

Define the design's **reframe gate**. Implementation returns here before adding
another component when a recorded revisit condition fires, a new subsystem
mainly preserves an implementation default, repeated fixes merely move failure
to the next internal boundary, or a proven predecessor now satisfies the
supported caller with less machinery.

The reframe record answers:

1. What user-visible outcome is blocked?
2. Which constraint creates the blocker, and where did it come from?
3. What concrete invariant fails if the constraint changes?
4. What is the simplest design without that constraint?
5. Which option has fewer trusted components and maintenance surfaces?

The answer replaces further implementation until the work order and its review
reflect the new architecture.

Keep one durable reframe status in the work order:

- `CLEAR` means no recorded revisit condition is currently met; state the
  evidence used to reach that conclusion.
- `OPEN` means implementation is stopped; record the triggering evidence and
  answer all five reframe questions above.

Implementation starts or resumes only from `CLEAR`. Closing an `OPEN` record
requires the revised work order and its design review evidence, not merely an
author statement that the concern is resolved.

**Complete when** every architecture-shaping constraint has provenance and a
revisit condition, every hard numeric limit has external or measured
justification, the sealed challenge packet has a revision identifier, the
document names the conditions that force reframing, and its durable reframe
status is `CLEAR` with evidence or `OPEN` with all five answers.

## 4. Write the document

Write or update a durable document containing:

- objective and non-goals;
- the lane from section 2;
- the constraint-provenance record and reframe gate from section 3;
- reuse contract — what existing helper, state owner, API, or error pattern
  carries this, and why anything new is required rather than convenient;
- affected data flow and the existing connection points it touches;
- realistic failure model — how this breaks in production, not in theory;
- hard invariants and acceptance criteria;
- migration and rollback when relevant;
- deterministic check definitions (section 5);
- a short **Definition of Done** under its own heading, covering exactly this
  change's scope.

Put it where the work lives — the repository, alongside the code it governs —
so a future agent inherits it. A design that exists only in a chat transcript
is not durable.

Give the Definition of Done a unique heading. Downstream runs point at it by
name.

**Complete when** every element above is present and the acceptance criteria
are observable — each one names something that can be checked, not a quality
someone would have to judge.

## 5. Define the check contract

For each proposed test or guard, state:

- the behavior or invariant it protects;
- the setup, input, or state transition that exercises it;
- the expected pass and failure signal;
- why that failure proves the intended contract.

Prefer, in order:

1. types and schemas that make invalid states impossible;
2. behavioral tests;
3. dependency and architecture checks;
4. text matching, as a temporary ratchet only.

Reach for `guardrails` only for cross-cutting rules likely to drift that types
and functional tests express badly. An invariant that is useful but not needed
to ship this change is tagged `REGISTER-ONLY` in the invariant register, or
recorded as follow-up work, rather than blocking.

Name any guard that must exist before implementation to constrain the work, and
why. `development-loop` writes it; nothing executable is created here.
Everything else is written alongside the implementation and reviewed with it.

**Complete when** every acceptance criterion in section 4 has at least one
check that would fail if the criterion were violated.

## 6. Review the work order

Run `constraint-challenge` immediately before normal design review as one
two-pass challenge:

1. Launch a fresh read-only challenger with only the sealed evidence packet.
   Persist its pass-1 minimum design before exposing the proposal.
2. Continue the same challenger with the finished work order and proposed
   architecture for pass 2.

Apply its verdict and gate: remove unsupported machinery, reframe the
end-to-end route when required, and resolve or explicitly block unknown
load-bearing premises. If that changes the work order, repeat pass 2 against
the new exact revision until the current gate permits design review. An
`ESCALATE` verdict returns to section 0 for the smallest required user
decision, creates a new evidence-packet revision, and reruns both passes before
normal design review.

Run `dual-review`'s normal bounded loop over the complete design document and
its check contract. Tell both reviewers this is a design review so
`dual-review` applies its disclosed architecture and scope lens before
implementation detail.

Start with `dual-review`'s standard packet. For this review, both reviewers also
receive:

- this `design-doc` skill as the authoring and completion rubric;
- the `scout` report, when one informed the chosen direction;
- the issue, user decisions, architecture documents, ADRs, invariants, or
  repository conventions that directly constrain the design;
- the constraint-provenance record, including every inherited default that
  materially shaped the design.
- the persisted independent constraint-challenge record, including its
  minimum design, three highest-leverage assumptions, reverse-trace gaps, and
  verdict;
- the user's relevant statements as exact quotes rather than an author's
  interpretation, together with their top-level, scoped, tactical, or
  ambiguous classification and the end user's job to be done.

The design document is the subject under review; the other artifacts are
evidence and rubric. Keep unrelated discovery, rejected alternatives, and
historical discussion out of the packet.

`design-doc` owns the back-to-back challenge immediately before the normal
two-family review. `dual-review` verifies that the resulting current record is
present and reflected honestly in the work order.

**Complete when** the independent challenge is current, its gate permits this
design review, and `dual-review`'s verification criteria are met.

## 7. Stop

The work order is finished. Present it.

Continue into implementation only on an instruction that already exists —
given in advance ("write the doc, then continue to development-loop") or after
you present it. On that instruction, hand the document to `development-loop`,
which owns whether the run is attended and every gate from build through land.

**Complete when** the reviewed document is presented, and `development-loop` is
invoked if an instruction to continue already exists.

## Pitfalls

- **Transcript as design.** A document that assumes the reader saw the
  conversation is not a work order. Write for the agent who arrives after a
  compaction.
- **Non-goals left empty.** The section that constrains reviewers and prevents
  scope growth is the one most often skipped, because it is the only one that
  costs something to write.
- **Designing for hypothetical callers.** Generalization justified by a caller
  that does not exist is the most common way a systemic change becomes a
  critical one.
- **Inherited mechanism as requirement.** A prior limit, service, or protocol
  is evidence about history, not proof that the new design must preserve it.
- **Self-certified provenance.** Writing "product decision" or "security
  requirement" beside an assumption does not prove its source or scope.
- **Every user statement treated as constitutional.** Top-level needs and
  product direction anchor the work. Tactical suggestions, quick approvals,
  and ambiguous acknowledgements remain challengeable, especially when the
  user did not inspect the implementation consequences.
- **Paraphrased authority.** Give the challenger the user's exact words. An
  agent's cleaner interpretation can erase uncertainty or broaden scope.
- **Written-only drift detection.** Architecture, tests, adapters, and proof
  obligations can enforce an unwritten rule. Reverse-trace the actual work,
  not only the requirement sentences.
- **Literal charter compliance.** A work order can remain internally
  consistent after its assumptions stop serving the user outcome. That is when
  its reframe gate should fire.
- **Unobservable acceptance criteria.** "Handles errors gracefully" cannot pass
  or fail. Each criterion names a checkable state.
- **Check contract as a test list.** Naming tests without stating what each
  proves produces coverage that passes while the invariant is broken.
- **Building.** Writing code here skips every gate `development-loop` owns —
  live proof, implementation review, landing — because none of them have run
  yet.

## Verification

The document is done when:

1. the objective is one sentence and the non-goals are explicit;
2. the user need, observable success condition, boundaries, and material
   decisions were established through a current `grill-me` interview;
3. it names one lane, with rollback and fail-closed evidence when critical;
4. every architecture-shaping constraint has provenance and a revisit
   condition;
5. the durable reframe status is checkable, and implementation proceeds only
   while it is `CLEAR`;
6. the reuse contract explains why anything new exists;
7. acceptance criteria are observable;
8. every acceptance criterion has a check that would fail if violated;
9. it carries a Definition of Done under a unique heading;
10. the bounded `dual-review` process met its verification criteria;
11. a fresh-context constraint challenger derived its minimum before seeing
    the proposal, then independently verified the completed work order's product
    and security premises, reverse-traced the actual machinery, and produced a
    current gate that permits this design; and
12. someone who was not in the conversation could build from it.
