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

Give it:

- the current work-order revision and Definition of Done;
- direct user decisions as exact quotes, their available context, and the
  supported user journey;
- relevant external policy, platform, compatibility, and observed-failure
  evidence;
- the prior challenge record, if one exists; and
- for pass 2 only, the proposed architecture plus material tasks, components,
  tests, and proof added since the prior accepted record.

A record is current only when it names the exact work-order revision and work
graph it reviewed, no mandatory event trigger occurred afterward, and its
durable active-time clock is below 480 minutes. Reuse one current accepted
record when normal design review starts; do not run the challenger twice for
the same revision and work graph.

The whole challenge has a budget of 20 tool calls or 20 minutes. Inspect the
three highest-leverage assumptions and material mechanisms added since the
prior accepted record. If that slice cannot establish a verdict, return
`UNKNOWN` with the smallest missing evidence; do not expand into a full code or
repository audit.

## Two-pass method

### 1. Derive the minimum design without seeing the proposed architecture

Give the challenger the supported user journey, direct user decisions, external
policy, platform facts, compatibility promises, and observed failures, but
withhold the proposed component graph and implementation plan.

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

An author's label such as `product decision`, `security requirement`, or
`existing architecture` is a claim, not proof. Historical implementation is
provenance, not authority. A tactical user approval is also not proof of a
top-level need. A control cannot expand from one actor to another merely
because both actors produce the same side effect.

From that evidence, derive the smallest design that satisfies the verified user
journey and security boundary. Mark unsupported or conflicting claims
`UNKNOWN`; do not silently convert them into requirements.

### 2. Compare the minimum design with the actual work

Now give the same challenger the proposed design, current charter and baton,
recent task assignments and handoffs, changed repositories and files, new
tests and proof obligations, and material implementation added since the prior
challenge.

Trace in both directions:

- **Forward:** for each of the three highest-leverage assumptions, identify the
  components, implementation, tests, proof, and operations it creates.
- **Reverse:** for every material component or work item added since the prior
  accepted record, identify the verified user need, threat, external
  obligation, or current compatibility promise that requires it.

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
three highest-leverage assumptions unless one of them exposes another
load-bearing dependency. This prioritization is mandatory: the pass must not
become a broad audit of every default or numeric value.

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
direct_user_quotes:
user_statement_classification:
job_to_be_done:
inferred_product_judgment:
top_level_goal_conflicts:
verified_user_outcome:
minimum_design:
top_load_bearing_assumptions:
untraced_work:
security_boundary:
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

The challenger is complete when every top-ranked assumption has an independent
trace, every material new mechanism in the bounded slice has a reverse trace,
the minimum-design comparison is explicit, and one verdict is persisted.
`NARROW`, `REFRAME`,
`ESCALATE`, and security-relevant `UNKNOWN` block implementation.
