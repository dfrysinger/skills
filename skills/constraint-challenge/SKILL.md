---
name: constraint-challenge
description: Challenge the load-bearing assumptions in systemic or critical work before implementation and while it evolves. Use when that work changes its design, charter, Definition of Done, trust boundary, constraint, or scope; before it adds a subsystem, service, protocol, store, broker, compiler, fork, repository, language, or platform lane; when its adapters preserve inherited behavior, proof machinery grows, or failures move between internal boundaries without user-visible progress; when completed work is used to preserve its architecture; or when the governing run lifecycle reports that its scheduled challenge is due.
---

# constraint-challenge

Use this pass for every systemic or critical design before normal design review,
and during implementation when one of the triggers below fires. It is a
focused challenge to the plan's premises, not a third full code reviewer.

The challenger must run in a fresh, read-only context that did not author the
plan. It distrusts both the proposed architecture and the rationale supplied by
the author. Pass 1 may read only its closed evidence packet. Pass 2 may also
read source, history, policy, platform documentation, accepted user decisions,
task records, tests, and recent implementation evidence. It must not build,
test, mutate, or propose a generalized replacement whose callers do not exist.

## Invocation

This skill is independent from implementation and diff review. A trigger runs
only this challenge; it does not start `dual-review`'s normal two-family review.
Prefer one fresh read-only agent for both passes below. When that agent is no
longer available after document authoring, compaction, or a later trigger,
launch a fresh read-only agent and give it the sealed pass-1 record to reconcile
before pass 2. Persist the record in the work order or baton and return to the
governing workflow with the verdict.

Each invocation normally runs both passes back to back: first expose only the
sealed evidence packet, persist pass 1, then reveal the proposal and current
work graph for pass 2. The trigger decides when the complete challenge runs;
quarantine is an input boundary, not a requirement to pause authoring between
passes. Reuse a pass-1 record only when its evidence-packet revision is still
exactly current.

For pass 1, give it:

- the pre-proposal evidence-packet revision identifier;
- an architecture-neutral extraction of product outcomes, observable
  acceptance criteria, non-negotiable product boundaries, and rollback;
- direct user decisions as exact quotes, their available context, and the
  supported user journey; and
- relevant external policy, platform, compatibility, and observed-failure
  evidence.

For pass 2, add:

- the full current work order and Definition of Done;
- the proposed architecture plus material tasks, components, tests, and proof
  added since the prior completed record; and
- the prior challenge record, if one exists.

A pass-1 record is current only for the exact evidence-packet revision it
reviewed. A final record is current only when it also names the exact work-order
revision and work graph it reviewed and no mandatory event trigger or
caller-owned scheduled trigger occurred afterward. Reuse one current record
when its gate permits the exact pending action; do not run the challenger twice
for the same revisions, work graph, and action.

Derive `gate_status` from the verdict:

- `CONTINUE` is `CLEAR`.
- `NARROW`, `REFRAME`, `ESCALATE`, and security-relevant `UNKNOWN` are
  `BLOCKED`.
- A non-security `UNKNOWN` is `PARTIAL`. It must name `blocked_scope` and
  `permitted_scope`, and permits an action only when that action is wholly
  inside the permitted scope and outside the blocked scope.

A `BLOCKED` or `PARTIAL` record gains no broader permission until its required
action or missing evidence changes the work order or evidence packet and a new
challenge clears that scope.

The whole challenge has a 20-minute budget. Inspect the three highest-leverage
assumptions and material mechanisms added since the prior completed record. If
that slice cannot establish a verdict, return `UNKNOWN` with the smallest
missing evidence; do not expand into a full code or repository audit.

## Two-pass method

### 1. Derive the minimum design without seeing the proposed architecture

Give the challenger the supported user journey, direct user decisions, external
policy, platform facts, compatibility promises, and observed failures, but
withhold the proposed component graph and implementation plan.

When an accepted design document is the product source of truth, extract its
objective, supported caller, observable outcomes, non-negotiable product
boundaries, and rollback promise. Keep architecture-shaped non-goals,
component names, protocol choices, and implementation-specific proof plans out
of pass 1. A source does not become architecture-neutral merely because it is
accepted.

