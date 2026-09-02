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

For an observed failure or mismatch, `development-loop` diagnosis first
identifies the earliest verified divergence and smallest proposed response.
The failure alone is not an event trigger. Run one challenge when that response
matches a trigger above, folding related observations and discarded hypotheses
that led to the same response into one evidence revision. When a diagnostic
probe itself would change architecture, trust, authority, irreversible state,
or a production or release contract, challenge that probe before it runs. A revisit
condition that fires without an observed failure forms its trigger immediately
from the triggering evidence.

Before launching a challenger, the caller persists a short **challenge
admission** in the durable baton:

```text
challenge_admission: {
  current_record, pending_action, changed_inputs,
  trigger_kind, decision: REUSE | DELTA | FULL, reason
}
```

`REUSE` is mandatory when the current record names the same evidence packet,
work-order revision, work graph, and action, or when new evidence and the next
action remain wholly inside its permitted scope. A consumed action, a failed
attempt, new evidence, artifact movement, elapsed time, or a prior record's
instruction to run another challenge does not independently form a trigger.
The caller first diagnoses the result and tests the resulting proposed response
against the trigger list. When no trigger matches, record `REUSE` and continue
under the current gate without launching this skill.

Use `DELTA` when a trigger is real but the user job, authority anchors,
requirements, selected architecture path, and trust domains remain current.
Give the blind pass the prior pass-1 record plus only the new sealed evidence;
it records which prior conclusions the evidence invalidates. Pass 2 receives
the prior final record, current proposal delta, and changed work graph. Use
`FULL` when no current record exists or when the job, authority, required
property, selected architecture path, or trust-domain map changed.

Admission classifies what the proposed response changes, not whether that
change is justified. A response that adds or relaxes a permission, trust
boundary, subsystem, or other triggered mechanism remains a real `DELTA` or
`FULL` trigger even when the challenge later marks its necessity `FAILED`.
Preserve the admitted `trigger_kind` in the final record; do not erase the
trigger merely because the verdict rejects the proposal.

Event triggers run immediately once formed; a caller-owned schedule is a
backstop this skill does not own. A trigger runs only this challenge, not
`dual-review`'s two-family review.

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
reviewed and no mandatory event or scheduled trigger fired afterward. Later
runtime evidence does not become reviewed evidence, but a persisted `REUSE`
admission keeps the record's campaign gate applicable when diagnosis confirms
that the evidence invalidates none of its subject, authority, trust, acceptance,
or effect invariants. Reuse one applicable record whose gate permits the exact
pending action instead of rerunning the challenge.

Budget 20 minutes: the three **load-bearing** assumptions selected in section
4.3 plus the material mechanisms added since the prior completed record. When
that slice cannot establish a verdict, return `UNKNOWN` naming the smallest
missing evidence rather than widening into a repository audit. Record
completeness comes from covering that bounded slice, not from repeating
unchanged inventories in a delta record. Every record still carries each
required property and retained product or security invariant needed to define
the minimum path and executable scope. A delta record references unchanged
sections by content hash and writes only invalidated or added entries in full.

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
- `requirements` — one entry for every `requirement_id`, with a
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
bypasses. Reconcile the recreated effect against the denied effect before
selecting either channel; authentication, journaling, or existing use of the
second channel proves that it is controlled, not that the bypassed capability
is necessary.

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

Rejection requires positive evidence of incompatibility. When persistence,
restart, topology, or production wiring bears on a recorded requirement or
evidenced actor lifecycle, never infer a candidate is ephemeral, local,
single-run, or otherwise incapable merely because that evidence is absent;
resolve that pair `UNKNOWN`. When it bears on neither, do not use its absence
to discount the candidate.

Compare against the required property, not the incumbent ownership topology.
An existing actor, service, process, or resource placement is not a concrete
incompatibility unless an authority anchor requires that placement itself.
Likewise, an alternative's missing evidence matters only when it bears on the
recorded observable result for the actual supported actors and lifecycle. Do
not reject or discount a substitute for lacking an incumbent-specific
ownership model, cross-run lifetime, production wiring, or coordination
semantic that no requirement or evidenced topology demands.
The absence of a current interface or adapter is missing wiring, not a
concrete incompatibility, unless authority requires the existing interface
itself. Compare the smallest wiring needed for the substitute against the
machinery the incumbent retains.

