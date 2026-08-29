---
name: development-loop
description: Develop and ship one non-trivial code change through a risk-sized loop — establish the failure, triage the blast radius, prove runtime behavior with machine-validated receipts, review, and land. Use when fixing bugs, building features, refactoring, changing UI, or changing apps, services, agent workflows, pipelines, or SDKs; invoke it before claiming runtime work is ready, opening or updating a PR, or landing. When triage finds shared state, persistence, public contracts, cross-component architecture, security, or fail-closed boundaries, invoke `design-doc` before coding.
---

# development-loop

Ship one coherent change through a process sized to its actual risk. The loop
must prevent regressions without turning a bounded bug into a speculative
architecture project.

The governing rule is:

> Use the lightest process that produces durable evidence for this change's
> realistic blast radius. Promote to a heavier lane only when concrete evidence
> requires it.

This skill orchestrates `design-doc`, `rubber-duck`, `dual-review`,
project-specific development/testing skills, and live validation.

The phase order is fail-closed:

> For user-visible or externally observable runtime behavior, do not start
> implementation review, broad CI, full lint, or PR creation or update until
> every claim reached by the current delta has current passing proof. Do not
> land, claim release readiness, or complete the task until the complete final
> acceptance campaign has passed on the exact frozen tree.

Targeted tests, type checks, and builds needed to make the live candidate
runnable may happen first. They are development diagnostics, not acceptance
evidence. The conditional pre-build guard review in section 4 is the only
implementation-review exception; it reviews a guard that constrains the work,
not an implementation claimed to work.

### Critical-path audit

An efficient loop keeps every independent ready item moving while preserving
the serial evidence gates. Run this audit at task start, after compaction or
resumption, at each phase boundary, and whenever the current action is waiting:

1. Map the remaining work into ready items, dependencies, and work that must be
   exclusive. Mark the critical path.
2. Execute cheap direct work immediately and batch independent tool calls.
   Give every substantial independent ready scope to a subagent when the host
   supports it and delegation is safe. Delegated scopes must have separate
   context and no overlapping ownership; one agent owns a scope until it
   completes or fails. Every delegate that writes files gets an isolated
   worktree or checkout; read-only delegates may share a source tree. The
   coordinator's worktree is never a concurrent write target.
3. Track every delegated agent as an owner, whether the user or coordinator
   assigned it. Record its scope, workspace or branch, session or coordination
   channel, expected evidence, and integration boundary. When the user assigned
   the agent, preserve that record in the durable baton and treat it as a
   first-class external owner. Keep each owner supplied with decisions and
   dependencies, unblock it promptly, and consume completed handoffs and frozen
   reviewed commits without waiting for `main`.
   Keep **worker state** separate from **artifact state**. Before reporting an
   assigned agent as active, waiting, blocked, failed, or complete, read that
   agent's latest explicit session result, task result, mailbox response, or
   handoff. A dirty, clean, changing, or unchanged worktree describes files; it
   does not establish what the agent is doing. When an agent completes its
   assignment, close that assignment and consume its handoff before inspecting
   the worktree or issuing successor work.
   Evidence that predates the current assignment cannot establish its status.
   When no current explicit result exists, record the worker state as
   `unknown`, request status once through its task or coordination channel, and
   advance other ready work. Never substitute repository movement for the
   missing response.
   A successor task is a new assignment, even when it goes to the same agent.
   Freeze the prior commit or receipt and explicitly transfer worktree
   ownership before the coordinator or another writer touches it. If two
   writers appear in one delegated worktree, stop both integration assumptions
   and restore one named owner before continuing.
4. Keep the coordinating agent on integration, critical-path work, decisions,
   and blockers that no delegate can own. When one action is waiting, advance
   another ready item instead of polling or idling.
5. Batch causally related fixes into one coherent candidate before expensive
   builds, verifiers, or CI. Use the change-to-claim impact map to rerun only
   the proof reached by that candidate.

Parallelism stops at an actual dependency or exclusive boundary. One proof
owner and one running candidate remain mandatory during live proof, and review,
broad CI, or PR work stays closed until the affected live claims pass.

The audit is complete when every ready item has an active owner or is being
executed directly, each delegated status comes from the owner rather than its
worktree, completed handoffs have been consumed, no owner is waiting for
information the coordinator already has, scopes and write ownership do not
overlap, and every intentionally serial item names the gate that makes it
serial.

### Durable proof admission

As soon as a task is classified as user-visible or externally observable
runtime work, create one stable proof id per independently observable
boundary or claim and make each open gate survive context loss. Keep dependent
checkpoints of one user journey in one receipt. Give unrelated systems,
independent refusal paths, bootstrap boundaries, and tamper lanes separate
receipts so one repair does not turn every proof into one all-or-nothing replay.
In Copilot CLI:

1. add a pending `live-proof-<claim-id>` todo for each claim, naming its exact
   trigger and terminal state;
2. insert or replace the same claim id in `live_proof_receipts` with status
   `INCONCLUSIVE`, the planned scenario, and its receipt-artifact path;
3. keep each affected pair open through implementation, compaction, rotation,
   scheduled turns, review fixes, and candidate rebuilds.

If session SQL is unavailable, create the structured JSON receipt from
[`references/live-proof-receipt.md`](./references/live-proof-receipt.md)
immediately and leave its status `INCONCLUSIVE`. Do not rely on a checklist
that exists only in conversation history.

After context loss or resumption, re-derive the required claim set from the
acceptance criteria and reconcile it one-to-one with the proof todos, durable
rows, and receipt paths. Create any missing claim record as `INCONCLUSIVE`
before continuing. An empty or partial proof-record set is never a completion
signal.