The challenger owns the last-mile quarantine. Scan every pass-1 input,
including exact user quotes, for named components, protocols, services,
stores, compilers, brokers, execution paths, and implementation-specific
proof, plus any other mechanism or constraint that presupposes a design.
Group repetition, then record every distinct material premise and its
disposition in `pass1_architecture_exposure`. Exclude it from the job and
minimum design until independent evidence traces it to a product outcome or
security boundary. It may remain an alternative in the simplest-path
comparison after evidence establishes that the path exists and supports the
same outcome; that does not make it a requirement. An exact user quote may
make a mechanism an important tactical decision; it does not turn the
mechanism into a top-level need.

Never give the reviewer an agent's paraphrase in place of the user's words.
Quote the relevant user statement exactly and identify enough surrounding
context to distinguish a durable direction from a quick approval. If the
original words are unavailable, label the decision `UNVERIFIED PARAPHRASE` and
do not treat it as binding.

Every `direct_user_quotes` entry must be an object containing `quote`,
`source`, `event_id`, and `exact_match: true`. `source` is a supplied durable
decision record or baton quote ledger, `event_id` identifies one record in it,
and `quote` reproduces that record's complete value byte for byte. Never
reconstruct, improve, combine, or invent a quote from text outside that record.
Copy the quote and identifier together from the source record rather than
retyping either field.
Put interpretations only in
`inferred_product_judgment`. If an exact source match cannot be found, omit the
entry from
`direct_user_quotes` and record the missing authority as `UNVERIFIED
PARAPHRASE`. Include only direct quotations that the challenge actually uses
as authority; identify incidental,
superseded, or formatting-damaged decisions by source record rather than
copying them into this field. A statement in a genuine top-level conflict is
not superseded by convenience or recency; quote every side of the conflict.

Classify each user statement by authority:

- **Top-level user need or product direction:** the job the product must do,
  the people it serves, the outcome it should create, and the user's explicit
  risk or business priorities. Treat this as authoritative within its stated
  scope.
- **Scoped product decision:** an explicit choice among understood product
  outcomes. Treat it as binding only for the named scope and while it remains
  consistent with top-level direction.
- **Tactical approval or implementation suggestion:** low-level architecture,
  mechanisms, defaults, estimates, or acknowledgements such as "sure" and
  "sounds good." Treat this as evidence of permission to proceed at that
  moment, not as a permanent requirement. Challenge it like an agent-authored
  assumption.
- **Ambiguous statement:** classify as unknown rather than upgrading it through
  interpretation.

The user's limited time and incomplete code context are part of the review
model. A low-level approval does not prove that the user saw hidden cost,
security consequences, duplicated machinery, or a simpler existing path.

Start the product trace with the end user's **job to be done**:

- who the end user is;
- what situation starts the journey;
- what progress or outcome they are trying to achieve;
- what currently makes that difficult, risky, slow, or confusing; and
- what observable product result means the job is done.

The challenger may infer a likely job or preference from the product's broader
purpose when direct evidence is incomplete. Label it `INFERRED`, cite the
product evidence, state confidence, and never present it as the user's words.
Use the inference to test whether the plan makes product sense, not to silently
override an explicit top-level direction.

Top-level goals can conflict. When they do, quote each conflicting statement
exactly, explain the concrete product or risk tradeoff, identify which end-user
job each serves, and return `ESCALATE` with the smallest decision the user must
make. Do not resolve a genuine authority conflict by choosing the most recent,
most convenient, or most implementation-friendly quote.

For each claimed product goal, independently record:

- the person or supported caller with the need;
- the source that establishes the need;
- the observable result that satisfies it;
- the actors and paths the goal actually covers; and
- what user-visible result fails if the goal is removed.

For each claimed security rule, independently trace:

- the protected asset;
- the untrusted actor;
- the harmful capability and reachable path;
- the actual enforcement point;
- the code, policy, platform behavior, or refusal evidence that proves it;
- the actors and operations within its scope;
- a narrower control that stops the same threat, when one exists; and
- the measurable residual risk after narrowing.

Treat this as a **trust-domain map**, not a list of reusable controls. Whenever
a proposal, inherited rule, or simpler path carries a control across callers,
actors, or operations, run a fresh **trust transfer test**. Record the original
actor, operation, reachable threat, authority owner, enforcement point, and
control; the candidate actor and operation; whether the same threat remains
reachable; and whether the control should be retained, narrowed, or removed.
Similar side effects do not make trust domains equivalent. Do not inherit a
restriction from an untrusted actor into a trusted actor's operation whose
authority is independently established merely because both can eventually
affect the same asset.

