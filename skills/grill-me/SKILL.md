---
name: grill-me
description: Interview the user one decision at a time until a plan's user need, scope, assumptions, and branches are settled. Use when planning needs explicit user alignment, scope is ambiguous or likely to drift, or another skill requires a decision-tree interview before proceeding.
---

# grill-me

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase instead.

Persist every decision as the interview reaches it, including decisions left
unresolved, to the caller's decision-record path. When none is supplied, use
`direct-user-decisions.json` beside the plan. Each record has:

- a stable `event_id`;
- the question and recommended answer shown to the user;
- the user's complete answer as an exact quote;
- its available context and authority classification; and
- `resolved: true`, or the precise unresolved decision.

Never rewrite the user's answer into a cleaner quote. Return the decision-record
path and unresolved event IDs to the caller.

**Complete when** every material branch is resolved or explicitly recorded as
unresolved, and the caller can trace each scope decision to an exact answer or
repository evidence.