Reopen a pass-1 disposition whenever pass 2 reveals an additional operation,
permission, lifecycle, or effect: expand the candidate's `operations` and
`effects` first, then resolve again. The pass-1 label never overrides newly
visible capability evidence.

Pass 2 does not manufacture authority from proposal detail. It may add a
required property only when a newly visible operation or effect creates a
reachable failure of the pass-1 job, authority, or trust boundary. A work
order, design, charter, test, proof, artifact manifest, or internally coherent
implementation cannot add an actor, outcome, or required property merely by
describing the challenged mechanism.

### 4.2 Build the material scope tree

Material scope is finite: the nodes present in the changed work graph and
proposal since the prior completed record, plus each ancestor a reverse trace
reaches from them. It also includes any exact direct user decision that changes
the supported caller, limits the agent or team's operational ownership, or
explicitly removes work from scope, even when that excluded work is absent from
the changed graph. Record that authority and its required action under
`scope_avoided_or_added`; graph omission cannot erase a direct scope limit.
Nothing else outside that set is in scope. Identify each node's identity,
parent, and kind, then assign its provisional rank. Persist the full section 7
fields only for active nodes selected in section 4.3; deferred nodes retain
their ID, rank, and deferral reason.

A binding acceptance criterion in the current work order remains in material
scope for necessity analysis even when a charter calls it deferred,
non-blocking for the current phase, or scheduled later. Sequencing controls
when work runs; it does not supply authority or preserve an unsupported future
gate.

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

Run an **incumbency check** before assigning `SUPPORTED` or `RETAIN`. Derive
the actual actors and operations from the job, then remove hypothetical actors
and actors created only by the incumbent machinery. Trace the mechanism to an
authority anchor independent of the proposal; an accepted design statement
that specifies the mechanism remains `claimed_authority`, not an
`authority_anchor`. Apply missing-evidence standards symmetrically. Existing
wiring, completed proof, and production use do not break a tie with a simpler
substitute whose corresponding evidence is also missing.

Apply that check to every incumbent placed on
`minimum_design.simplest_existing_path`, not only to the three active nodes. A
genuine simpler substitute left `UNKNOWN` makes the selected-path mechanism
and verdict unresolved; deferring its comparison cannot leave the incumbent
`SELECTED`.

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
Such a descendant cannot be labeled orthogonal or deferred to preserve it from
the failed ancestor's disposition.

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

Nodes made mandatory by a fired lens or section 4.4 rule outrank discretionary
nodes. When more than three are mandatory, inspect the three highest, record
the unexamined mandatory nodes separately from ordinary deferrals, and return
`UNKNOWN` naming them; no gate may clear work that overlaps them.

When the resource-demand lens fires, its largest weakly authorized multiplier
is mandatory active scope and displaces a lower-ranked node. It cannot be
ordinarily deferred while a dependent boundary, limit, or optimization is
selected.
When excessive demand motivates a proposed limit, the mechanism multiplying
that demand is an ancestor in active scope; analyzing only the limit or its
value does not satisfy the resource-demand lens.

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

For an assurance or proof node, decompose the protected property, the subject
that must carry it, and the proof method. When the proof method's necessity
fails, trace the narrow property independently and state the minimum evidence
gate that preserves it on the supported path. Exclude excess assurance
machinery without dropping an independently anchored identity, provenance,
correspondence, integrity, or fail-closed property together with it. Follow
the protected subject through every carrier and interface on the selected path
to the observable result. Rejecting equality or reproducibility of a broader
container does not make the narrower payload-to-carrier or
carrier-to-execution correspondence inapplicable. A carrier used by the
selected route is current scope for that correspondence even when broader
construction or release work for the carrier is not.

Use **layer peeling** when a leaf mechanism fails its trace: continue upward
through the service, protocol, store, compiler, broker, or other enclosing
architecture that made the leaf look necessary. The trace ends only at a
verified authority anchor or at a finding that the enclosing architecture is
unsupported; replacing one leaf while preserving an unsupported parent is not a
minimum-design result. When a load-bearing assumption fails, also re-test each
sibling mechanism whose only reverse trace ends at that assumption. Retire,
exclude, or hold that sibling by its own evidence and section 4.2 transition
status rather than preserving adjacent machinery whose shared premise has
already failed. Re-derive each sibling from the top-level job and independent
authority anchors after removing the premise; a local requirement, test, or
design statement created for that premise cannot become a replacement
authority anchor.

