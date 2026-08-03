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

## 3. Write the document

Write or update a durable document containing:

- objective and non-goals;
- the lane from section 2;
- reuse contract — what existing helper, state owner, API, or error pattern
  carries this, and why anything new is required rather than convenient;
- affected data flow and the existing connection points it touches;
- realistic failure model — how this breaks in production, not in theory;
- hard invariants and acceptance criteria;
- migration and rollback when relevant;
- deterministic check definitions (section 4);
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

## 4. Define the check contract

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

**Complete when** every acceptance criterion in section 3 has at least one
check that would fail if the criterion were violated.

## 5. Review the work order

Run `dual-review`'s normal bounded loop over the complete design document and
its check contract.

Start with `dual-review`'s standard packet. For this review, both reviewers also
receive:

- this `design-doc` skill as the authoring and completion rubric;
- the `scout` report, when one informed the chosen direction;
- the issue, user decisions, architecture documents, ADRs, invariants, or
  repository conventions that directly constrain the design.

The design document is the subject under review; the other artifacts are
evidence and rubric. Keep unrelated discovery, rejected alternatives, and
historical discussion out of the packet.

**Complete when** `dual-review`'s verification criteria are met.

## 6. Stop

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
2. it names one lane, with rollback and fail-closed evidence when critical;
3. the reuse contract explains why anything new exists;
4. acceptance criteria are observable;
5. every acceptance criterion has a check that would fail if violated;
6. it carries a Definition of Done under a unique heading;
7. the bounded `dual-review` process met its verification criteria;
8. someone who was not in the conversation could build from it.
