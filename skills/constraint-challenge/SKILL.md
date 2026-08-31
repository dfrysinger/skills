---
name: constraint-challenge
description: Challenge the load-bearing premises of systemic or critical work with a blind minimum-design pass, then reconcile it against the proposal. Use when such work changes its design, charter, Definition of Done, trust boundary, constraint, or scope; before it adds a subsystem, service, protocol, store, broker, compiler, fork, repository, language, or platform lane; when adapters, proof, or repeated fixes grow without user-visible progress; when completed work becomes the argument for keeping the architecture; or when the governing run lifecycle reports a scheduled challenge due.
---

# constraint-challenge

A **blind** challenger derives the minimum design from evidence alone, then
**reconciles** what it found against the proposal. It attacks the
**load-bearing** premises of systemic or critical work. This is a challenge to
premises, not a third code reviewer.

## 1. Triggers and invocation

Run the challenge before normal `dual-review` approval of any systemic or
critical design; after any design, charter, Definition-of-Done, trust-boundary,
constraint, or scope change; before adding a subsystem, service, protocol,
store, broker, compiler, fork, native binary, repository, implementation
language, or platform lane; when an adapter, compatibility layer, proof
machinery, or repeated fix grows without user-visible progress; when preserving
completed work becomes an argument for preserving the architecture; and when
the governing run lifecycle reports that its scheduled challenge is due.

Event triggers run immediately; a caller-owned schedule is a backstop this
skill does not own. A trigger runs only this challenge, not `dual-review`'s
two-family review.

Run the challenger in a fresh, read-only context that did not author the plan
and distrusts both the proposed architecture and the author's rationale. It
reads, quotes, and reasons; it does not build, test, mutate, or propose a
generalized replacement whose callers do not exist.

Pass 1 sees only the sealed evidence packet: its revision identifier, an
architecture-neutral extraction of product outcomes, observable acceptance
criteria, non-negotiable boundaries and rollback, direct user decisions as
exact quotes with their context and the supported user journey, and relevant
external policy, platform, compatibility, and observed-failure evidence. Pass 2
adds the current work order and Definition of Done, the proposed architecture,
the material tasks, components, tests, and proof added since the prior
completed record, and the prior challenge record.

One agent normally runs both passes back to back: expose the packet, persist
the pass-1 record, reveal the proposal. When that agent is gone after
authoring, compaction, or a later trigger, launch a fresh **blind**-context
agent and hand it the sealed pass-1 record to **reconcile**. Quarantine is an
input boundary, not a reason to pause authoring between passes.

Persist the record in the work order or durable baton and return to the
governing workflow with its verdict and gate. A pass-1 record is current only
for the exact evidence-packet revision it reviewed. A final record is current
only when it also names the exact work-order revision and work graph it
reviewed and no mandatory event or scheduled trigger fired afterward. Reuse one
current record whose gate permits the exact pending action instead of rerunning
the challenge for the same revisions, work graph, and action.

Budget 20 minutes: the three **load-bearing** assumptions selected in section
4.3 plus the material mechanisms added since the prior completed record. When
that slice cannot establish a verdict, return `UNKNOWN` naming the smallest
missing evidence rather than widening into a repository audit.

## 2. Provenance is not authority

One rule governs every claim in both passes. Each of these establishes only
what it says:

- an author's label such as `product decision`, `security requirement`, or
  `existing architecture` is a claim;
- a rule, limit, default, or mechanism observed in force proves the present
  state;
- a tactical user approval proves permission at that moment;
- an accepted design, working implementation, completed proof, sunk work, or
  compatibility with its own callers proves a mechanism is available.

None of them establishes necessity, which requires a trace to an **authority
anchor**: a verified user need, reachable risk, external obligation, measured
demand, or current compatibility promise. Mark necessity `FAILED` when the
bounded evidence is complete enough to show no such trace exists, and `UNKNOWN`
when one named unavailable fact would decide it. Holding an incumbent while
evidence is missing is an operational precaution, not authority to add work
that accommodates it.

Apply one proof standard symmetrically to incumbent and alternative. Where a
property lacks evidence on both sides, mark both `UNKNOWN` and name the same
decisive evidence.