After a runtime-relevant candidate change, first write the change-to-claim
impact map required by section 6. Mark only affected claim rows `STALE` and open
successor receipts for them. Preserve unaffected passing receipts as diagnostic
history under their original fingerprints; they do not authorize a release
verdict for the new candidate, but they do not mandate immediate replay. Treat
aggregate release readiness as `STALE` until the final frozen-candidate
campaign passes. Close a claim todo and write `PASS` only after its receipt
validator accepts the current candidate.

### Tracer-bullet UI branch

Use this branch when the user explicitly wants to explore and refine a
user-visible interface before investing in durable validation. It changes the
timing of sections 2, 4, and 5, not the evidence or landing requirements.

Record the candidate as exploratory, the interaction being evaluated, and the
deferred gates. Reuse the running watcher or HMR process and change one visible
behavior at a time. Produce only enough diagnostics to make that slice load in
the existing runtime, then hand the runnable candidate to the user. Treat their
first visible divergence as the next work item; keep accepted behavior fixed
while refining that divergence.

User acceptance freezes the interface candidate and ends this branch. Encode
the durable contract and regression tests, run the proportionate deterministic
checks, and continue through the normal live-proof, review, and landing gates.
Manual exploration counts toward live proof only when its candidate identity,
scenario, checkpoints, and explicit confirmation satisfy section 6's receipt.

Complete when the user has accepted the frozen interface candidate, every
deferred gate is recorded for the normal loop, and no exploratory result has
been represented as validated or ready to land.

## 0. Establish the failure

Wrong behavior is diagnosed before it is classified: a misdiagnosed bug gets
designed for the wrong lane. This step fires whenever observed behavior is
wrong — a bug, a regression, a flaky test, a feature that misbehaves. Work that
adds behavior starts at section 1.

Watch the failure happen at the boundary it surfaces on: the running screen,
the CLI output, the API response, the stored result, the process logs. Record
what you observed and keep it apart from what the report claimed. A failing
test encodes an observation; it does not replace looking.

Then trace from the trigger to the wrong result, naming each hop and the state
it carried. The cause is the earliest verified divergence — the first point
where correct input produced wrong output. It can be a line, a branch, a state
transition, a configuration, or a dependency's response, and it names something
specific enough to be wrong: "the cache key omits the tenant id", not "caching
is broken". Trace every hop that can change the reported result and stop there;
a local predicate is one hop, not an expedition.

**Probe uncertain mechanisms before designing around them.** When the proposed
fix depends on an unobserved browser or WebView operation, OS API, callback
bridge, framework lifecycle, protocol, or external-service response, state one
falsifiable hypothesis and the smallest observation that distinguishes it.
Test that mechanism directly in the failing process when possible. Prefer an
existing debug, eval, console, CDP, IPC, API, log, or temporary diagnostic
surface over a production edit and rebuild. Keep each probe reversible and
single-purpose, and record the observation separately from its interpretation.

A successful invocation proves only that the caller returned success. It does
not prove the runtime effect occurred. Keep or reject the hypothesis from the
observed effect before choosing architecture or writing production code. When
no direct route reaches the boundary, add a safe debug-gated reusable route as
described by `visual-proof` section 3a when that instrumentation is
proportionate to the change. Do not impose instrumentation on a deterministic
local bug whose mechanism is already established.

When no proportionate probe can observe an uncertain mechanism, do not
implement a path that depends on it. Record the unresolved hypothesis, then
choose a path that uses established mechanisms or keep the work blocked until
the mechanism can be observed.

| Proof | Shows | Does not show |
| --- | --- | --- |
| **Code** | Internal logic behaves correctly | The real platform integration works |
| **Integration** | The browser, OS API, callback, protocol, or service performs the operation | The complete user workflow succeeds |
| **End-to-end** | The actual build completes the full user workflow | Every internal edge case is covered |

Use the levels in order when each is relevant; lower proof never substitutes
for higher proof. For runtime failures, read current state and logs, run one
direct probe, keep or reject its hypothesis, and repeat only for the next
uncertain bridge. Then resume the normal workflow at section 1; mechanism proof
does not select the lane, satisfy the durable contract, or authorize skipping
design, tests, implementation discipline, or complete live acceptance. If a
production edit fails to sharpen the boundary observation, the next action is
a direct probe rather than another edit.

When the failure resists reproduction — production-only, timing-dependent, no
repro steps — force it with instrumentation, added logging, or a test that
recreates its conditions. If it still will not surface, `rubber-duck` the trace
for one pass, which returns either a verified divergence or one falsifiable
hypothesis and the check that would distinguish it; run that check. A fix that
ships on an undistinguished hypothesis says so in its durable record and is
reviewed as a hypothesis at section 7. Carry on rather than stopping for the
user.

When the failure is visual, capture it here through `visual-proof` while it
still fails. After the edit lands there is no before to pair the fix against.

Complete when you can point at the observed failure, the traced path to it, and
a named cause — or at a labeled hypothesis and the check that failed to settle
it. When an uncertain runtime mechanism was involved, also record the
hypothesis, distinguishing observation, observed result, and keep or reject
decision. An unresolved mechanism may complete the diagnosis record, but it
cannot authorize an implementation that depends on that mechanism.

## 1. Triage the change before designing it

### Bounded lane

Use when the change:

- fixes a localized behavior or adds a small capability;
- reuses established architecture and data flow;
- changes no authentication or authorization behavior, public contract, schema,
  migration, durable storage semantics, shared concurrency, or fail-closed
  boundary;
