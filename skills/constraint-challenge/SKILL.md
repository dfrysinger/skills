---
name: constraint-challenge
description: Challenge proposed scope before implementation. Use when a plan may be adding mechanisms, controls, proof, coordination, or operational work beyond what the user outcome requires.
---

# constraint-challenge

Find the smallest justified path to the user's outcome. Be strict about adding
scope, not about removing unsupported scope.

## Method

1. State the user's job, supported caller, and observable result. Quote direct
   decisions exactly when available. A tactical approval permits an option; it
   does not prove the option is necessary.
2. Separate required outcomes and proven security or compatibility boundaries
   from the mechanisms currently used to provide them. Preserve independently
   supported outcomes when narrowing scope; do not remove a proven boundary
   merely because a broader project or mechanism is being removed.
   When a multi-application or end-to-end release shrinks to a core capability
   MVP, translate each retained capability and release boundary into the
   smallest focused acceptance fixture. Do not make an independently required
   capability optional merely because the selected fixture would avoid
   exercising it.
3. Identify the material work being added or retained. Examine at most the
   three additions that create the most implementation, coordination, proof, or
   continuing ownership.
   When an addition exists to accommodate the incumbent mechanism's limits,
   challenge that parent mechanism before tuning its quota, adding an API, or
   strengthening its coordination. The incumbent is a candidate, not settled
   context. Until that comparison closes, do not accommodate the incumbent by
   raising a quota, widening a grant, adding an API, or expanding proof.
4. For each addition, require:
   - an independent user need, reachable risk, external obligation, measured
     demand, or current compatibility promise;
   - a concrete explanation of what fails without it;
   - comparison with the simplest existing capability that could produce the
     same result.
5. Search for that simpler capability across the existing system, not only in
   the proposed component or abstraction. Identify the actual actors, writers,
   operations, and already-owned artifacts. A current runtime limitation is an
   implementation choice, not authority that alternatives are forbidden.
   Before adding transport, ingestion, synchronization, or publication work,
   verify that the destination does not already contain the required data or
   bytes.
   - Before retaining coordination, locking, atomicity, or multi-writer
     machinery, identify at least two evidenced writers or callers and their
     conflicting operations. Hypothetical concurrency does not justify it.
   - For a sandbox, allowlist, or denied capability, inspect both what is
     blocked and what bounded capability is already available. An API or
     service that recreates a denied operation is another grant of that
     capability and must justify its necessity against the simpler bounded
     grant. Name the concrete existing alternative, its owner, and its
     lifecycle; an unspecified future facility is not a comparison.
   - Resolve each operation independently. Sharing a service, process, or
     component does not let authority for one operation justify another.
6. Remove or defer an addition when its support comes only from the proposal,
   an earlier challenge conclusion, existing implementation, completed proof,
   an accepted design or work-order criterion, a preferred default, or fear
   without a reachable failure path. Calling unsupported work deferred does not
   make it a valid future requirement; future hardening needs fresh authority.
   Do not require symmetric proof that unsupported scope is safe to remove.
7. For a security restriction, name:
   - the protected asset;
   - the actor whose runtime behavior is outside the authority owner's control;
   - the operation that actor must not perform;
   - the evidence making that operation unauthorized.

   Classify control per operation and influence path, never for an entire
   workflow, process, file, language, or runtime merely because untrusted
   behavior also occurs inside it. Deterministic orchestration reviewed by the
   authority owner remains owner-controlled when it invokes an untrusted
   subsystem; only behavior that subsystem can choose or alter is untrusted.
   Reviewed deterministic action accepted by the authority owner is the owner
   exercising authority unless another actor can alter or invoke it outside
   that approval. A model or attacker must not acquire or exercise authority
   beyond the owner's approved grant. A deliberate owner grant may be risky,
   but it is not model privilege escalation. Restrict owner choices only when
   a direct product requirement, evidenced policy, obligation, or harm to
   another party or asset requires it. Owner freedom does not erase an
   independently required mediation or separation boundary. A proposal saying
   an actor currently lacks a permission proves the current configuration, not
   that the owner must be forbidden from granting it. Rewrite categorical
   denials as "not unless deliberately granted" only when no independent
   authority fixes the ceiling. Record whether external policy is evidenced,
   absent, or unresolved.
   A model-controlled actor exercising an explicitly approved grant is not
   acquiring authority beyond that grant. Do not retain a categorical
   permission denial merely because a safer mediated path exists.