## 3. Pass 1 — derive the minimum design blind

### 3.1 Quarantine architecture out of the packet

The challenger owns the last-mile quarantine. Scan every pass-1 input,
including exact user quotes, for named components, protocols, services, stores,
compilers, brokers, execution paths, implementation-specific proof, and any
other mechanism or constraint that presupposes a design. Group repetition, then
record each distinct material premise and its disposition in `quarantine` and
keep it out of the job and the minimum design until independent evidence traces
it to a product outcome or security boundary. It re-enters as a candidate in
section 3.5 once evidence establishes the path exists and supports the same
outcome. An accepted design document is not architecture-neutral: it supplies
its objective, supported caller, observable outcomes, non-negotiable
boundaries, and rollback promise, while its architecture-shaped non-goals,
component names, protocol choices, and proof plans stay quarantined.

### 3.2 Classify authority

Quote the user exactly. Every `authority.direct_user_quotes` entry carries
`quote`, `source`, `event_id`, and `exact_match: true`: `source` is a supplied
durable decision record or baton quote ledger, `event_id` identifies one record
in it, and `quote` reproduces that record's complete value byte for byte. Copy
quote and identifier together from that record. Where no exact source match
exists, omit the entry and record the missing authority as `UNVERIFIED
PARAPHRASE`, which binds nothing. Include only quotations used as authority,
identify incidental, superseded, or formatting-damaged decisions by source
record instead, and keep interpretation in
`authority.inferred_product_judgment`.

Classify each user statement:

- **Top-level user need or product direction** — the job the product must do,
  who it serves, the outcome it creates, the user's stated risk or business
  priorities. Authoritative within its stated scope.
- **Scoped product decision** — an explicit choice among understood outcomes.
  Binding for the named scope while consistent with top-level direction.
- **Tactical approval or implementation suggestion** — low-level architecture,
  mechanisms, defaults, estimates, acknowledgements. Challenge it like an
  agent-authored assumption; the user's limited time and partial code context
  mean it does not prove they saw hidden cost, security consequences,
  duplicated machinery, or a simpler existing path.
- **Ambiguous statement** — unknown, never upgraded through interpretation.

Top-level goals can conflict. Then quote each side exactly, state the concrete
product or risk tradeoff, identify the end-user job each serves, and return
`ESCALATE` with the smallest decision the user must make. Convenience and
recency do not supersede a side of a genuine top-level conflict.

### 3.3 Root the trace in the job to be done

Record who the end user is, what situation starts the journey, what progress
they seek, what makes that difficult, risky, slow, or confusing today, and what
observable product result means the job is done. Where direct evidence is
incomplete, infer a likely job or preference from the product's broader
purpose, label it `INFERRED`, cite the product evidence, and state confidence.
Use an inference to test whether the plan makes product sense, never as the
user's words and never to override a top-level direction.

### 3.4 State the required properties

Derive each requirement from the job under a stable `requirement_id`, as a
property rather than a mechanism. Durability, atomicity, isolation,
reviewability, and bounded authority are properties; a service, protocol,
store, compiler, broker, or runtime is a candidate mechanism.

Each requirement records its `requirement_kind` (`product`, `security`,
`compatibility`, `resource`), the person or supported caller with the need, the
authority anchor establishing it, the observable result that satisfies it, the
actors and operations it covers, and the user-visible result that fails without
it. Together these entries are the trust-domain map: a control belongs to a
trust domain, not to a catalogue of reusable restrictions.

Two lenses from section 5 fire here — `trust-transfer.md` for every `security`
requirement, every control transfer, and every unresolved security, integrity,
or trust-boundary control; and `resource-demand.md` when a resource boundary
motivates the work.

### 3.5 Build the capability ledger

Inventory every candidate mechanism the bounded evidence exposes into one
`capability_ledger` keyed by a stable `candidate_id`. Search by required
property across every layer already available to the caller and runtime, not
only the proposal's namespace, abstraction level, or assembled end-to-end
paths. Inventory at capability granularity: a bounded permission, exception,
optional mode, or narrower interface inside a component is its own candidate,
because a component's headline role is not its complete capability set. For
each behavioral evidence source, record either the candidates it exposes or
that it exposes none relevant to the required properties.