When an unsupported parent contains independently useful low-level
capabilities, split those capabilities into ledger candidates. Retaining a
primitive does not retain the parent's orchestration, protocol, compatibility
layer, state machine, or proof campaign without its own authority trace.

When one challenge-authorized diagnostic or proof mechanism produces no
user-visible progress and the proposed response is another mechanism on the
same causal branch, the parent premise becomes mandatory active scope. Compare
removing that parent against the user outcome before authorizing the next
descendant. A second descendant may proceed only when positive evidence shows
the parent-removal path is incompatible with a required property. Do not let a
chain of individually narrow probes substitute for this parent counterfactual.

More generally, when a proposed mechanism compensates for a cost, limit,
failure, or complexity created by an incumbent ancestor, that ancestor is
mandatory active scope even on the first corrective attempt, subject only to
section 4.3's mandatory-node overflow rule. Run the ancestor-removal
counterfactual before selecting the compensating mechanism or retaining the
ancestor as baseline.

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

When `NARROW` removes an unsupported parent but leaves a simpler supported path,
the current proposal remains blocked. Name the exact corrected successor
campaign, its retained invariants, and whether its changed work order requires
`DELTA` or `FULL` reconciliation. Do not leave the next step as an unspecified
"rechallenge," and do not claim the corrected campaign is already cleared when
it was absent from the reviewed work graph.

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
Every supported product or security invariant needed by the selected path
appears explicitly in the final minimum design and permitted or blocked scope;
deferring its implementing inventory does not defer or remove the invariant.

Scope a `CLEAR` or `PARTIAL` permission to the smallest coherent campaign that
can produce the observable result, not automatically to one command. The
record names campaign invariants, permitted setup-only retries, terminal
conditions, and invalidation predicates. Reversible retries remain inside the
same clearance only while subject bytes, authority, trust boundaries,
acceptance criteria, and persistent or remote effects are unchanged. Use a
one-shot permission when repetition itself adds authority, creates an
irreversible effect, changes the evidence subject, or can hide the failed
state.

A record may specify a conditional revisit predicate, tied to a concrete
future event and proposed response. It must not require another challenge
merely because the permitted action ran, completed, or failed. The predicate
forms a trigger only when its named evidence occurs and diagnosis selects the
named material response.

## 7. Record

Persist this record in the work order or durable baton. A `FULL` record writes
the complete shape below. A `DELTA` record starts with
`record_mode: DELTA`, `inherits_record: {path, sha256}`, and
`invalidated_ids: []`; it writes changed entries in full and records inherited
unchanged sections or entries under `inherited_ids`. A top-level field name is
its section ID. Repeated entries use their existing `requirement_id`,
`candidate_id`, or `node_id`; an unkeyed repeated section is inherited only as
one whole section by field name and hash, or rewritten in full. Braces mark
nested keys and brackets mark repeated records:

```text
record_mode: FULL | DELTA
inherits_record: {path, sha256} | null
invalidated_ids: []
inherited_ids: [{id, sha256}]
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
campaign: {invariants, permitted_retries, terminal_conditions, invalidation_predicates}
revisit_predicates: [{event, proposed_response, trigger_kind}]
```

## 8. Complete when

Before returning, audit the draft record against every applicable item below
and repair omissions or contradictions. When missing evidence prevents an item
from closing, record `UNKNOWN` and the resulting gate instead of silently
omitting the requirement, candidate, node, or boundary.

- The record names the exact evidence-packet revision and, after pass 2, the
  exact work-order revision and work-graph cutoff.
- A `DELTA` record names and hash-verifies its inherited record, writes every
  invalidated or added entry in full, and identifies every unchanged inherited
  section or entry by stable ID and content hash. Use `FULL` instead when that
  inheritance would be ambiguous.
- Every `authority.direct_user_quotes` entry byte-matches its named source
  record, and interpretation sits outside that field.
- Every distinct material architecture-shaped premise from pass 1 carries a
  `quarantine` disposition with an independent trace or exclusion, or the
  record states that none was visible.
- Every ledger candidate carries recorded `operations` and `effects`, and every
  recorded candidate/requirement pair carries exactly one pass-2 resolution whose
  `REJECTED` names a concrete incompatibility and whose `UNKNOWN` names
  decisive missing evidence.
- Every candidate's recorded operations and effects are checked against every
  required property they could bear on, rather than being confined to one
  property, namespace, abstraction level, or headline role.