An author's label such as `product decision`, `security requirement`, or
`existing architecture` is a claim, not proof. Historical implementation is
provenance, not authority. A tactical user approval is also not proof of a
top-level need.

Call a verified user need, reachable risk, external obligation, measured
demand, or current compatibility promise an **authority anchor**.

Separate an inherited constraint's observed existence from its authority to
shape future design. Evidence that a rule, limit, default, or mechanism is
currently enforced proves the present state only. Its necessity is a separate
claim that requires a trace to an authority anchor. When the bounded evidence
is complete enough to show that no such trace exists, mark the necessity claim
`FAILED`. Use `UNKNOWN` only when a specific unavailable piece of evidence
could decide the claim. Preserving an incumbent temporarily while evidence is
missing is an operational precaution, not authority to add work that
accommodates it.

From that evidence, derive the smallest design that satisfies the verified user
journey and security boundary. Name the simplest existing supported path found
anywhere in the bounded evidence, not merely the path closest to the current
proposal. Compare each evidenced path that could satisfy the same verified
user outcome and non-negotiable boundaries using the scope-multiplication
factors below. Choose the smallest or state the concrete incompatibility that
rules it out. If the bounded packet cannot establish the relevant path set,
mark it `UNKNOWN`; do not expand the audit or silently convert unsupported
claims into requirements.

Keep **properties** separate from **mechanisms**. Durability, atomicity,
isolation, reviewability, and bounded authority may be required properties;
the current service, protocol, store, compiler, broker, or runtime is only one
candidate mechanism. A mechanism is supported only when external compatibility
or policy requires that mechanism, or concrete evidence rules out simpler
existing primitives that provide the same properties. An accepted design or
working implementation proves availability, not necessity.

Inventory platform and product primitives already present in the evidence,
then compose the smallest path that satisfies the required properties. Search
by required property across every layer already available to the caller and
runtime. Do not restrict the search to the proposal's namespace, abstraction
level, or already assembled end-to-end paths. For each composition edge, cite
an existing supported interface and trace authority, data flow, lifecycle, and
failure semantics across it. If the packet cannot prove that the primitives
compose without a new boundary or weakened control, mark the path `UNKNOWN`.
If the bounded packet cannot establish the relevant simpler-primitive set,
set the incumbent mechanism's `necessity_status` to `UNKNOWN`, not `FAILED`. A
non-security unknown necessity alone does not justify removing or reframing a
working incumbent; it does block new machinery whose necessity depends on
that unknown.

Run a **native primitive mirror check** for every proposed custom API, service,
store, broker, or protocol under the selected scope nodes. Defer other material
custom boundaries through `deferred_scope_nodes`. List the operations and
semantics each selected boundary exposes, find any existing platform or product
primitive in the evidence that provides the same abstraction, and identify the
verified property the custom boundary adds. Split a heterogeneous boundary
into independently authorized operation families or responsibilities before
comparing it; one valid responsibility cannot justify unrelated operations
that happen to share its process or service. Account for every operation
family in `native_primitive_mirror`.

When recommending that an operation family leave a shared boundary, run a
trust transfer test for its post-split authority. The replacement must preserve
or narrow credential and capability distribution; a simpler component graph
does not justify granting authority to more callers.
If no additional property is established, a proposed but unbuilt custom
boundary is not the minimum design. A proposed or expanded mechanism bears the
burden of proof: existing dependencies establish that it can be built, not
that it is needed. Mark its necessity `FAILED` when no independent required
property supports it, and do not use an `UNKNOWN` inherited constraint as
authority for adding it. For a working incumbent whose comparison or property
evidence is genuinely unavailable, keep its `transition_disposition` as
`HOLD_PENDING_EVIDENCE`
rather than inferring safe removal. A node whose `necessity_status` is
`FAILED` cannot authorize a new or expanded mechanism regardless of its
transition disposition. For a control on a security, integrity, or trust
boundary, use `FAILED` only when the trust-domain map shows that the protected
risk is unreachable or that another supported control preserves the required
property through the transition; otherwise use `UNKNOWN` and leave the control
in place.