- carries no security, data-loss or corruption, privacy or compliance,
  production-infrastructure, or audited-control risk;
- has a clear regression test or observable runtime proof.

Examples: a restored UI loading stale state, a missing button state, a local
error-handling bug, or a well-understood adapter correction.

### Anything else

A change that fails any bounded condition — or that alters cross-component
architecture, a reusable framework, a central data-access boundary, or multiple
independent user flows — does not proceed past this section without a reviewed
design document carrying its lane, invariants, acceptance criteria, check
contract, and Definition of Done.

If a document exists, confirm it is finished and reviewed on `design-doc`'s
terms before reading its lane and continuing. A draft, a stale document
describing different work, or one that never cleared review is not one. If none
exists or it falls short, write or finish it with `design-doc` and return here.
That skill owns the scope and architecture call, decides systemic versus
critical, and reviews the design before any code exists.

### Promotion rule

Start bounded when uncertain. Promote only after code tracing, a failing test,
or a live reproduction proves the fix requires a larger change. Do not
generalize in anticipation of hypothetical future callers.

The rule keeps small work small. A change touching a listed boundary stays
larger even when the document is inconvenient, and a run whose recorded lane is
systemic or critical with no document path in its baton is misclassified.

Record the selected lane, objective, acceptance criteria, and explicit
non-goals before editing — from the design document where one exists, and in
the existing issue, plan, or session artifact for bounded work. Non-goals are a
review boundary, not an invitation for reviewers to add requirements.

For runtime work, turn the acceptance criteria into short live scenarios now,
one per independently observable claim. Name each trigger, its user-visible
checkpoints, terminal success state, and the errors or regressions that must be
absent. Keep checkpoints together when they jointly establish one claim. A
later partial success cannot silently become the proof contract.

For a pull request with a new or materially expanded user-facing visual
journey, also record `walkthrough: required` and invoke `walkthrough-video`
after live proof passes. A UI fix may use `visual-proof`'s paired screenshots;
pure API, service, or CLI behavior with no graphical UX records
`walkthrough: not required` and its reason.

## 2. Choose the durable contract

Do not require a standalone architecture document or permanent invariant guard
for every bug. For bounded work, use:

- a short change note in the existing issue, plan, or relevant design document
  when needed;
- one or more functional regression tests that fail for the observed bug;
- existing type, lint, unit, integration, and E2E infrastructure;
- a brief reuse check: reuse before extend, extend before create.

A regression test is usually the right durable guard for a bounded behavior
bug. Do not create a structural grep guard, invariant row, or new framework
merely to prove one local branch.

Larger work carries the contract its design document already defines.

## 3. Design and self-review

For bounded work, inspect the existing path, state the smallest fix, and ask:

- Can an existing helper, state owner, API, or error pattern carry this?
- What code and behavior are explicitly outside this change?
- What observable proof would fail if the fix were wrong?
- Is the proposed generalization required by a supported caller today?

Use a `rubber-duck` pass when the bounded solution is ambiguous, crosses
ownership boundaries, or risks broadening.

Larger work arrives with these questions answered by its reviewed design
document. Implement what it specifies and enforce its recorded constraint
revisit conditions. A design that turns out to be wrong goes back to
`design-doc`; do not reopen scope or architecture here.

### Reframe gate

For systemic and critical work, stop implementation and return to `design-doc`
when a recorded revisit condition fires, or when implementation would add a
new subsystem mainly to preserve an inherited limit or mechanism. Repeated
movement of a failure to the next internal boundary without user-visible
progress is evidence that the gate has fired.

Persist the blocked outcome, the implicated constraint and provenance, the
invariant that would fail if it changed, and the simpler alternative. Further
implementation resumes only after the work order and its design review accept
the reframed architecture.

*Handoff point: a design document, or a bug report with recorded acceptance
criteria and a Definition of Done under its own heading, is a complete work
order — it says what to build without the conversation that produced it. When
the work ahead is long, write that Definition of Done if bounded work lacks
one, then take one of these exits into implementation:*

- *Unattended, or long enough that the context will compact before the plan is
  done — run `unattended-run` against the work order. It arms the recurring
  charter re-brief that holds the run on course through compaction, and points
  its Definition of Done at the one the work order already carries. Register
  `development-loop` as the charter's governing skill, project-specific
  development and testing skills as execution skills, and `self-compact` as its
  context skill. Complete its live-schedule gate before any phase-boundary
  compact. It performs the handoff and compact itself, so do not invoke
  `self-compact` or `handoff` first.*
- *Attended and finishing in one sitting, but the run so far has been long —
  self-hand-off into implementation via the `handoff` skill.*

## 4. Tests and guards

For a bug, encode the failure established in section 0 as the smallest
functional test, before or alongside the fix. Red-first is preferred when
practical, but do not build a large test harness solely to obtain a red phase.
For new behavior, encode the acceptance criterion that would regress most
silently.

For systemic and critical work, implement the check contract the design
document defines; `design-doc` already reviewed it. Write executable tests and
guards alongside the implementation unless the document required a guard to
exist first.

When a guard must exist first, write it and prove that it goes red on a
deliberate violation and green on the restored tree. Before implementation,
run one paired `dual-review` round over that guard and the relevant design and
check-contract material. Fix `must-fix` findings; run one fix-verification
round only if material findings were found.

Do not run `dual-review` on the tests separately. They are reviewed with the
implementation after the behavior works.

## 5. Build a small coherent diff