Decompose every deny-by-default, allowlist, or sandbox boundary into both
sides. Record what it denies, then create a separate candidate for each
explicitly allowed operation and its effects. An allowed capability is never
summarized as part of the denial that surrounds it.

Run a **grant census** before abstraction: enumerate every explicit grant,
allow rule, exception, bypass, and delegated target in each control source
before grouping entries that share operation, owner, and lifecycle into
candidates.

Split allowed targets again when their owner or lifecycle differs. A private
temporary resource and a caller-, operator-, service-, or externally owned
resource cannot share one candidate or inherit each other's lifetime.

Inventory an allowed capability by **affordance**: record every material
external or persistent effect the granted operation can produce, not only its
stated purpose or current caller's intended use. Purpose, cleanup, and
lifecycle evidence decide the resolution; they do not erase capability.

Classify lifetime from resource ownership and evidenced teardown. Mutation of
a resource owned outside the controlled actor is persistence-capable unless
evidence proves it is destroyed before a later actor can observe it; an
unknown resource lifecycle is `UNKNOWN`, never ephemeral by assumption.

Each candidate records:

- `origin` — the evidence source, layer, and component it comes from;
- `operations` and `effects` — what it can do and what persistent or external
  effects it produces; classification derives from these alone, never from the
  policy or component label that introduced it;
- `requirements` — one entry per `requirement_id` it could bear on, with a
  pass-1 disposition of `PROVIDES`, `MAY_PROVIDE`, or `NOT_RELEVANT`, where
  `NOT_RELEVANT` holds only when none of the recorded effects can produce any
  part of that requirement;
- `evidence`; and
- `emulates` — the abstraction it adapts, virtualizes, proxies, or emulates.

Where a candidate `emulates` an abstraction, search the evidence for a native
provider of that abstraction and enter that provider as its own candidate.
Every authority channel that can exercise a protected capability is also a
candidate: when one control narrows a capability and another service, tool,
adapter, or side channel recreates it for the same actor, they are one
boundary, and the first control earns no credit for a restriction the second
bypasses.

A candidate that enters the ledger stays in it through pass 2.

### 3.6 Compose the minimum design

Compose the smallest path over ledger candidates that satisfies the verified
journey and the non-negotiable boundaries, and record it as
`minimum_design.simplest_existing_path` — the simplest supported path found
anywhere in the bounded evidence, not the path closest to the proposal. Where
the packet cannot establish the relevant path set, mark the minimum design
`UNKNOWN` rather than converting unsupported claims into requirements. Where
the path crosses an interface between candidates, read
`boundary-composition.md`.

## 4. Pass 2 — reconcile against the proposal

### 4.1 Reconcile the capability ledger

Begin pass 2 by reconciling the persisted pass-1 record: every ledger
candidate, quarantine entry, required property, and selected assumption takes
an explicit pass-2 disposition. A promising candidate does not disappear
because the proposal supplies a more detailed incumbent.

Determine applicability before judging proof. If a candidate's operations or
effects could satisfy a requirement in a supported topology, link the pair;
missing wiring, lifecycle, or production evidence makes the resolution
`UNKNOWN`, not inapplicable.

Resolve every recorded candidate/requirement pair exactly once:

- `SELECTED` — evidence shows the candidate satisfies that requirement on the
  selected path.
- `REJECTED` — names a concrete incompatibility. That none of the candidate's
  recorded effects can produce any part of the requirement is one; nothing in
  section 2 is.
- `UNKNOWN` — names the decisive missing evidence, which is never existing
  implementation, completed proof, or possible usefulness.

Rejection requires positive evidence of incompatibility. Never infer a
candidate is ephemeral, local, single-run, or otherwise incapable merely
because persistence, restart, topology, or production wiring evidence is
absent; resolve that pair `UNKNOWN`.

Compare against the required property, not the incumbent ownership topology.
An existing actor, service, process, or resource placement is not a concrete
incompatibility unless an authority anchor requires that placement itself.