When concurrency, fencing, locking, coordination, or multi-writer machinery is
claimed, name the actual actors or executions, the reachable overlap, and the
failure caused by their interleaving. Retries, resumed or restarted attempts,
at-least-once delivery, and stale in-flight predecessors are candidate actors,
not proof of overlap. Cite scheduler and lifecycle evidence that two executions
can remain active against the same state. A removal counterfactual must state
the outcome under every evidenced duplicate-execution condition. Platform-
serialized execution does not justify multi-writer machinery. Cancellation
rules out overlap only when evidence shows termination is synchronous and
effective before another writer starts. A transactional stale-completion
boundary may protect one named effect while overlap remains reachable; record
that narrower protection in `transactional_effects` for selected scope nodes
and make the removal counterfactual cover every other read, write, external
call, and duplicate side effect under those nodes. Defer other material
transactional boundaries through `deferred_scope_nodes`. Hypothetical future
callers do not justify present concurrency machinery.

Use `writer_lifecycle` as the single record of each logical writer or execution:
how it is created, when it can remain active, how retry or resume starts, and
how termination, cancellation, or lease expiry ends its authority. Cite the
evidence that permits or excludes overlap. Entries in `concurrency_actors`
reference these lifecycle records rather than restating them.

### 2. Compare the minimum design with the actual work

Now give the same challenger the proposed design, current charter and baton,
recent task assignments and handoffs, changed repositories and files, new
tests and proof obligations, and material implementation added since the prior
challenge.

First build a **scope tree** from user outcome to architectural path to
subsystem to leaf mechanism. For each material node record its parent,
`node_kind` (`outcome`, `architecture_path`, `subsystem`, `leaf_mechanism`, or
`parameter`), dependent machinery, claimed authority or evidence,
`existence_status` (`PRESENT`, `PROPOSED`, `ABSENT`, or `UNKNOWN`),
`necessity_status` (`SUPPORTED`, `FAILED`, or `UNKNOWN`),
`transition_disposition` (`RETAIN`, `RETIRE`, `HOLD_PENDING_EVIDENCE`, or
`EXCLUDE_FROM_TARGET`), and the scope removed from the target design if the
node is excluded. Apply the
scope-multiplication factors below plus provenance weakness to rank the
provisional nodes. Select the three highest-leverage nodes for tracing; those
become the provisional top load-bearing assumptions. Record every other
material node in `deferred_scope_nodes` with its rank and deferral reason;
record missing evidence only when evidence is the reason.

Assign transition dispositions consistently:

- `RETAIN` includes a node with supported necessity in the target design when
  its existence is known, whether it already exists or must be created.
- `RETIRE` applies to a present node with failed necessity only after a safe
  transition is established.
- `HOLD_PENDING_EVIDENCE` applies only to a node that is present, or may be
  present, when its existence, necessity, or removal safety remains unresolved.
  It preserves current operation but authorizes no expansion.
- `EXCLUDE_FROM_TARGET` applies to a proposed or absent node whose necessity is
  not supported.

Then trace in both directions:

- **Forward:** for each of the three highest-leverage assumptions, identify the
  components, implementation, tests, proof, and operations it creates.
- **Reverse:** for every material component or work item under the three
  selected nodes, identify the authority anchor that requires it.

Use those traces to confirm, clear, or overturn each provisional
`necessity_status`. When a trace exposes a higher unsupported parent, replace
the lower node and rerank
within the three-node set; do not expand into a full-tree trace.

Do not mark an architecture node supported merely because it currently
implements a required property. Record the property separately, then either
prove that the mechanism itself is required or set its `necessity_status` to
`UNKNOWN` while testing simpler primitives. Record existence and transition
separately.

Use **layer peeling** when a leaf mechanism fails its trace. Continue upward
through the service, protocol, store, compiler, broker, or other enclosing
architecture that made the leaf appear necessary. The trace ends only at a
verified authority anchor or a finding that the enclosing architecture is
unsupported. Replacing one leaf while preserving an unsupported parent is not
a minimum-design result.

Removing or reframing a scope-tree node excludes from the target design every
descendant whose only supported caller or property came through that node. A
descendant survives only when it has an independently evidenced caller or
required property outside the removed path. Local correctness, completed
implementation, or useful tests do not create that independent need. Existing
production behavior remains `HOLD_PENDING_EVIDENCE` until a safe transition is
established; excluding it as design authority is not permission to remove it
unsafely. A narrower verdict may not retain in planned work machinery whose
only reverse trace still ends at a failed parent. Under a `PARTIAL` gate,
`permitted_scope` may contain only actions independent of the blocked
`UNKNOWN` nodes.

