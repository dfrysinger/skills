---
name: development-loop
description: Develop and ship one non-trivial code change through a risk-sized loop — establish the failure, triage the blast radius, prove runtime behavior with machine-validated receipts, review, and land. Use when fixing bugs, building features, refactoring, changing UI, or changing apps, services, agent workflows, pipelines, or SDKs; invoke it before claiming runtime work is ready, opening or updating a PR, or landing. When triage finds shared state, persistence, public contracts, cross-component architecture, security, or fail-closed boundaries, invoke `design-doc` before coding.
---

# development-loop

Ship one coherent change using the lightest process that proves its actual
behavior and realistic blast radius. Start small; enlarge the process only
when observed evidence requires it.

**Phase gate:** externally observable runtime claims must pass on the actual
candidate before implementation review, broad CI, full lint or PR work.
Targeted diagnostics needed to make the candidate runnable may precede proof.
Landing, release readiness and completion require the complete final
acceptance set to pass against one frozen candidate.

Before a consequential decision, name the positive evidence establishing its
prerequisite for the current source. An empty observation, no work in flight,
or failure to match one pending flag does not prove successful completion.
Keep unresolved observations distinct from confirmed absence and stale-source
observations distinct from current ones.

Build a small decision table covering the producer's initial state and every
reachable resolution: pending, success, confirmed absence and each terminal
failure. List existing terminal exits and the inputs each actually depends on.
Route an independent terminal result before waiting on unrelated state; put
it behind the wait only when the producer contract proves that dependency.
Check every proposed predicate against every row, including old exits a new
guard could shadow.

Prove changed decisions through the component/service owning the user-visible
result. Begin before its producer starts, control completion order, and assert
intermediate and terminal results for every changed or shadowable row. A helper
fed chosen inputs is a diagnostic, not owner-level proof. Simplifying a guard
reopens these checks before build or review.

## 1. Diagnose the behavior

For a failure, separate the report from the observation. Reproduce it at the
cheapest boundary that directly establishes the reported result: a focused
functional test, retained output, state query, existing log or running product.
Trace the request to the wrong result, recording each consequential decision
and its source/state. Stop at the earliest verified divergence, not a general
label such as "caching is broken."

Use this diagnosis ladder in order:

1. Compare retained outputs and their metadata.
2. Trace recorded inputs through source, build and generation paths.
3. Read existing logs and use available diagnostic surfaces.
4. Add one reversible probe or reproducer only for a named question the first
   three rungs could not settle.

Record the rung, what its evidence establishes and what remains unknown.
Before a probe, classify its architecture, trust, authority, irreversible-state
and production/release effects. Challenge material changes before probing;
ordinary single-purpose read-only diagnosis needs no new design campaign.
An unexplained failure is not permission to weaken the criterion it failed.

When a browser, WebView, callback, OS API, protocol or external response is
uncertain, state a falsifiable hypothesis and the smallest distinguishing
observation. Prefer the failing process's existing console, debug, CDP, IPC or
API surface to production edits and rebuilds. A successful invocation is not
proof of its effect. Keep or reject the hypothesis from the resulting state
before choosing an implementation. Code, platform integration and complete
user-flow proof establish different boundaries; use each that the claim needs.

If diagnosis still resists reproduction, use a bounded `rubber-duck` pass for
one hypothesis and distinguishing check. Record an unresolved hypothesis
honestly; it cannot authorize a path that depends on an unobserved mechanism.
For a visual failure, capture its failing state with `visual-proof` before
editing.

**Replay upgrades before editing.** When changing behavior that has already
produced saved results, use the unchanged implementation to create a small
input exercising those results and their status/error meanings. Keep the
produced input. Define which meanings the changed consumer must retain and
which must disappear. After the edit, consume that same input through its
owning path, including paths that reuse it without recomputation. Check the
current semantic assertions there. Newly produced data proves a separate
boundary, not compatibility with previously stored output.

Complete diagnosis when the observed result, traced path and verified cause
are explicit, or the unresolved hypothesis and failed distinguishing check
are labeled. For a feature, specify the intended observable result instead.

## 2. Size the contract

Record the objective, acceptance criteria, non-goals and selected lane.
A bounded change reuses established architecture, has a clear observable
regression, and changes none of: authentication/authorization, public contracts,
schema/migration/storage semantics, shared concurrency, fail-closed boundaries,
security, privacy, data integrity or production infrastructure.