*Compaction point: persist the plan/lane/acceptance state. For a long or
unattended run, section 3's `unattended-run` handoff must already have armed
its live re-brief and owns this reset; a bare compact returns to an idle prompt.
If the re-brief is not live, run `unattended-run` now instead of compacting.
For an attended run, invoke `self-compact`.*

Run the critical-path audit before starting the diff. Repeat it whenever a
build, external agent, approval, or live system becomes the current wait.

Preserve a healthy development process before creating another one. When the
same worktree already has a watcher-backed app or service running, classify the
changed files before editing:

- Hot-loadable frontend, template, style, and copy changes stay in the existing
  process when its watcher, HMR, or reload path can be shown to apply them.
- Native code, build configuration, dependencies, generated runtime assets, or
  another input the watcher cannot apply requires the smallest rebuild or
  restart that loads it.

The running process is working state, not disposable setup. Reuse it while its
identity matches and the current candidate can be shown to be loaded. Create a
new process when it is missing, unhealthy, the wrong identity, unable to load
the candidate through its reload path, or unable to apply a required input.

Branch from current main and implement one behavior at a time.
Branch bookkeeping alone is not a runtime change: when the checked-out content
already matches the intended base, rename or create refs without replacing it.
Otherwise update the tree to current main, classify the resulting file changes
under the rules above, then branch.

**Freeze stacked dependencies before final proof.** First pass the dependency
branch's own compiler, lint, and other candidate-defining gates. Record that
exact dependency commit, rebase the child once, then run the expensive build,
live-proof, and review ladder. Keep the proven stack frozen: movement on main
alone is not a reason to rebase it. Move the dependency only for required
mergeability, human direction, or a material dependency correction. When it
does move, the child candidate and its runtime evidence change; freeze again
and restart from the rebase rather than accumulating proof across histories.

For an expensive native, generated, or packaged runtime artifact, separate
diagnosis from artifact production. Reproduce the exact failure, settle the
state transition with focused tests or instrumentation, and batch the coherent
fix before producing another artifact. Build once per candidate, then run the
targeted acceptance flow; use a short bounded stress repetition only when the
defect is timing-dependent.

**Freeze the final CI candidate.** Treat the complete cross-platform or
otherwise expensive CI matrix as final proof, not as the primary debugging
harness. Before starting it, batch every fix supported by focused evidence,
pass the candidate-defining checks, and record the exact commit. Keep that
candidate unchanged while the matrix runs. A red flaky, unrelated, or
repository-health check is not permission to push a successor.

Change the frozen candidate only when a completed check proves a reproducible
candidate defect that reaches changed behavior. Diagnose it with the smallest
equivalent local, platform, or manual canary, batch related fixes, rerun their
focused checks, record the successor commit, and restart final proof once.
When pull-request policy permits, keep large or expensive work draft during
diagnosis and mark it ready only after the final candidate is frozen.

- Keep refactoring separate unless required for the fix.
- Prefer reviewable slices; roughly 200-400 human-written changed lines is a
  useful review target, not an absolute limit.
- If the change begins touching unrelated state owners or multiple independent
  flows, pause and split or promote the lane.
- Confirm `git diff --stat` contains only intended files.
- Do not repair pre-existing adjacent issues unless the current diff worsens,
  relies on, or makes them newly reachable.

**Write in the local idiom.** Before adding code, find the nearest current
sibling of the same kind — the closest handler, model, migration, or test —
and read it. Match its structure, naming, error handling, and file layout, and
reach for the same helpers it reaches for. New code should read as though
whoever wrote its neighbours wrote it too. Whether to write new code at all is
already settled in sections 2 and 3.

Current beats near. Where a migration is underway, the local idiom is the one
the codebase is moving toward, not the older neighbour it replaces. Matching a
pattern that is deprecated or being retired is itself a departure. When no
sibling exists, say so, follow the language and framework convention, and have
a `rubber-duck` pass confirm the first one — it sets the idiom for everything
that follows.

Departing from the local idiom is a decision rather than a default: name the
pattern you are leaving and the concrete incompatibility that makes following
it wrong. Inconvenience is not an incompatibility — needing to rewrite to match
is the rule working. A `rubber-duck` pass carries a one-off departure and
confirms it is genuinely one-off. A departure whose reasoning applies to the
siblings too is a pattern change, which is the user's call; record it and
follow the local idiom until they rule.

Before review, be able to point at the sibling each new unit followed, or the
endorsed departure. Section 7's reviewers check idiom parity.

Run only the smallest existing test, type, lint, or build commands needed to
catch cheap regressions and produce a runnable candidate. Do not spend time on
broad CI, full lint, or implementation review while the live acceptance flow is
still unproven.

## 6. Prove runtime behavior before static review

*Compaction point: when the implementation is ready for validation, compact so
runtime proof and any debugging start from a clean context.*

This is a hard gate for user-visible or externally observable runtime work.
When classification is unclear, treat the change as runtime work requiring the
gate. Before the first implementation review, run every externally observable
claim changed by the implementation in the real app or service. After a
successor edit or review fix, rerun the claims reached by the change-to-claim
impact map before review continues. The complete frozen-candidate campaign is
the later landing and release-readiness gate. Do not dispatch review, broad CI,
full lint, or PR work in parallel with an active live proof: a failed proof
invalidates the premise of that work and wastes time.

Before starting, record a structured **live-proof receipt** using
[`references/live-proof-receipt.md`](./references/live-proof-receipt.md):

- candidate identity: a clean commit, or a full candidate identity that covers
  tracked changes plus every untracked file that can affect the build or
  runtime; branch plus commit alone is valid only for a clean worktree;