- Every deny-by-default, allowlist, or sandbox source records both the denied
  set and each explicitly allowed operation as separate ledger candidates.
- Every active node's `alternatives` contains its incumbent and every genuine
  substitute exactly once, excludes merely complementary candidates, and its
  three statuses agree with the incumbent support rule and with each other.
- Every incumbent on the minimum-design path has comparison closure; a simpler
  substitute left `UNKNOWN` is reflected as unresolved in the verdict even
  when its comparison node is deferred.
- Every `SUPPORTED` or `RETAIN` mechanism names an authority anchor independent
  of the proposed or accepted mechanism statement, and no node remains
  `SUPPORTED` while a genuine substitute is `UNKNOWN` under evidence missing
  equally for the incumbent.
- Every alternative's `REJECTED` incompatibility or `UNKNOWN` evidence need
  traces to a recorded requirement, observable result, and evidenced actor
  lifecycle; no incumbent-specific topology or property is used as an
  unstated requirement.
- Every property added in pass 2 traces a newly visible operation or effect to
  the pass-1 job, authority, or trust boundary; proposal and proof artifacts do
  not supply that authority.
- Every pass-1 `REJECTED` or `NOT_RELEVANT` disposition contradicted by a
  pass-2 operation, permission, lifecycle, or effect is reopened and resolved
  from the expanded candidate.
- Every separately granted channel whose effects recreate a denied capability
  is reconciled as part of that same boundary before either channel is
  selected.
- Every fired boundary-composition lens resolves each material operation
  family separately under
  [`boundary-composition.md`](references/boundary-composition.md); one
  supported family does not retain unrelated coordination, storage,
  compatibility, or proof families.
- An authoritative payload already present at its consumer remains a candidate
  independent of the machinery that produced or transported it; no upstream
  provider or transfer is required unless the selected journey independently
  requires producing or refreshing that payload.
- Every retained multi-writer coordination family names either two evidenced
  writer lifecycles with reachable overlap or an authority anchor for the
  second writer and its triggering event; otherwise it is separated from any
  independently required single-writer atomicity or crash-recovery property.
- When resource demand is material, the largest weakly authorized multiplier
  is active; no dependent boundary uses an implementation maximum or appears
  in the minimum or permitted scope while that multiplier or supported demand
  remains unresolved. If mandatory-node overflow prevents its inspection, the
  verdict is `UNKNOWN` and overlapping work is blocked.
- A parameter that bounds an incumbent mechanism cannot be selected, tuned, or
  ordered as the preferred correction while that incumbent's comparison with
  a genuine substitute remains unresolved; measurement may continue without
  authorizing the parameter change.
- When a proposed mechanism compensates for an incumbent ancestor's cost,
  limit, failure, or complexity, the ancestor is active and its removal
  counterfactual is resolved before the compensating mechanism is selected,
  or mandatory-node overflow records it unexamined and forces `UNKNOWN`.
- Each of the three active nodes carries an actual-caller list, a forward
  trace, a reverse trace, and a removal counterfactual; every other material
  node is deferred with its rank and reason.
- Every fired lens has a recorded `lens_findings` result.
- Every lens-assigned `FAILED` or `UNKNOWN` identifies its material `node_id`
  and is reflected in the verdict even when that node is deferred.
- Every failed assurance method is separated from its protected property; the
  final minimum design and scopes retain each independently anchored property
  while excluding only the unsupported proof machinery, and trace the
  protected subject through every selected carrier and interface to the
  observable result.
- A `FULL` pass-2 record restates every retained pass-1 required property and
  its selected or permitted scope; implicit inheritance or a lens finding does
  not substitute for that reconciliation.
- Every sibling whose only reverse trace ended at a failed premise records
  either a fresh top-level authority trace or the applicable `RETIRE`,
  `EXCLUDE_FROM_TARGET`, or `HOLD_PENDING_EVIDENCE` disposition; requirements,
  tests, and design statements created for the failed premise do not serve as
  that authority.
- Every descendant whose only trace ends at a failed or excluded ancestor
  receives the corresponding transition disposition rather than an
  orthogonal or deferred label.
- One verdict, its derived `gate_status`, and any `PARTIAL` scopes are
  persisted and consistent with the recorded statuses.
- Every executable permission names campaign invariants, retry and terminal
  behavior, and the events that invalidate the clearance. Every revisit
  predicate is conditional on named evidence and a material proposed response;
  completion, failure, or consumption alone never requires another challenge.
