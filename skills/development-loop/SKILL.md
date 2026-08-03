---
name: development-loop
description: Develop and ship one non-trivial code change through a risk-sized loop — establish the failure, triage the blast radius, prove runtime behavior, review, and land. Use for bug fixes, features, refactors, app or service changes, agent workflows, pipelines, and SDK changes. When triage finds shared state, persistence, public contracts, cross-component architecture, security, or fail-closed boundaries, invoke `design-doc` before coding.
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
> implementation review, broad CI, full lint, PR creation or update, or landing
> work until the complete acceptance flow has passed in the live app or service
> on the current tree.

Targeted tests, type checks, and builds needed to make the live candidate
runnable may happen first. They are development diagnostics, not acceptance
evidence. The conditional pre-build guard review in section 4 is the only
implementation-review exception; it reviews a guard that constrains the work,
not an implementation claimed to work.

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
it.

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

For runtime work, turn the acceptance criteria into a short live scenario now.
Name the trigger, each user-visible checkpoint, the terminal success state, and
the errors or regressions that must be absent. A later partial success cannot
silently become the proof contract.

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
document. Implement what it specifies. A design that turns out to be wrong goes
back to `design-doc`; do not reopen scope or architecture here.

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

Branch from current main and implement one behavior at a time.

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
gate. Run the complete acceptance flow in the real app or service before
implementation review, broad CI, full lint, PR creation or update, or landing
work. Do not dispatch those tasks in parallel with an active live proof: a
failed proof invalidates the premise of their work and wastes time.

Before starting, record a compact **live-proof receipt** using
[`references/live-proof-receipt.md`](./references/live-proof-receipt.md):

- candidate identity: a clean commit, or a full candidate identity that covers
  tracked changes plus every untracked file that can affect the build or
  runtime; branch plus commit alone is valid only for a clean worktree;
- running identity: process/build identity that proves the app or service was
  started from that candidate, not a stale installation or another agent's
  build;
- scenario: the exact trigger, required checkpoints, terminal success state,
  and forbidden errors from the acceptance criteria;
- evidence source: what the agent can inspect directly and what requires a
  human action or confirmation.

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

Confirm every checkpoint and the observable end state, not merely a harness
exit code, scripted test result, log line, or helper self-report. Inspect the
actual app/service state out-of-band. Any unexplained user-visible error,
missing window, manual workaround, stale data, failed retry, race, or unverified
acceptance criterion makes the result **FAIL**, not "partial pass."

When credentials, MFA, JIT approval, or subjective visual confirmation requires
the user, stop at the ready live candidate and ask for only that action. Do not
claim success from reaching the prompt. After the user acts, inspect the
terminal app state and record their confirmation where direct automation cannot
observe it.

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

The gate opens only with a receipt whose result is `PASS` and whose evidence
covers every acceptance criterion. `FAIL`, `BLOCKED`, `STALE`, and
`INCONCLUSIVE` all keep the gate closed. On failure, record the first divergent
checkpoint, return directly to sections 3-5, and rerun this gate before any
review or PR work.

Until the gate passes, describe the state as "candidate ready," "proof in
progress," or the actual failure status. Do not say the feature works, is
verified, or is ready to land.

The receipt remains valid only while its covered runtime candidate is
unchanged. A later delta may be appended without rerunning the live scenario
only when all are true:

- it changes no executable source, runtime configuration, dependency, build
  input, generated runtime asset, or behavior exercised by the scenario;
- the receipt records the delta identity and why it cannot affect runtime;
- the smallest deterministic check confirms the runtime artifact or exercised
  path is unchanged.

Comments outside generated artifacts, documentation, and test-only changes are
typical eligible deltas. "Mechanically equivalent" executable edits are not;
rerun the affected live scenario for those. Any unrecorded or runtime-relevant
delta makes the receipt `STALE`.

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

Before dispatching, verify the live-proof receipt is present and still matches
or explicitly covers the reviewed tree. If runtime work has no passing receipt,
stop: do not
reinterpret scripted checks or a partial scenario as permission to review. Once
the gate passes, run the remaining deterministic validation proportionate to
the lane, then review.

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

- If review fixes changed runtime behavior, rerun the affected targeted tests
  and live scenario.
- If review produced only a delta eligible under section 6's receipt-validity
  rule, append it to the receipt and rerun the required deterministic check.
- If review made a supposedly behavior-preserving executable edit, rerun the
  affected live scenario as required by section 6.
- Systemic/critical changes always rerun their final live E2E on the reviewed
  tree.

If final validation fails, fix the root cause and re-review the **new fix
delta**, not the entire historical diff, unless the fix materially redesigns
the change.

## 9. Land

Before landing:

- relevant tests/build/type/lint checks are green;
- required live-proof receipt is `PASS` and matches or explicitly covers the
  exact tree being landed under section 6's receipt-validity rule;
- dual review has no `must-fix` finding;
- the diff still matches the objective and non-goals;
- test artifacts are cleaned up.

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

The baton this loop hands forward is the plan path, lane, objective, acceptance
criteria, non-goals, remaining Definition-of-Done items, branch, what has
landed versus what remains, and the live-proof receipt path, status, candidate
identity, running identity, first divergence, unverified criteria, and covered
post-proof deltas. Persist it before compacting: use the existing committed
repo plan/design for systemic or critical work, and an existing issue, handoff,
or named session artifact for bounded work. The summary points to this durable
record; it does not recreate its evidence. When you are still stuck after a
compact, `rubber-duck` before trying more variations.

## Rabbit-hole stop rules

Stop and re-scope when any occurs:

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
- **Partial proof promoted to pass.** Reproducing the failure, reaching login,
  or proving one downstream result cannot open the review gate when another
  acceptance checkpoint is broken or unseen.
- **Review started before proof.** Section 6's gate is closed while runtime
  behavior remains unproven; debugging and review/PR mechanics are separate
  phases.
- **Stale or competing live candidates.** A process without tree identity, or
  one restarted by another worker, cannot produce an admissible proof.
- **Duplicate E2E runs without causal value.** Rerun expensive live proof when
  section 6's receipt-validity rule requires it, not because unrelated
  evidence-output churn restarts the scenario.

## Verification

The change is complete when:

1. its lane matches its demonstrated risk, and systemic or critical work has a
   reviewed design document carrying that lane;
2. objective, acceptance criteria, and non-goals are explicit;
3. the durable contract is proportional to the lane;
4. functional behavior is tested;
5. required live behavior has a passing receipt that matches or explicitly
   covers the exact reviewed tree under section 6's receipt-validity rule;
6. dual review has no verified in-scope must-fix finding;
7. post-review validation covers the actual review fixes;
8. the landed diff remains coherent and scoped.