- running identity: process/build identity that maps the running code to the
  candidate, not a stale installation or another agent's build. For a reused
  watcher-backed process, record its existing PID/worktree mapping plus direct
  runtime evidence that it loaded every changed input exercised by the
  scenario; the process need not postdate the delta;
- scenario: the exact trigger, required checkpoints, terminal success state,
  and forbidden errors from the acceptance criteria;
- evidence source: what the agent can inspect directly and what requires a
  human action or confirmation.

### Receipt granularity and impact mapping

Use one receipt for one independently observable boundary or claim. A sequential
flow whose checkpoints jointly establish one claim stays together. Claims that
can fail and be repaired independently use separate receipts, even when one
release campaign eventually requires all of them.

Before rerunning proof after candidate movement, write a durable
change-to-claim impact map. For every changed executable file, runtime path,
configuration, dependency, build input, and generated runtime asset, record:

- the runtime path it reaches;
- the claim receipts it can affect;
- any shared dependency that broadens reach;
- the evidence that makes other claims unaffected.

Every runtime-relevant change appears in the map, and every reopened claim has a
concrete reach path from that change. A broad replay requires a named shared
dependency or plausible regression path that reaches the additional claims.
The systemic or critical lane label alone does not broaden rerun scope, and a
new commit hash alone is not a reach path.

Generate the receipt's candidate object with
`scripts/validate-live-proof.py fingerprint`; do not hand-write a commit-only
identity for a dirty worktree. The fingerprint covers `HEAD`, tracked changes,
and every non-ignored untracked file except predeclared evidence outputs.
Ignored configuration or generated inputs that affect runtime are named as
additional inputs and hashed. The helper rejects excluding tracked files.

The receipt records evidence; it does not create evidence. Every `PASS` row must
point to a direct observation, artifact, query result, or explicit human
confirmation from this run. Agent-written summaries of what "should" have
happened are not evidence.

Run a real end-to-end check when the change affects runtime behavior that unit
tests cannot fully prove.

- UI: exercise the running app and capture it through `visual-proof`, which
  owns the capture surface, the settle, and what makes an image evidence.
- Service/API: call the running service and inspect the actual state/result.
- Agent/LLM: use the real backend/model when behavior depends on it.
- Pipeline/workflow: run the real canary or equivalent live path.

When a script, helper, CI job, or API-driven harness participates in the proof,
apply the fail-closed checks in
[`references/live-harness-traps.md`](./references/live-harness-traps.md).

For UI and authentication flows, exercise the interaction, not just the final
screen: opening/focusing the correct window, user input, redirects, retries,
auto-close/resume behavior, and the resulting app state are separate
checkpoints when the acceptance criteria name them. A screenshot of one state
or a source read succeeding after manual recovery does not prove the whole
flow.

For a new user-facing visual journey, the passing live receipt opens a
presentation-evidence gate before PR creation. Keep it pending through static
review so review fixes do not force avoidable recordings. The movie helps
reviewers see the feature but never substitutes for checkpoint evidence in
this section. Fixes may proceed with `visual-proof`'s paired screenshots unless
the user explicitly requests video.

Confirm every checkpoint and the observable end state, not merely a harness
exit code, scripted test result, log line, or helper self-report. Inspect the
actual app/service state out-of-band. Any unexplained user-visible error,
missing window, manual workaround, stale data, failed retry, race, or unverified
acceptance criterion makes the result **FAIL**, not "partial pass."

**Treat an authentication gate as a human handoff.** When live proof requires
login, MFA, JIT approval, account selection, or another authentication action,
stop at the ready candidate and ask the user to complete that action. Permission
to test the application is not permission to authenticate.

The agent owns setup through the last step before protected human input. Trigger
the application's login flow, follow its browser or window handoff, and directly
verify that the actual login, device-code entry, account-selection, MFA, or
approval page is visible, stable, and usable before asking the user to act.
Copying a code to the clipboard, printing a URL, opening a blank window, or
receiving a successful launcher result is only an intermediate event. If the
protected-input page is missing, blank, stuck, or cannot be observed, record the
handoff as **BLOCKED** at that earlier checkpoint and diagnose the launch or
navigation failure; do not transfer a broken login flow to the user. This
readiness check never authorizes inspecting or entering the user's protected
input.

Do not use password managers, Keychain, browser autofill, cached credentials,
stored cookies or tokens, one-time codes, recovery methods, or alternate
accounts to cross the gate unless the user explicitly authorizes that exact
method for the current task. Prior permission and general access do not carry
forward. An application that was already authenticated before the task may
continue in that state; if it asks to authenticate or reauthenticate, hand the
gate to the user.

After the user acts, inspect the resulting application state. Reaching or
dismissing the prompt is not proof that authentication or the acceptance flow
succeeded. When acceptance requires subjective visual confirmation, stop at the
ready candidate and ask the user for only that confirmation.

When the owner may be away and the user-level `agent-help` MCP server is
available, call its `request_help` tool once for the blocker. Use the matching
reason (`login_required`, `permission_required`, `decision_required`, or
`blocked`) and only a short non-secret context label. Never include URLs,
domains, credentials, repository content, raw errors, or personal data, and do
not send repeated notifications for the same blocker. Continue only independent
work that cannot change the candidate or bypass the live-proof gate. Resume the
same identified candidate when the user returns; if it changed, mark the receipt
`STALE` and restart the scenario.

Use one proof owner and one running candidate. Scheduled turns and parallel
agents must not restart the app, mutate the worktree, consume the fixture, or
run a competing scenario; keep them read-only or stop them until proof ends.