Begin pass 2 by reconciling the persisted pass-1 record. Every pass-1 primitive,
architecture exposure, required property, and selected assumption must appear
in pass 2 with an explicit retained, rejected, superseded, or still-unknown
disposition. A promising simpler primitive found in pass 1 cannot disappear
merely because the proposal supplies a more detailed incumbent mechanism.

Run a **counterfactual** for each top-ranked assumption. State the assumption
being removed now, enumerate the dependent machinery that disappears with it,
name the simplest evidenced supported path after removal, and decide whether
that path reaches the user outcome. If the proposal remains necessary, name
the specific evidence-backed incompatibility that defeats the simpler path. A
future contingency such as "if validation fails, stop" is a fallback plan, not
a counterfactual. If the packet cannot establish either result, return
`UNKNOWN` rather than inheriting the proposal.

Reverse-trace work even when no design sentence names its premise. Repeated
implementation behavior, acceptance machinery, adapters, fixtures, and proof
requirements can create an effective unwritten constraint. Flag any
substantial work whose reverse trace ends at an implementation default,
historical mechanism, sunk work, unsupported assertion, or missing source.

## Challenge the load-bearing assumptions first

Rank assumptions by how much they multiply:

- components, tasks, repositories, or languages;
- credentials, trusted actors, or enforcement boundaries;
- platforms and release artifacts;
- stored state, public contracts, migrations, or irreversible decisions;
- builds, live proof, validation matrices, and operating cost; and
- maintenance that remains after the current feature ships.

Increase priority when provenance is weak or the assumption is several
reasoning steps removed from the user-visible outcome. Investigate only the
three assumptions selected and reranked through the scope tree so the pass
does not become a broad audit of every default or numeric value.

## Mandatory triggers

Run the challenge:

- before normal `dual-review` approval of every systemic or critical design;
- after any design, charter, Definition-of-Done, trust-boundary, or constraint
  change;
- before adding a subsystem, service, protocol, store, broker, compiler, fork,
  native binary, repository, implementation language, or platform lane;
- when a compatibility layer or adapter exists mainly to preserve inherited
  behavior;
- when proof or validation machinery grows without a corresponding
  user-visible capability;
- when repeated fixes move a failure between internal boundaries without
  user-visible progress;
- when preserving completed work becomes an argument for preserving the
  architecture; and
- when the governing run lifecycle reports that its scheduled challenge is
  due.

The event triggers run immediately; a caller-owned schedule is a backstop, not
a reason to postpone an earlier challenge. This skill does not own or maintain
that schedule.

## Output and gate

Persist a short challenge record in the work order or durable baton:

```text
reviewed_at:
evidence_packet_revision:
work_order_revision:
work_graph_cutoff:
evidence_sources:
pass1_architecture_exposure:
direct_user_quotes:
  - quote:
    source:
    event_id:
    exact_match: true
user_statement_classification:
job_to_be_done:
inferred_product_judgment:
top_level_goal_conflicts:
verified_user_outcome:
required_properties:
minimum_design:
simplest_existing_path:
primitive_inventory:
native_primitive_mirror:
composition_edges:
concurrency_actors:
writer_lifecycle:
transactional_effects:
scope_tree:
  - node:
    parent:
    node_kind: outcome | architecture_path | subsystem | leaf_mechanism | parameter
    existence_status: PRESENT | PROPOSED | ABSENT | UNKNOWN
    necessity_status: SUPPORTED | FAILED | UNKNOWN
    transition_disposition: RETAIN | RETIRE | HOLD_PENDING_EVIDENCE | EXCLUDE_FROM_TARGET
    dependent_machinery:
    claimed_authority:
    scope_removed_if_excluded:
top_load_bearing_assumptions:
deferred_scope_nodes:
counterfactuals:
untraced_work:
enclosing_architecture_trace:
security_boundary:
trust_domain_map:
trust_transfer_tests:
scope_avoided_or_added:
pass2_dispositions:
verdict: CONTINUE | NARROW | REFRAME | ESCALATE | UNKNOWN
gate_status: CLEAR | PARTIAL | BLOCKED
blocked_scope:
permitted_scope:
```

Verdicts mean:

- `CONTINUE`: the current design is the minimum justified design.
- `NARROW`: remove or reduce identified machinery, update the work order, and
  rerun this comparison before implementation continues.
- `REFRAME`: a load-bearing premise failed; stop implementation and return to
  `design-doc`.