Reopen a pass-1 disposition whenever pass 2 reveals an additional operation,
permission, lifecycle, or effect: expand the candidate's `operations` and
`effects` first, then resolve again. The pass-1 label never overrides newly
visible capability evidence.

### 4.2 Build the material scope tree

Material scope is finite: the nodes present in the changed work graph and
proposal since the prior completed record, plus each ancestor a reverse trace
reaches from them. Nothing outside that set is in scope. Identify each node's
identity, parent, and kind, then assign its provisional rank. Persist the full
section 7 fields only for active nodes selected in section 4.3; deferred nodes
retain their ID, rank, and deferral reason.

For each active node, comparison closure is a substitution invariant. Its
`alternatives` holds the incumbent and every ledger candidate that could
replace it for one or more required properties. Complementary candidates
remain resolved in the ledger and composition traces; do not duplicate them
into unrelated node comparisons merely because they share a broad requirement
ID.

Each alternative references one existing `candidate_id`. When replacement
requires several candidates, record that path in `minimum_design` and the
node's counterfactual; never invent a combined candidate ID.

The incumbent support rule follows from that set:

- `SUPPORTED` requires an authority anchor that requires the mechanism itself
  rather than only its property, and every substitute alternative resolved
  `REJECTED` by concrete incompatibility;
- any substitute alternative left `UNKNOWN` makes the node `UNKNOWN`, naming
  the same missing evidence;
- a substitute alternative `SELECTED` on a simpler path makes the node's
  necessity `FAILED`.

In section 4.2, reconcile every pass-1 and pass-2 lens result onto its material
node. A lens-assigned `FAILED` or `UNKNOWN` overrides a weaker result from the
incumbent support rule. When that node is deferred, retain its `node_id` and
status in `lens_findings`; the result still participates in section 6.

Parent each mechanism under its nearest evidenced actual caller — a runtime
actor, process, user flow, or external consumer that invokes or depends on it.
A source file, generated artifact, test, package, or component that implements
the mechanism is evidence of existence, not a caller. A mechanism survives a
failed caller only where evidence shows a supported outcome independently
invokes it.

Assign transition dispositions consistently:

- `RETAIN` — supported necessity and known existence, whether the node exists
  already or must be created.
- `RETIRE` — a present node with failed necessity, once a safe transition is
  established.
- `HOLD_PENDING_EVIDENCE` — a node that is or may be present whose existence,
  necessity, or removal safety is unresolved. It preserves current operation
  and authorizes no expansion of itself or its dependent planned work; a
  control on a security, integrity, or trust boundary is held under the rule in
  [`references/trust-transfer.md`](references/trust-transfer.md).
- `EXCLUDE_FROM_TARGET` — a proposed or absent node whose necessity is not
  supported. A node with failed necessity authorizes no new or expanded
  mechanism whatever its transition disposition.

Removing or reframing a node excludes every descendant whose only supported
caller or property came through it; a descendant survives only on an
independently evidenced caller or required property outside the removed path.

### 4.3 Rank the load-bearing three

Rank material nodes by how much the assumption beneath them multiplies:

- components, tasks, repositories, or languages;
- credentials, trusted actors, or enforcement boundaries;
- platforms and release artifacts;
- stored state, public contracts, migrations, or irreversible decisions;
- builds, live proof, validation matrices, and operating cost; and
- maintenance remaining after the current feature ships.

Raise the rank when provenance is weak or the assumption sits several reasoning
steps from the user-visible outcome. Carry the three highest into
`scope_tree.active` for section 4.4; list every other material node in
`scope_tree.deferred` as `node_id`, `rank`, and deferral reason, naming missing
evidence only when evidence is the reason.

When the resource-demand lens fires, its largest weakly authorized multiplier
is mandatory active scope and displaces a lower-ranked node. It cannot be
deferred while a dependent boundary, limit, or optimization is selected.

### 4.4 Trace, peel, and run counterfactuals

For each active node:

- **Forward** — identify the components, implementation, tests, proof, and
  operations the assumption creates.
- **Reverse** — for every material work item under it, identify the authority
  anchor that requires that item. Reverse-trace even when no design sentence
  names the premise, since repeated implementation behavior, acceptance
  machinery, adapters, fixtures, and proof requirements create unwritten
  constraints. A work item whose reverse trace ends at an implementation
  default, historical mechanism, sunk work, unsupported assertion, or missing
  source becomes its own node with no authority anchor.