During iterative development, a changed claim's gate opens only with its current
receipt at `PASS`. Before the first review, every changed externally observable
claim needs current proof. After a review fix or successor edit, the impact map
reopens only affected claims; unaffected receipts remain diagnostic history
until the final campaign. `FAIL`, `BLOCKED`, `STALE`, and `INCONCLUSIVE` keep
their claim gates closed. On failure, record the first divergent checkpoint,
return directly to sections 3-5, and rerun that claim before review continues.

Run `scripts/validate-live-proof.py validate <receipt.json>` before opening a
claim gate. It must recompute that receipt's exact candidate fingerprint and
accept the complete scenario, forbidden-outcome evidence, visual inspection
when required, empty unverified list, and absence of a manual workaround. Copy
the accepted receipt path and result into `live_proof_receipts`, then close the
matching claim todo. The validator's exit code, not the agent's summary, is the
admission decision.

Until the gate passes, describe the state as "candidate ready," "proof in
progress," or the actual failure status. Do not say the feature works, is
verified, or is ready to land.

Each receipt remains exact to its covered runtime candidate. Candidate movement
makes it non-current for a new release verdict. In the iterative loop, that
does not force immediate replay of every unrelated receipt: use the impact map
to reopen affected claims and retain unaffected receipts as diagnostic history.
A later delta may be appended to a receipt without rerunning its live scenario
only when all are true:

- it changes no executable source, runtime configuration, dependency, build
  input, generated runtime asset, or behavior exercised by the scenario;
- the receipt records the delta identity and why it cannot affect runtime;
- the smallest deterministic check confirms the runtime artifact or exercised
  path is unchanged.

Comments outside generated artifacts, documentation, and test-only changes are
typical eligible deltas. "Mechanically equivalent" executable edits are not;
rerun the affected live scenario for those. Any unrecorded or runtime-relevant
delta makes the affected receipt `STALE`.

The final frozen-candidate acceptance campaign is stricter than iterative
replay. Before landing or a release-readiness claim, validate the complete
required receipt set against one exact candidate fingerprint. Re-derive that
set from the acceptance criteria and reconcile it one-to-one with the campaign
receipts before validation. Every required claim is fresh for that candidate,
the aggregate verdict is `PASS`, and no evidence from different fingerprints
is combined to fill the campaign.

Before proof, designate evidence and test-output paths that are not build or
runtime inputs. Creating or cleaning those outputs does not change candidate
identity and needs no per-file covered-delta entry. If an output path can affect
the executable candidate, it cannot use this exclusion.

For a purely internal change fully proven by deterministic tests, the targeted
integration test may be the live gate only when no user, external caller, or
downstream live surface observes the changed runtime behavior. If any
acceptance checkpoint is externally observable, the hard gate above applies.
Do not manufacture an expensive external E2E without added evidence value.

## 7. Risk-gated static review

Invoke `dual-review` after the change works.

Before dispatching, verify every claim affected by the review subject has a
receipt that matches or explicitly covers the reviewed tree. If an affected
runtime claim has no passing receipt, stop: do not reinterpret scripted checks
or an unaffected historical scenario as permission to review. Rerun
`scripts/validate-live-proof.py validate <receipt.json>` for each affected
claim and confirm its `live_proof_receipts` row is `PASS`; a remembered earlier
exit code is not current evidence. Once those claim gates pass, run the
remaining deterministic validation proportionate to the lane, then review.

Give reviewers:

- objective, acceptance criteria, and non-goals;
- selected lane;
- the complete implementation diff, including every new or modified test and
  guard;
- relevant design and check-contract material only;
- targeted test and live-proof results.

Tests and guards are reviewed as part of the same coherent change. Reviewers
must check that tests fail for the intended reason, assertions prove observable
behavior, and guards neither pass vacuously nor reject valid architecture.

Use `dual-review`'s bounded loop:

- round 1: broad discovery;
- round 2: prior-fix verification plus fix delta;
- round 3: unresolved material findings only.

*Compaction point: after applying a round's fixes, compact so the next round's
delta stands clear.*

Fix `must-fix` findings. Use the selective finding verifier for a disputed
candidate only when it could block landing and deterministic investigation
cannot settle it. Do not add a third full-diff reviewer.

### Ensemble escalation

`dual-review` is the default and handles most changes. The `deep` plugin's
`code-review` skill is the heavier alternative: a fixed roster of reviewer
personas over the whole diff, then dedup, opposing advocates, and an
independent judge that filters false positives. Its discovery cost is flat in
diff size, but it is many model calls at high reasoning effort and it reports
its own spend in `COST.md`. Treat it as a deliberate purchase, not a default.

Escalate to it only when the lane is systemic or critical **and** at least one
concrete condition holds:

- the diff could not be split below the reviewable-slice target in section 5,
  so a single reviewer pass cannot hold the whole change in view;
- the change spans multiple independent user flows or state owners that must
  be reasoned about together;
- the critical lane applies to security, authorization, data loss, or a
  fail-closed boundary, where a missed defect is not recoverable after landing;
- `dual-review` round 2 leaves a material finding that neither deterministic
  investigation nor the selective verifier can settle, and it blocks landing.

Diff size alone does not qualify a bounded change. A large mechanical rename
is still bounded.

Escalation does not replace anything. Section 6's live-proof gate stays closed
until it passes on its own terms, and `dual-review` still runs first — the
ensemble reviews the tree that survived it, and its judge-confirmed findings
re-enter this section's normal must-fix gate rather than arriving as a
mandatory work list. The judge rules on whether a finding is accurate, not on
whether it is worth acting on.