For anything else, use `design-doc` before implementation. An existing design
counts only when reviewed and applicable to this exact work. It must carry the
lane, invariants, acceptance criteria, check contract, Definition of Done,
constraint provenance and revisit conditions. Promote a bounded change when
tracing or a failing check proves a larger change is necessary, not in
anticipation of hypothetical callers.

Reuse before extending; extend before creating. A focused functional regression
is usually the durable guard for a localized bug. Larger work implements its
reviewed check contract. Add architecture documents, structural guards or
frameworks only when they protect a distinct required boundary.

Turn externally observable acceptance into short scenarios: trigger,
intermediate checkpoints, terminal success and forbidden outcomes. One
independently observable claim gets one receipt; dependent checkpoints of the
same journey stay together. Neither a partial result nor an easier fixture
can silently replace this contract.

For systemic/critical work, compare the exact next action with the recorded
constraint gate: `CLEAR`, or `PARTIAL` explicitly permitting it. Persist the
current record, proposed action, changed inputs, named trigger and
`REUSE`/`DELTA`/`FULL` decision before invoking `constraint-challenge`.
Invoke it for material scope, architecture, trust, authority or policy changes,
new subsystems, effective inherited limits, or repeated repairs that move the
same failure between internal boundaries without product progress. Diagnose
failures before challenging their proposed response. Elapsed time, a consumed
action or new evidence alone is not a trigger.

A fired reframe/revisit condition stops the implicated implementation. Return
to `design-doc` with the cause, protected invariant and simplest alternative.
Before another mechanism on the same causal branch, test removal of the parent
premise rather than preserving prior machinery because it was built.

For a security control, name the protected asset, untrusted actor, unauthorized
operation and independent authority/policy. Separate an attacker's operation
from an owner's deliberate authorized action. If that distinction is
unresolved, return to design/challenge rather than inventing a guard.
Preserve relevant user decisions verbatim with stable event identifiers;
summaries cannot replace their authority.

Complete when the applicable reviewed contract and gate permit the exact next
action. User-facing visual journeys also record whether walkthrough evidence
is required; a fix may use paired screenshots instead.

When the user explicitly wants to explore an interface before durable tests,
label the candidate exploratory and record deferred gates. Reuse its watcher
and change one visible behavior at a time. User acceptance freezes that
interface, ends exploration and opens contract/regression work before normal
proof, review and landing. Manual exploration counts as proof only with the
same candidate identity, checkpoints and explicit confirmation.

## 3. Reconcile state and ownership

At task start, resumption, phase/candidate movement, failure, handoff, material
direction or a wait, audit the critical path: ready work, prerequisites and
exclusive work. Execute cheap ready work directly; delegate substantial
independent work when safe. Every writing delegate gets an isolated checkout.
One owner controls each scope until its frozen handoff is consumed; the
coordinator's tree and documents have one writer.

Record each assignment's stable ID, exact routable owner, scope, writable
paths, workspace/branch, expected evidence, blockers and integration boundary.
Preserve user-assigned owners. Worker state is not artifact state: read the
owner's explicit current result before reporting status or transferring writes.
A clean/dirty/changing tree proves no worker status. If a response is missing,
record `unknown`, request it once through the known route and advance other
ready work; never guess a missing route. Close completed assignments and
consume their evidence before successor integration.

Complete the audit when every ready scope has an owner, no writes overlap,
completed handoffs are consumed, and serial work names its actual gate.

## 4. Build a coherent candidate

Add the smallest functional test for the diagnosed failure or required behavior,
preferably red before the fix. Use existing test/type/build infrastructure.
If a reviewed design requires an invariant guard first, prove it red on a
deliberate violation and green after restoration, then run one paired
`dual-review` of that guard/check contract before implementation. This is the
pre-proof review exception; other tests are reviewed with working implementation.

Read the nearest current sibling before adding a handler, model, test or
other unit. Match the architecture, helpers, naming, structure and error
handling the codebase is moving toward. A one-off incompatibility needs an
explicit reason and bounded `rubber-duck` check; a pattern change affecting
siblings needs the user's decision. Keep unrelated refactors and pre-existing
issues outside the diff unless the change relies on or worsens them.

Batch causally related fixes before expensive production artifacts. Settle a
deterministic state transition with focused checks, then build the candidate
once. Use the full native/CI matrix for final proof, not iterative diagnosis.
Reserve pre-edit native builds for unresolved platform behavior, not a bounded
bug already established by cheaper evidence.