- **Counterfactual** — state the assumption removed now, enumerate the
  dependent machinery that disappears with it, name the simplest evidenced
  supported path after removal, and decide whether that path reaches the user
  outcome. Where the proposal survives, name the evidence-backed
  incompatibility that defeats the simpler path. A future contingency is a
  fallback plan, not a counterfactual; where neither result can be
  established, return `UNKNOWN`.

Use **layer peeling** when a leaf mechanism fails its trace: continue upward
through the service, protocol, store, compiler, broker, or other enclosing
architecture that made the leaf look necessary. The trace ends only at a
verified authority anchor or at a finding that the enclosing architecture is
unsupported; replacing one leaf while preserving an unsupported parent is not a
minimum-design result.

Use these traces to confirm, clear, or overturn each provisional
`necessity_status`. Where a trace exposes a higher unsupported parent, swap it
into the active set and rerank within those three rather than expanding to a
full-tree trace.

## 5. Conditional lenses

Read a lens when its context fires, and record its result under
`lens_findings`:

| Read | When |
| --- | --- |
| [`references/resource-demand.md`](references/resource-demand.md) | a capacity, latency, quota, cost, or other resource boundary motivates the work |
| [`references/concurrency-lens.md`](references/concurrency-lens.md) | the work claims or retains concurrency, fencing, locking, leasing, or coordination machinery, or an active node persists or coordinates state |
| [`references/boundary-composition.md`](references/boundary-composition.md) | an active node exposes a custom API, service, store, broker, or protocol, or the minimum design composes candidates across an interface |
| [`references/trust-transfer.md`](references/trust-transfer.md) | a requirement is `security`, a control moves across callers, actors, or operations, or a security, integrity, or trust-boundary control has unresolved necessity or removal safety |

## 6. Verdict and gate

- `CONTINUE` — the current design is the minimum justified design.
- `NARROW` — remove or reduce identified machinery, update the work order, and
  rerun this comparison before implementation continues.
- `REFRAME` — a load-bearing premise failed; stop implementation and return to
  `design-doc`.
- `ESCALATE` — verified authorities conflict; present the smallest product
  decision required, each side quoted exactly.
- `UNKNOWN` — evidence for a load-bearing premise is unavailable. Treat a
  product or implementation premise as nonbinding; for a security boundary,
  fail closed and obtain evidence before continuing.

Derive the verdict from the highest failed or unresolved `necessity_status` in
the active nodes and fired lens results:

- a failed node permits `NARROW` only when its parent path remains
  independently supported, excluding it does not change which path reaches the
  user outcome, the narrowed target excludes every dependent descendant, and
  every remaining load-bearing architecture node on that route is `SUPPORTED`;
- any other failed necessity, including a failed outcome or one that changes
  the selected architectural path, requires `REFRAME` around the nearest
  supported ancestor or verified user need;
- a conflict between verified authorities requires `ESCALATE`;
- an unresolved load-bearing architecture node on the remaining selected route
  requires `UNKNOWN`, even when a different leaf or parameter failed; choose
  `REFRAME` instead when the evidence supports an end-to-end route that avoids
  the unresolved node;
- `CONTINUE` requires every node needed by the current action to be
  `SUPPORTED`.

The architectural path is the end-to-end route from the user's trigger to the
observable outcome and required trust properties, not every internal branch of
the work order. Removing a subsystem, many dependent tasks, or substantial
completed work is still `NARROW` while that route holds; `REFRAME` is for a
different route or a different user outcome.

`CONTINUE` gates `CLEAR`. `NARROW`, `REFRAME`, `ESCALATE`, and
security-relevant `UNKNOWN` gate `BLOCKED`. A non-security `UNKNOWN` gates
`PARTIAL`, naming non-overlapping `blocked_scope` and `permitted_scope` and
permitting an action only when it lies wholly inside the permitted scope.
`permitted_scope` holds only actions independent of the blocked unknown nodes,
and no machinery whose only reverse trace ends at a failed or excluded
ancestor.