- `ESCALATE`: verified user, policy, or platform authorities conflict and the
  implementing agent cannot choose between them. Quote conflicting user goals
  exactly and present the smallest product decision required.
- `UNKNOWN`: evidence for a load-bearing premise is unavailable. Treat a
  product or implementation premise as nonbinding. For a security boundary,
  fail closed and obtain evidence before continuing.

Derive the verdict from the highest failed or unresolved
`necessity_status` in the scope tree:

- A node with failed necessity permits `NARROW` only when its parent path
  remains independently supported, excluding it does not change which path
  reaches the user outcome, and the narrowed target design excludes every
  descendant that depended on it.
- Any other failed necessity, including a failed outcome or a failure that
  changes the selected architectural path, requires `REFRAME` around the
  nearest supported ancestor or verified user need.
- A conflict between verified authorities requires `ESCALATE`.
- With no failed necessity, an unresolved load-bearing necessity requires
  `UNKNOWN`.
- Use `CONTINUE` only when every selected node needed by the current action is
  necessary and supported.

Here, the architectural path is the end-to-end route from the user's trigger
to the observable outcome and required trust properties, not every internal
branch in the current work order. Removing a subsystem, many dependent tasks,
or substantial completed work can still be `NARROW` when that end-to-end route
remains the same. Use `REFRAME` only when the supported result requires a
different end-to-end route or a different user outcome.

The recorded assumption statuses, scope-tree dispositions, verdict,
`gate_status`, and permitted scope must agree. Do not choose a softer verdict
to preserve completed work.

The challenger is complete only when every distinct material
architecture-shaped premise in pass 1 has a recorded disposition and
independent trace or exclusion, or the record states that none was visible;
the record names the exact evidence-packet revision and, after pass 2, the exact
work-order revision;
every `direct_user_quotes` entry byte-matches its named source and every
interpretation is kept out of that field;
every pass-1 primitive, architecture exposure, required property, and selected
assumption has an explicit pass-2 disposition;
each required property is separated from its candidate mechanism; the
primitive inventory covers the bounded evidence or records `UNKNOWN`; every
custom boundary under the selected nodes has a native-primitive mirror
comparison or records `UNKNOWN`;
every independently authorized operation family under each selected custom
boundary is accounted for in that comparison; every family recommended out of
a shared boundary has a trust transfer test proving that credential and
capability distribution is preserved or narrowed;
every selected composition edge has an interface, authority, data-flow,
lifecycle, and failure-semantics trace; every retained concurrency control
names the actual overlapping actors or executions, references complete
`writer_lifecycle` evidence that permits overlap, and records the
duplicate-execution outcome; when scheduler or lifecycle evidence is
unavailable, `writer_lifecycle` records `UNKNOWN` and any existing integrity
control remains in place pending evidence; every transactional
stale-completion boundary under the selected nodes records its protected effect
in `transactional_effects`, and the corresponding removal counterfactual covers
all unprotected reads, writes, external calls, and duplicate side effects
under those nodes;
the scope tree produces the three top-ranked assumptions; every top-ranked
assumption has an independent trace and a removal counterfactual rather than a
failure contingency; every material new mechanism in the bounded slice and
the enclosing architecture reached by a failed trace have a reverse trace;
every material scope node outside the three-node slice is recorded as deferred
with its rank and deferral reason;
the bounded packet's equivalent path set is considered and the simplest is
either selected or rejected by concrete evidence, or the record returns
`UNKNOWN` because that set cannot be established within budget; every security
control is scoped to its trust domain and every cross-actor or cross-operation
transfer has a recorded trust transfer test; the minimum-design comparison is
explicit; one verdict and its derived `gate_status` are persisted; and a
`PARTIAL` gate names non-overlapping `blocked_scope` and `permitted_scope`.
The verdict matches the highest failed or unresolved `necessity_status`; each
selected node has a consistent `existence_status`, `necessity_status`, and
`transition_disposition`; and no permitted scope contains machinery whose only
reverse trace ends at an ancestor with failed necessity, has been excluded
from the target design, or depends on a blocked unknown necessity.
`NARROW`, `REFRAME`, `ESCALATE`, and security-relevant `UNKNOWN` block
implementation. A non-security `UNKNOWN` blocks only new machinery whose
necessity depends on that unknown; unrelated work and a working incumbent may
continue when the record's `PARTIAL` gate names them in `permitted_scope`.