Preserve a healthy running watcher/HMR process. Classify changes before editing:
hot-loadable code/copy stays in it when loaded identity can be observed; native,
dependency, build or generated-runtime changes get the smallest required
rebuild/restart. Create a process only when it is missing, unhealthy, the wrong
candidate or unable to load the change. Branch bookkeeping alone is not a
reason to replace matching content or restart the product.

Freeze a stacked dependency after its own compiler/lint gates, rebase the child
once and keep that stack fixed through expensive proof/review. Move it only for
required mergeability, human direction or a material dependency correction.
Then refreeze the child and assess affected proof rather than pooling results.

When a tool wraps, composes or inserts an artifact, read its caller contract:
who owns entry points, wrappers and dependencies? Check the artifact as the
consumer actually assembles it. Producer-only success is insufficient.
If the primary build is unavailable, use an equivalent consumer in the
workspace or keep composition unverified.

Translate supported policy into actual caller behavior, not merely a derived
field. Trace its authoritative source through configuration and the owning
consumer; exercise refusal and terminal-error paths as well as success.
An emitted setting is not enforcement until that consumer applies it.

Close identity chains through actual loaded inputs: selected source, generated
artifact, caller flags, dependency contents and runtime. A filename, claimed
hash, manifest or emitted flag is insufficient when the next consumer may load
different bytes or apply different policy. Preserve source/model/fixture
differences instead of treating similar-looking outputs as interchangeable.

Complete when the scoped diff is coherent, focused diagnostics pass, the
consumer seam loads and the candidate is ready for real proof.

## 5. Prove behavior on the exact candidate

For runtime work, create stable `live-proof-<claim-id>` todos and
`live_proof_receipts` rows immediately, initially `INCONCLUSIVE`. Use structured
JSON receipts if session SQL is unavailable. After resumption, rederive claims
from acceptance and reconcile them one-to-one with todos, rows and receipt
paths. A partial or empty ledger is not completion.

Read [live-proof-receipt](references/live-proof-receipt.md) when registering,
fingerprinting, validating or reusing a claim. Use its existing validator,
not a hand-written clean-commit identity for a dirty tree. Identity must cover
tracked changes, relevant untracked/ignored files, configuration, actual
dependencies, build/runtime/generated inputs and fixtures. Exclude only
predeclared evidence outputs that cannot affect the executable candidate.

Record running identity mapping the process/build/model to that candidate.
A retained watcher needs evidence it loaded the exercised changes; it need
not be newer than the edit. One proof owner controls the candidate, process
and fixture during live proof. Other agents and scheduled turns remain
read-only there, advancing only independent work.

Exercise the supported real path and inspect its actual state, including
intermediate checkpoints, terminal result and forbidden outcomes. Use the
real model when behavior depends on it. Scripted or mocked success, an
invocation returning success, and a helper printing PASS cannot replace
platform/product observations. Read
[live-harness-traps](references/live-harness-traps.md) when a helper, workflow,
API harness, collector or substituted component participates in proof.
Use `visual-proof` for graphical evidence and actually inspect its captures.

Treat login, MFA, JIT, account selection and protected input as a human handoff.
The agent sets up and verifies the real protected-input page is visible,
stable and usable before asking the user to act. A URL, copied code, launcher
success or blank window is not readiness. Diagnose a broken handoff rather
than transferring it. Continue already-authenticated state; reauthentication
is a gate, not permission to inspect cached credentials or switch accounts.
After the user acts, inspect the resulting state; dismissed prompts do not
prove success. If the user is away and `agent-help` is available, notify once
with the matching reason and a short non-secret label, then advance only
independent work. Subjective acceptance stays pending until explicitly given.

After candidate movement, write a change-to-claim impact map before choosing
replays: each changed executable path, configuration, dependency, generated
asset or fixture must name reached claims and why others are unaffected.
Mark reached rows `STALE` and preserve old receipts under their execution
identity. Reopen aggregate readiness until final acceptance passes.

Reuse results only when separate checked correspondence proves all relevant
contents, modes, types, directory membership, configuration, dependencies,
build/runtime/environment/generated inputs, callers and fixtures unchanged.
Include the harness for deterministic results. Keep original candidate,
process/model identity and observations untouched. Record a new complete
target fingerprint and per-claim applicability separately. Commit/worktree
movement alone does not require replay; unchanged source alone does not prove
reuse. Unknown coverage or a changed relevant input requires new proof.
Never manufacture old execution-time measurements after the fact.