When invoking it, pass `WORKTREE`, `BASE`, `HEAD`, and a `RUN` directory under
the project or session — never `/tmp`, which its sub-agent policy rejects. Name
the repository's convention file (`CLAUDE.md`, `AGENTS.md`,
`copilot-instructions.md`, or the local equivalent) in the input you give it:
its reviewer personas check compliance against project guidelines and will
otherwise review against generic defaults. Its reviewer agents register at
session start, so a session that began before the plugin was installed cannot
launch them; start a fresh one rather than falling back to a general-purpose
agent, which runs the wrong prompt.

The review gate passes when no verified, in-scope, material finding remains.
Non-blocking follow-ups may remain.

## 8. Final validation

After review:

- Write a change-to-claim impact map for the review delta before choosing any
  reruns. Candidate movement makes aggregate release readiness `STALE`.
- If review fixes changed runtime behavior, rerun the affected targeted tests
  and claim receipts.
- If review produced only a delta eligible under section 6's receipt-validity
  rule, append it to each affected receipt and rerun the required deterministic
  check.
- If review made a supposedly behavior-preserving executable edit, rerun the
  claims reached by that edit as required by section 6.
- For systemic or critical work, determine rerun scope from the same reach map.
  Replay additional claims only when a named shared dependency or plausible
  regression path reaches them.

After iterative reruns pass, run the complete final acceptance campaign on the
frozen reviewed candidate. Every required claim is fresh under that one
fingerprint; prior receipts from other fingerprints remain history, not
campaign evidence.

For a new user-facing visual journey, invoke `walkthrough-video` now, after the
final reviewed candidate is frozen and before creating or updating its PR.
Rehearse and record the supported journey, fully decode and inspect the movie,
and obtain its hosted PR-media URL. Runtime-relevant movement after recording
makes the walkthrough stale and reopens this step.

If final validation fails, fix the root cause and re-review the **new fix
delta**, not the entire historical diff, unless the fix materially redesigns
the change.

Classify a broad CI failure before editing. Run the smallest equivalent local,
platform, or manual canary against the frozen candidate. When the failure may
be repository health, run the same check on the exact base candidate, or on
current main when the base is unavailable. A candidate-unique failure that
reaches changed behavior reopens the loop. A failure reproduced by the control
is repository-health evidence, not acceptance evidence for this change; record
the comparison and keep it outside the fix.

When evidence points to an intermittent failure, rerun only the failed jobs on
the same candidate. Do not start the complete workflow again and do not push a
successor merely to obtain another attempt. Record the rerun URL and outcome.
A successful same-candidate rerun is explicit intermittent evidence for the
original failure. If the same failure repeats under the same conditions, it
remains unclassified until focused reproduction or a named control run ties it
to the candidate or repository health. Apply section 5's candidate-change rule
when classification proves a candidate defect.

Classification is complete when every red broad check is tied to the candidate,
a named control run, or a named successful rerun of the same failed job on the
same candidate.

## 9. Land

Before landing:

- relevant tests/build/type/lint checks are green;
- the required receipt validators have just accepted every claim in the final
  frozen-candidate campaign for the exact tree being landed, and every matching
  durable proof row and todo is `PASS` and closed;
- dual review has no `must-fix` finding;
- the diff still matches the objective and non-goals;
- test artifacts are cleaned up.
- a PR for a new user-facing visual journey has a reachable movie in its
  `## Walkthrough` section, bound to the demonstrated candidate; a UI fix has
  its required before/after screenshots instead.

Apply the same validator, durable-row, and closed-todo gate before
`task_complete` or any final statement that the runtime change works, even
when the task has no commit or PR.

For a PR, inspect Copilot PR review comments and pass them through the same
scope/risk gate. A substantive verified must-fix comment reopens review of that
fix delta. A non-blocking, hypothetical, or adjacent comment does not restart
the full development loop.

Commit and merge according to repository policy.

*Compaction point: compact before starting the next change or run. Stay in this
conversation — the commit records what shipped, but only the conversation can
answer why, and the user may want to interrogate it.*

## Lane summaries

### Bounded bug or feature

1. Establish the failure, then define acceptance/non-goals.
2. Add a focused regression test.
3. Implement the smallest existing-pattern fix.
4. Run only targeted validation needed to produce a runnable candidate.
5. Pass the section 6 live-proof gate when it applies.
6. Run remaining deterministic validation, then risk-gated dual review.
7. Rerun validation and live proof affected by review fixes.
8. Land.

### Systemic change

1. Arrive with a reviewed design document from `design-doc`; read its lane.
2. Implement its check contract and run only enough targeted validation to
   produce a runnable candidate.
3. Pass the section 6 live-proof gate.
4. Run the broader suite, then risk-gated dual review of implementation, tests,
   and guards together.
5. Final real E2E.
6. Land.

### Critical change

Use the systemic lane plus the relevant specialist review, and the rollback
path and fail-closed evidence the design document carries. Security specialist
findings use the same evidence/scope process but critical
security/auth/data-integrity risks remain must-fix even when reproduction is
difficult. Where a missed defect is unrecoverable after landing, escalate
section 7 to ensemble review.

## Context hygiene

At every **Compaction point** marked above, invoke `self-compact`, except the
first implementation handoff for a long or unattended run. Until that run has a
confirmed live re-brief, invoke `unattended-run` instead and let it own the
reset. Once its schedule is live, later compaction points use `self-compact`
normally. Naming the skill is the instruction; a general intention to compact
is not one, and is why agents arrive at review with a context full of resolved
work.