8. Treat exact components, versions, artifact bundles, topologies, permission
   sets, fixed proof counts, and verification systems as candidate mechanisms,
   not requirements, unless independent authority requires that exact choice.
   A current pin proves current state, not a need for version closure. Preserve
   ordinary reviewable source-to-artifact correspondence, but do not turn it
   into semantic admission or policy enforcement without an observed gap and
   independent authority.
   When removing an overbroad assurance or proof method, name the independently
   supported property it was meant to protect. Preserve the smallest direct
   evidence that the reviewed component, delivered artifact, and
   installed/executed component correspond and refuse substitution when that
   property is required. A failed or excessive proof method does not prove that
   no check is needed.
9. When later evidence changes an actor, operation, risk, or supported caller,
   reopen every dependent conclusion. A prior record or matching hash is not
   authority.
10. Challenge a materially changed trust boundary before exercising it. Reuse
    a prior result when the actor, authority, operation, effects, and protected
    boundary are unchanged; do not rerun after every invocation. After removing
    a bad work order or control, reconcile and explicitly clear the corrected
    bounded action rather than treating removal itself as permission to run.
    Adding or removing filesystem, network, code-execution, credential, or
    carrier allowances changes the trust boundary even when the package and
    intended high-level operation are unchanged.
    A challenge may reject the proposed action, but it cannot simultaneously
    clear a materially different replacement that is not fully specified in
    the current work order. First write the corrected bounded action, then run
    one focused reconciliation against that exact action.

## Decision rule

- `CONTINUE` only when the pending additions are independently necessary and
  no simpler evidenced path remains unresolved.
- `NARROW` when the user outcome survives after removing unsupported additions.
- `REFRAME` when a load-bearing premise, actor classification, or requirement
  fails.
- `UNKNOWN` only when one named unavailable fact decides whether an addition is
  necessary. Block that addition while allowing the smallest independently
  supported path to continue.

When the incumbent mechanism and a simpler alternative remain unresolved,
block new work that accommodates either one. `UNKNOWN` is not permission to
tune the incumbent while postponing its necessity decision.

Do not clear a dependent implementation, release, or merge action when removing
its current assurance method leaves a retained property unproven. First replace
the work order with the narrower property and a runnable minimum check; block
only until that replacement boundary exists.

Do not create an exhaustive inventory, work graph, proof campaign, or challenge
record unless the user explicitly needs one. Spend no more than 20 minutes on
the bounded decision.

## Return

State:

- the decision and its effect on the pending action;
- the user outcome and authority used;
- `keep`, `remove`, and `unresolved`, each limited to material items;
- the smallest next step.

For each retained addition, give its independent authority and the concrete
failure it prevents. For each unresolved addition, name the single deciding
fact. Preserve a recommended or default safety path in any role where the owner
may select it, even when it is unsuitable for another role. A recommendation
stays optional unless independent authority makes it mandatory.
Controls intrinsic to an optional safety path remain conditions of that path
when selected; they do not become mandatory policy across alternative
owner-approved paths.

Before returning, explicitly state whether deliberate owner grants are allowed,
whether external policy constrains them, and whether each retained security
control governs owner-approved action or only authority expansion by an
untrusted actor.

For every retained coordination or shared-state mechanism, state the evidenced
writer or caller count; fewer than two conflicting writers cannot justify
concurrency machinery. For every denied capability, state whether another API,
service, or sandbox grant can produce the same effect and compare that indirect
path with the simplest direct bounded grant.