A `BLOCKED` or `PARTIAL` record gains no broader permission until its required
action or missing evidence changes the work order or evidence packet and a new
challenge clears that scope. Recorded statuses, dispositions, verdict, gate,
and scopes agree, and the verdict is never softened to preserve completed work.

## 7. Record

Persist this record in the work order or durable baton. Braces mark nested keys
and brackets mark repeated records; both are written out in full:

```text
reviewed_at:
inputs: {evidence_packet_revision, work_order_revision, work_graph_cutoff, evidence_sources}
quarantine: [{premise, disposition, independent_trace_or_exclusion}]
authority:
  direct_user_quotes: [{quote, source, event_id, exact_match: true}]
  classification:
  inferred_product_judgment:
  conflicts:
job_to_be_done:
required_properties: [{requirement_id, requirement_kind: product | security | compatibility | resource,
  property, authority_anchor, observable_result, covered_actors_and_operations,
  fails_if_removed, security_trace}]
capability_ledger: [{candidate_id, origin, operations, effects, emulates, evidence,
  requirements: [{requirement_id, pass1_disposition: PROVIDES | MAY_PROVIDE | NOT_RELEVANT,
  pass2_resolution: SELECTED | REJECTED | UNKNOWN, reason}]}]
minimum_design: {simplest_existing_path, composition}
scope_tree:
  active: [{node_id, parent,
    node_kind: outcome | architecture_path | subsystem | leaf_mechanism | parameter,
    existence_status: PRESENT | PROPOSED | ABSENT | UNKNOWN,
    necessity_status: SUPPORTED | FAILED | UNKNOWN,
    transition_disposition: RETAIN | RETIRE | HOLD_PENDING_EVIDENCE | EXCLUDE_FROM_TARGET,
    requirement_ids, claimed_authority, authority_anchor, missing_evidence,
    dependent_machinery, scope_removed_if_excluded,
    actual_callers: [{actor, actor_kind: runtime_actor | process | user_flow | external_consumer,
      operation, evidence}],
    alternatives: [{candidate_id, resolution: SELECTED | REJECTED | UNKNOWN, reason}],
    forward_trace, reverse_trace, counterfactual}]
  deferred: [{node_id, rank, reason}]
lens_findings:
scope_avoided_or_added:
verdict: CONTINUE | NARROW | REFRAME | ESCALATE | UNKNOWN
gate_status: CLEAR | PARTIAL | BLOCKED
blocked_scope:
permitted_scope:
```

## 8. Complete when

- The record names the exact evidence-packet revision and, after pass 2, the
  exact work-order revision and work-graph cutoff.
- Every `authority.direct_user_quotes` entry byte-matches its named source
  record, and interpretation sits outside that field.
- Every distinct material architecture-shaped premise from pass 1 carries a
  `quarantine` disposition with an independent trace or exclusion, or the
  record states that none was visible.
- Every ledger candidate carries recorded `operations` and `effects`, and every
  recorded candidate/requirement pair carries exactly one pass-2 resolution whose
  `REJECTED` names a concrete incompatibility and whose `UNKNOWN` names
  decisive missing evidence.
- Every deny-by-default, allowlist, or sandbox source records both the denied
  set and each explicitly allowed operation as separate ledger candidates.
- Every active node's `alternatives` contains its incumbent and every genuine
  substitute exactly once, excludes merely complementary candidates, and its
  three statuses agree with the incumbent support rule and with each other.
- When resource demand is material, the largest weakly authorized multiplier
  is active; no dependent boundary uses an implementation maximum or appears
  in the minimum or permitted scope while that multiplier or supported demand
  remains unresolved.
- Each of the three active nodes carries an actual-caller list, a forward
  trace, a reverse trace, and a removal counterfactual; every other material
  node is deferred with its rank and reason.
- Every fired lens has a recorded `lens_findings` result.
- Every lens-assigned `FAILED` or `UNKNOWN` identifies its material `node_id`
  and is reflected in the verdict even when that node is deferred.
- One verdict, its derived `gate_status`, and any `PARTIAL` scopes are
  persisted and consistent with the recorded statuses.