Every unattended re-brief also reruns the critical-path audit. It reconciles
the remaining dependency graph, delegated ownership, current waits, candidate
batching, and proof replay scope against this skill rather than merely
confirming that a charter still exists.

The baton this loop hands forward is the plan path, lane, objective, acceptance
criteria, non-goals, remaining Definition-of-Done items, branch, what has
landed versus what remains, the change-to-claim impact map, and each live-proof
receipt path, status, candidate identity, running identity, first divergence,
unverified criteria, and covered post-proof deltas. For systemic and critical
work, it also carries the
constraint-provenance location, open revisit conditions, and current reframe
status; persist any `OPEN` reframe record before compacting. Use the existing
committed repo plan/design for systemic or critical work, and an existing
issue, handoff, or named session artifact for bounded work. The summary points
to this durable record; it does not recreate its evidence. When you are still
stuck after a compact, `rubber-duck` before trying more variations.

## Rabbit-hole stop rules

Stop and re-scope when any occurs:

- the design's reframe gate or a recorded constraint revisit condition fires;
- reviewers are finding adjacent issues rather than regressions caused by the
  diff;
- a proposed fix adds a new subsystem, state owner, or generalized framework
  not required by acceptance criteria;
- round 2 resolves prior material findings and leaves only medium,
  hypothetical, or follow-up items;
- round 3 introduces a new defect class unrelated to the fix delta;
- review effort exceeds implementation effort without identifying a new
  must-fix risk;
- the same behavior is being encoded in a functional test, architecture guard,
  design invariant, and E2E without each layer adding distinct evidence.

At that point, land if the material gate is clear, record important follow-ups,
or send any remaining `must-fix` risk through `dual-review`'s autonomous
completion ladder. Escalate only when that skill's explicit effort, authority,
or irreversibility threshold is reached. Do not continue merely to obtain a
literal `findings: []`.

## Pitfalls

- **One process for every change.** Heavy ceremony on bounded bugs increases
  delay and often expands scope.
- **Reviewing guards to zero.** Tests and guards can always be made more
  exhaustive. Review them for material contract gaps, not perfection.
- **Hostile prompts that demand findings.** Telling a model that zero findings
  is failure drives confabulation and obscure edge-case hunting.
- **From-scratch review every round.** Re-review the fix delta and prior
  findings; broad rediscovery belongs to round 1.
- **All comments treated as blockers.** Explicitly separate must-fix,
  verification-needed, follow-up, and dropped findings.
- **Third full reviewer.** Use a cheap finding verifier only for disputed
  blockers.
- **Ensemble review as the default.** Buying the heavy roster for a bounded
  change spends real credits to rediscover what one reviewer already covers,
  and a long judged findings list invites exactly the adjacent-issue expansion
  the stop rules exist to prevent.
- **Permanent guard proliferation.** A focused regression test is often enough.
- **Harness green mistaken for product green.** Scripted checks, mocked E2Es,
  helper messages, and successful source reads do not prove the visible flow.
- **Successful invocation mistaken for runtime effect.** A returned success
  value does not prove that a WebView, OS API, callback, protocol, or service
  changed the observed state. Probe the uncertain mechanism before building
  retry, timeout, ownership, or abstraction machinery around it.
- **Worktree activity mistaken for agent activity.** File changes show artifact
  state, not whether an assigned agent is active, idle, blocked, failed, or
  complete. Read the agent's explicit result or handoff first, then inspect the
  artifact it delivered. When no current result exists, report `unknown` and
  request status rather than guessing. Never prolong a completed assignment
  because its worktree is dirty or changing.
- **Partial proof promoted to pass.** Reproducing the failure, reaching login,
  or proving one downstream result cannot open the review gate when another
  acceptance checkpoint is broken or unseen.
- **Review started before proof.** Section 6's gate is closed while runtime
  behavior remains unproven; debugging and review/PR mechanics are separate
  phases.
- **Stale or competing live candidates.** A process without tree identity, or
  one restarted by another worker, cannot produce an admissible proof.
- **Duplicate E2E runs without causal value.** Use the change-to-claim impact
  map to reopen reached claims. A lane label, unrelated candidate movement, or
  a new commit hash is not by itself a reason to replay every receipt.
- **Using the full CI matrix as an iterative debugger.** Repeated successor
  pushes discard partial evidence, cancel expensive work, and mix unrelated
  failures into the next attempt. Follow section 5's final-candidate freeze and
  successor rule.

## Verification

The change is complete when:

1. its lane matches its demonstrated risk, and systemic or critical work has a
   reviewed design document carrying that lane;
2. objective, acceptance criteria, and non-goals are explicit;
3. the durable contract is proportional to the lane;
4. functional behavior is tested;
5. required live behavior has a complete final receipt set that the validator
   accepted against one exact reviewed-tree fingerprint, with every durable
   proof row and todo closed only after validation;
6. dual review has no verified in-scope must-fix finding;
7. post-review validation covers the actual review fixes;
8. the landed diff remains coherent and scoped; and
9. the critical-path audit ran at each required trigger, and no remaining
   ready scope is unowned, overlapping, or serial without a named gate; and
10. every PR that adds a new user-facing visual journey contains its validated
    candidate-bound walkthrough movie, while fixes retain their required
    screenshot evidence.

Changes to the mechanism-probe rule also pass the behavioral fixture in
[`references/mechanism-probe-fixture.md`](./references/mechanism-probe-fixture.md).