Run the receipt validator, with checked reuse where applicable. Copy accepted
paths, target identity and result into the durable row and close its todo only
on accepted `PASS`. `FAIL`, `BLOCKED`, `STALE` and `INCONCLUSIVE` remain closed
gates. On failure, record the first divergent checkpoint, diagnose and fix it,
then rerun the reached claim. Partial success cannot narrow acceptance.

Complete when every changed externally observable claim has current accepted
proof and no unexplained error, manual workaround or unverified criterion.

## 6. Review and final acceptance

Revalidate affected claim receipts before review. Once they pass, run remaining
deterministic checks proportionate to the lane and invoke `dual-review` with
objective, acceptance, non-goals, lane, coherent diff, tests/guards, relevant
design and actual proof results. Check local idiom and that guards fail for
the intended reason without vacuity or rejecting authorized behavior.

Use its bounded loop: discovery, fix/delta verification, then unresolved
material findings only. Classify must-fix, verification-needed, follow-up and
dropped findings; permit an honest zero-findings result. Disputed material
blockers may use its selective verifier, not another full-diff reviewer.
Critical security/authorization/data-integrity risks remain must-fix even
when reproduction is difficult.

Escalate to the `deep` code-review ensemble only for systemic/critical work
with a concrete need: inseparable large reasoning scope, coupled independent
owners/flows, unrecoverable boundary risk, or an unresolved material round-two
blocker. Preserve runtime proof and default dual review; ensemble findings
still enter the ordinary scope/risk gate. Use the real convention file and
exact worktree/base/head; store its run under project/session, not `/tmp`.

Review fixes get an impact map and reached diagnostics/proof before further
review. Even a behavior-preserving executable edit within a exercised scope
needs replay. Reuse unaffected evidence only through validated applicability.
Final acceptance reconciles the entire required claim set against one exact
frozen reviewed candidate. Every claim must have accepted direct proof or
checked reuse and the aggregate must pass.

For broad CI failures, run the smallest equivalent canary on the frozen
candidate. Compare with the exact base or main when repository health is
suspected. Rerun only failed intermittent jobs on the same candidate, retaining
the original failure and rerun evidence. A repeated failure remains unclassified
until a focused check/control establishes its cause. Change the candidate only
for a demonstrated candidate defect reaching changed behavior, not to get a
green workflow; batch the correction and refreeze.

After the final reviewed visual journey is frozen, use `walkthrough-video`
when required. Rehearse, record, fully decode/inspect, host and bind the movie
to the demonstrated candidate before PR work. Runtime movement makes it stale.
Visual fixes may retain their required paired screenshots.

Complete when final acceptance, proportionate deterministic checks and review
have no verified in-scope must-fix remaining.

## 7. Land and preserve continuity

Before landing, release-readiness or completion, revalidate the complete final
receipt set on the exact target. All proof rows must be accepted PASS and their
todos closed; checks/review must pass, the diff stay scoped, required visual
evidence be attached and temporary artifacts be cleaned up. Use repository
commit/merge/release policy and verify produced/published/installed bytes when
the deliverable crosses those boundaries.

Treat substantive verified PR review comments as fix deltas; hypothetical,
adjacent or non-blocking comments do not restart the entire loop.

For long/unattended work, `unattended-run` owns the initial implementation
handoff, one four-hour liveness backstop and its schedule registry. Register
this governing skill and relevant execution/context skills. Event-driven
critical-path audits and material challenges remain immediate, not timer
jobs. A liveness tick checks coherent state; it runs a full audit only for
stale/inconsistent state. Stop reminders only when the actual Definition of
Done is verified.

At phase resets, use `self-compact` only when permitted by the user's context
instructions; the initial unattended handoff belongs to `unattended-run`.
Persist the baton first: work order, lane, objective/acceptance/non-goals,
remaining Done items, branch, delivered versus pending work, impact map,
receipts/status/identities/divergence/unverified items, exact owners and
integration boundaries. Systemic/critical batons also carry constraint
provenance, open revisit/reframe conditions, current gates and admission,
unserviced triggers, exact new user decisions and schedule registry.

Stop scope expansion when work adds an unsupported subsystem, repeats the same
unproductive internal-boundary repair, reviews adjacent issues, duplicates
guards without distinct evidence, or continues after only non-blocking findings
remain. Reframe the premise or use the existing bounded completion ladder.
Land only when the material gates pass; otherwise preserve the named blocker
and next supported action rather than claiming completion.
