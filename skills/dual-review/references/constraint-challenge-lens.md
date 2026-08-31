# Independent constraint challenge

Use this pass for every systemic or critical design before normal design review,
and during implementation when one of the triggers below fires. It is a
focused challenge to the plan's premises, not a third full code reviewer.

The challenger must run in a fresh, read-only context that did not author the
plan. It distrusts both the proposed architecture and the rationale supplied by
the author. It may read source, history, policy, platform documentation,
accepted user decisions, task records, tests, and recent implementation
evidence. It must not build, test, mutate, or propose a generalized replacement
whose callers do not exist.

## Challenge-only invocation

This reference is an independently invokable mode of `dual-review`. A trigger
during implementation runs this mode only; it does not start the normal
two-family diff review. Launch one fresh read-only agent, keep it for both
passes below, persist its record in the work order or baton, and return to the
governing workflow with the verdict.

For pass 1, give it:

- the current work-order revision identifier, without the work order body;
- an architecture-neutral extraction of product outcomes, observable
  acceptance criteria, non-negotiable product boundaries, and rollback;
- direct user decisions as exact quotes, their available context, and the
  supported user journey; and
- relevant external policy, platform, compatibility, and observed-failure
  evidence.

For pass 2, add:

- the full current work order and Definition of Done;
- the proposed architecture plus material tasks, components, tests, and proof
  added since the prior accepted record; and
- the prior challenge record, if one exists.

A record is current only when it names the exact work-order revision and work
graph it reviewed, no mandatory event trigger occurred afterward, and its
durable active-time clock is below 480 minutes. Reuse one current accepted
record when normal design review starts; do not run the challenger twice for
the same revision and work graph.

An accepted record has verdict `CONTINUE`. A blocking verdict becomes eligible
for acceptance only after its required action changes the work order and a new
challenge on that revision returns `CONTINUE`.

The whole challenge has a 20-minute budget. Inspect the three highest-leverage
assumptions and material mechanisms added since the prior accepted record. If
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
then compose the smallest path that satisfies the required properties. Do not
limit the comparison to complete end-to-end paths already assembled by the
proposal. For each composition edge, cite an existing supported interface and
trace authority, data flow, lifecycle, and failure semantics across it. If the
packet cannot prove that the primitives compose without a new boundary or
weakened control, mark the path `UNKNOWN`. If the bounded packet cannot
establish the relevant simpler-primitive set, mark the incumbent mechanism
`UNKNOWN`, not unsupported. A non-security `UNKNOWN` alone does not justify
removing or reframing a working incumbent; it does block new machinery whose
necessity depends on that unknown.

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
boundary is not the minimum design. For a working incumbent, or when comparison
or property evidence is incomplete, mark the mechanism `UNKNOWN` under the
incumbent rule above rather than inferring removal.

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
dependent machinery, claimed authority or evidence, provisional support
status, and the scope retired if the node is removed. Apply the
scope-multiplication factors below plus provenance weakness to rank the
provisional nodes. Select the three highest-leverage nodes for tracing; those
become the provisional top load-bearing assumptions. Record every other
material node in `deferred_scope_nodes` with its rank and deferral reason;
record missing evidence only when evidence is the reason.

Then trace in both directions:

- **Forward:** for each of the three highest-leverage assumptions, identify the
  components, implementation, tests, proof, and operations it creates.
- **Reverse:** for every material component or work item under the three
  selected nodes, identify the verified user need, threat, external obligation,
  or current compatibility promise that requires it.

Use those traces to confirm, clear, or overturn each provisional status. When
a trace exposes a higher unsupported parent, replace the lower node and rerank
within the three-node set; do not expand into a full-tree trace.

Do not mark an architecture node supported merely because it currently
implements a required property. Record the property separately, then either
prove that the mechanism itself is required or mark the node `UNKNOWN` while
testing simpler primitives.

Use **layer peeling** when a leaf mechanism fails its trace. Continue upward
through the service, protocol, store, compiler, broker, or other enclosing
architecture that made the leaf appear necessary. The trace ends only at a
verified user outcome, threat, external obligation, current compatibility
promise, or a finding that the enclosing architecture is unsupported. Replacing
one leaf while preserving an unsupported parent is not a minimum-design result.

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
- after eight hours of active implementation since the last accepted
  challenge. Known blocked or idle time does not count. If elapsed active time
  cannot be reconstructed after resumption, treat the challenge as due.

The event triggers run immediately; the eight-hour trigger is a backstop, not a
reason to postpone an earlier challenge.

## Output and gate

Persist a short challenge record in the work order or durable baton:

```text
reviewed_at:
work_order_revision:
work_graph_cutoff:
evidence_sources:
pass1_architecture_exposure:
direct_user_quotes:
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
top_load_bearing_assumptions:
deferred_scope_nodes:
counterfactuals:
untraced_work:
enclosing_architecture_trace:
security_boundary:
trust_domain_map:
trust_transfer_tests:
scope_avoided_or_added:
verdict: CONTINUE | NARROW | REFRAME | ESCALATE | UNKNOWN
active_time:
  accumulated_minutes:
  active_interval_started_at:
  paused_at:
  pause_reason:
next_review_due_at_active_minutes: 480
```

Reconcile this clock at task start, phase boundaries, every scheduled re-brief,
and when work becomes blocked, idle, or active:

1. If an active interval is open, add its elapsed minutes to
   `accumulated_minutes`, then close it.
2. Open a new interval only while implementation is actively progressing.
   Record a pause timestamp and reason while blocked or idle.
3. After an accepted challenge, reset accumulated time to zero and open a new
   interval only if implementation resumes.
4. Treat a missing, overlapping, future-dated, or otherwise inconsistent clock
   as due immediately.

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

The challenger is complete only when every distinct material
architecture-shaped premise in pass 1 has a recorded disposition and
independent trace or exclusion, or the record states that none was visible;
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
explicit; and one verdict is persisted.
`NARROW`, `REFRAME`, `ESCALATE`, and security-relevant `UNKNOWN` block
implementation. A non-security `UNKNOWN` blocks only new machinery whose
necessity depends on that unknown; unrelated work and a working incumbent may
continue.
