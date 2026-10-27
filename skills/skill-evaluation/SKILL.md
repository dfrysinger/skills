---
name: skill-evaluation
description: Build and run frozen behavioral evaluation corpora for any agent skill. Use when regression-testing a skill against historical or synthetic cases, adding transcript-derived cases, checking that general prompt language handles new evidence, comparing a revised skill against unchanged or no-skill controls, or qualifying a released skill for generalization.
---

# skill-evaluation

Use a **frozen case** to separate evidence from the answer the skill is expected
to reach. The target skill may be any installed or development skill; this
procedure does not encode its output shape or domain.

For a multi-task corpus, the goal is to refine and ship one shared skill or
coherent set of skills that solves every evaluation task. Carry each proven
general improvement into the next shared revision and ship it when its own
product, regression, and transfer gates pass; do not wait for the whole corpus
to turn green. Measure progress on the same exact released revision, not a
pooled count of passes from different experiments. Follow the
[`cumulative skill hill climb`](references/cumulative-skill-hill-climb.md)
for the complete process.

## Keep evaluation proof proportional

Default to the smallest evaluation that can answer the user's question.
Ordinary skill tuning does not require a hostile-party or independently
verifiable experiment.

Candidate agents running in separate cloud VMs cannot inspect the coordinator's
local files unless the prompt, tools, mounted workspace, or supplied evidence
gives them access. Protect hidden criteria from those real exposure paths. Do
not assume the candidate will attack the evaluator, rewrite local evidence, or
collude with the test operator.

For normal tuning, use frozen fixtures, development and held-out cases,
first-result records, and ordinary file hashes or Git history. Record
evaluator-controlled selection and other practical limits honestly. Those
limits do not by themselves require independently administered storage,
cryptographic commitments, random-selection services, external attestations,
new platform capabilities, privacy or legal review, or cross-team approval.
Name the exact candidate identity in the evaluation plan and result. For a Git
candidate, record the commit and the target-skill file hashes rather than
describing the bytes only as current, exact, or unchanged.

Invoke `constraint-challenge` before a material experimental-design change that
adds or retains a new service, external authority, independent proof owner,
capture population, selection or randomization mechanism, immutability system,
or adversarial threat assumption. Ask whether the addition improves the
behavioral evidence or only prevents the test operator from manipulating its
own experiment. A routine fixture correction, extra case, judge repair, or
predeclared repetition does not need this gate.

Use `constraint-challenge` as the internal scope gate rather than adding a
second skill-specific necessity test. Give it the exact user outcome,
candidate boundary, proposed addition, claimed failure without it, and simplest
known alternative. Only `CONTINUE` approves that exact expansion. `NARROW`,
`REFRAME`, or `UNKNOWN` means continue without the disputed addition. If this
gate is too lax, improve `constraint-challenge` and rerun it instead of adding
custom constraints here. Its decision approves internal design scope only; it
cannot grant credentials, legal authority, or permission to represent the user
externally.

A material trigger is not serviced until the `constraint-challenge` skill call
completes successfully. Do not imitate its verdict format or issue
`CONTINUE`, `NARROW`, `REFRAME`, or `UNKNOWN` yourself. If the call is
unavailable or incomplete, treat the disputed addition as `UNKNOWN`, omit it,
and continue the simpler supported evaluation.

Use stronger infrastructure only when an actual reachable threat, external
obligation, publication claim, or explicit user instruction requires it.
Instructions such as "make it robust," "make it generalizable," "keep going,"
"work in parallel," or "do not be cost conscious" do not request adversarial or
independently administered proof.

External actions follow `development-loop`'s cross-project representation
boundary. Neither this process nor `constraint-challenge` grants that authority.
Without an existing user grant, draft optional outreach and continue the local
evaluation.

## Local evaluation dashboard

Declare a project in each participating corpus with
`evaluation-project.json`. The declaration uses one stable project ID, lists
each task, and binds every frozen case to one task and exact case revision.
Multiple corpora join only when they declare the same compatible project.

```json
{
  "schema_version": 1,
  "supersedes": null,
  "project_id": "example-skill-improvement",
  "title": "Improve example-skill",
  "goal": "Pass the declared behavior checks on one exact skill revision.",
  "target_skills": ["example-skill"],
  "tasks": [{
    "task_id": "example-behavior",
    "title": "Handle the example behavior",
    "summary": "Produce the required behavior without breaking regression cases.",
    "qualification": {
      "kind": "all_bound_cases",
      "required_roles": ["development", "regression"],
      "minimum_terminal_repetitions_per_case": 1,
      "required_passes_per_case": 1
    }
  }],
  "case_bindings": [{
    "binding_id": "example-case-development",
    "case_id": "example-case",
    "case_revision": "<case-manifest-sha256>",
    "task_id": "example-behavior",
    "role": "development",
    "safe_progress": {
      "kind": "repository_checks",
      "checks": ["regression", "target"]
    }
  }],
  "holdout_requirements": []
}
```

Use `kind: "exact_experiment_population"` when a task's qualification must be
decided by one pre-registered finite distributed treatment population rather
than cumulative matching evaluator history:

```json
{
  "kind": "exact_experiment_population",
  "required_roles": ["development"],
  "experiment_id": "fixed-population-v1",
  "experiment_fingerprint": "<experiment-plan-sha256>",
  "treatment_id": "candidate",
  "required_passes_per_case": 3
}
```

The experiment declaration owns the exact attempt IDs, cases, revisions,
treatments, repetitions, model, platform, and route. The task remains
unavailable until every attempt in the named treatment has one valid immutable
terminal result on the selected skill revision. Missing, duplicate,
conflicting, mismatched, or nonterminal evidence fails closed. Results from
another experiment, including later rescue attempts, never change this
qualification. Use `all_bound_cases` for cumulative qualification.

Publish an additive revision by setting `supersedes` to the exact fingerprint
of the current declaration. Keep all existing task, binding, and holdout IDs.
Registration archives each accepted declaration so older runs retain their
original meaning.

For `distributed_product_stages`, each declared check is an exact
`stage_kind` from the bound distributed dispatch plan. It counts as complete
only after a validated non-failing stage receipt exists; unknown stage names
make the safe breakdown unavailable instead of displaying a fabricated zero.

Register this Copilot session once using its exact session UUID. The dashboard
opens the project at most once for the current service process. Later sessions,
retries, and runs update the same page without opening another tab.
The project is the only auto-opened page. Runs remain compact rows underneath
the tasks they support; retries, treatments, repetitions, and canaries never
open standalone pages.

Run dashboard registration and browser lifecycle commands through the current
installed `skill-evaluation` skill. Do not use a copy embedded in a candidate
plugin, run snapshot, or frozen experiment bundle. Those copies are evidence
for the evaluator that produced them, but an older dashboard client can open
one legacy page per corpus instead of joining the current project page. The
dashboard service rejects the obsolete campaign-open protocol so stale clients
fail before opening a browser tab. A frozen evaluator may still publish attempt
events during `run` or `run-suite`; the installed client owns registration,
project opening, status, and stop.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard register CORPUS \
  --session-id SESSION_UUID
```

Registration into an explicit `--state-root` is noninteractive: it records the
session without starting a service or opening a browser. Use `--open` only when
that private state root is intentionally being inspected by a person.

Use the explicit commands to reopen a project, list projects, or inspect
legacy corpora that do not declare a project:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard open-project PROJECT_ID
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard projects
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard unassigned
```

The browser keeps its scoped read capability in tab-only `sessionStorage`, so
refresh works without putting authority in a query string, cookie, or
persistent browser storage. A project capability cannot read another project
or the unassigned legacy view.

Publish a short non-final assignment event when work starts, blocks, or
completes. Use the frozen case ID; the command resolves its exact revision.
Refresh the heartbeat during long work that has no assignment transition.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard event CORPUS \
  --session-id SESSION_UUID --event-type assignment_started \
  --case CASE_ID --summary "Running the baseline attempt"
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard heartbeat CORPUS \
  --session-id SESSION_UUID --state active
```

The evaluator publishes its own planned, started, and artifact-available
attempt events when the corpus is registered. These live records are
non-final: immutable evaluator artifacts always supersede them.

Capture an immutable snapshot when a campaign skill reaches a meaningful
lineage state. Name every target skill represented by the snapshot. Roles are
workflow declarations except `passing`, which only the evaluator can derive.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard lineage-snapshot CORPUS \
  --session-id SESSION_UUID \
  --plugin-dir /path/to/plugin \
  --skill TARGET_SKILL \
  --role integrated \
  --parent derived_from PARENT_SNAPSHOT_ID \
  --summary "Integrated the general fix"
```

Publish task progress against the exact frozen case revision and associated
snapshot. Progress explains the current frontier, movement, blockers, and
instruction uptake; it does not change evaluator correctness. A project task
may record only the work intent phases `experimenting`, `delta_ablation`, or
`regression_check`. Qualification, holdout validation, publication readiness,
and publication come from evaluator, holdout, or lineage evidence.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard task-progress CORPUS \
  --session-id SESSION_UUID \
  --case CASE_ID \
  --snapshot SNAPSHOT_ID \
  --comparison-snapshot PARENT_SNAPSHOT_ID \
  --frontier behavioral \
  --classification skill_defect \
  --movement "Strict improvement" \
  --phase experimenting \
  --summary "The remaining failure is isolated to behavioral review" \
  --uptake preserve-authority OBSERVED "The candidate preserved authority" \
  --blocker "One behavioral criterion still fails" \
  --next-action "Refine the general rule" \
  --source review_receipt REVIEW_ID
```

For aggregate holdout validation, create one owner-protected Ed25519 authority,
then import its signed started and terminal receipts. Receipts bind the exact
project, holdout set, candidate revision, task set, claim, and lifetime. They
contain aggregate counts and accounting only. Case identities, prompts,
criteria, outputs, private paths, and per-case failures are rejected.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard holdout-authority \
  --authority-id independent-evaluator \
  --public-key BASE64_ED25519_PUBLIC_KEY

python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard holdout-private-sign \
  --private-key /protected/private-key \
  --unsigned-receipt /protected/aggregate-receipt.json \
  --output /protected/signed-receipt.json

python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard holdout-import \
  /protected/signed-receipt.json
```

For a distributed treatment experiment, publish each bounded projection only
through its event-specific adapter. The adapters validate and correlate the
declaration, immutable dispatch binding, exact-known-jobs observer output,
package, plan, retained receipt, retained artifact, and retention manifest.
Only dashboard-safe projections are stored; private repository, workflow, run,
branch, URL, artifact path, log, and credential fields are not persisted.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard experiment-declaration CORPUS \
  /path/to/declaration.json \
  --session-id SESSION_UUID

python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard experiment-dispatch CORPUS \
  /path/to/plan.json /path/to/private-run.json /path/to/dispatch-binding.json \
  --experiment-id EXPERIMENT_ID \
  --opaque-source-id SAFE_SOURCE_ID \
  --writer-id COORDINATOR_ID \
  --writer-generation GENERATION

python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard experiment-observation CORPUS \
  /path/to/observation.json /path/to/plan.json \
  /path/to/private-run.json /path/to/dispatch-binding.json \
  --experiment-id EXPERIMENT_ID \
  --opaque-source-id SAFE_SOURCE_ID \
  --writer-id OBSERVER_ID \
  --writer-generation GENERATION
```

Use a session writer for the immutable declaration, a distributed coordinator
for dispatch, stage, and result records, and a cloud observer for one complete
exact-known-jobs snapshot. Generate the private dispatch binding with
`distributed_campaign.py bind-dispatch`; observe only its complete expected
job set with `observe_campaign_runs.py --direct-known-jobs`.

Publish a checksum-bound nonterminal stage or terminal result from its retained
owner artifacts. The stage kind is derived from the validated receipt and plan,
not supplied by the caller.

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard experiment-stage CORPUS \
  /path/to/package /path/to/plan.json /path/to/stage-receipt.json \
  /path/to/retained-artifact.tar.gz /path/to/retention-manifest.json \
  --experiment-id EXPERIMENT_ID \
  --attempt-id ATTEMPT_ID \
  --writer-id COORDINATOR_ID \
  --writer-generation GENERATION

python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard experiment-result CORPUS \
  /path/to/package /path/to/plan.json /path/to/result-receipt.json \
  /path/to/retained-artifact.tar.gz /path/to/retention-manifest.json \
  --experiment-id EXPERIMENT_ID \
  --attempt-id ATTEMPT_ID \
  --writer-id COORDINATOR_ID \
  --writer-generation GENERATION
```

The retention manifest is schema version 1 and contains exactly
`receipt_sha256`, `artifact_sha256`, and a nonempty `source_ids` list in
addition to `schema_version`. The dashboard retains safe identities, bounded
status and evidence summaries, coverage, accounting observations, and opaque
source IDs, not private transport fields or artifact paths.

After every required terminal result is admitted, run deterministic selection:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard experiment-selection CORPUS \
  --declaration-event DECLARATION_EVENT_ID \
  --writer-id EXPERIMENT_EVALUATOR_ID \
  --writer-generation GENERATION
```

The evaluator discovers every admitted result for the declaration and
recomputes eligibility, metrics, disqualifiers, ties, and the selected or
no-selection result. Missing or duplicate attempt results return
`selection_incomplete` and write no terminal selection. A later conflicting or
additional result invalidates an older terminal selection at read time.

For per-task minimization, use the same experiment declaration and result
authority with `experiment_kind: "delta_ablation"`. Its `ablation` object binds
the exact project declaration, newly conquered task, published baseline,
exploratory passing snapshot, treatment-to-candidate snapshot map, maintained
task fingerprints, and removed, retained, or restored instruction identities.
A restored instruction requires a plain-language reason. Every candidate
snapshot must descend from the exploratory pass. The dashboard derives bytes,
text lines, and file counts from the captured snapshots and calls a selected
candidate final only when every maintained task meets its declared
qualification rule.

Use `experiment_kind: "whole_skill_ablation"` only when the workflow explicitly
starts the separate neutral, lean, and full comparison. Its `ablation` object
maps declared arms to treatments and exact snapshots and binds the maintained
task set. Missing arms remain absent. Without this declaration, the project
page does not show a whole-skill ablation section.

Bind an evaluator run to the snapshot whose bytes it is meant to exercise:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run-suite CORPUS \
  --plugin-dir /path/to/plugin \
  --dashboard-snapshot SNAPSHOT_ID \
  --run-goal "Check whether the current revision passes every declared task"
```

The evaluator pins the plugin first and refuses the run before model execution
if the pinned target-skill identities do not match the snapshot. Campaign-level
passing requires one bound full-corpus suite on one exact snapshot, plugin
identity, case-revision set, and evaluation contract. Separate cases, suites,
or revisions never pool into passing.

Project-aware `run` and `run-suite` commands require a plain-language
`--run-goal`. They write startup and renewable lease artifacts before risky
setup, then use immutable result or typed failure artifacts as terminal
authority. An expired run without a terminal artifact appears as
`liveness_lost`; it is not labeled interrupted unless an explicit interruption
artifact exists.

Manual lifecycle commands remain available:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard ensure CORPUS
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard open CORPUS
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard status
python3 "$SKILL_DIR/scripts/skill_eval.py" dashboard stop
```

The project page shows each task result and work phase separately. It shows
safe named checks only when the declaration selects a supported reader. It also
shows time to the first qualified pass, covered run and attempt counts,
infrastructure failures, tokens, credits, compact local and distributed runs,
and authenticated aggregate holdout status. Unknown and partial accounting
stay labeled as unknown or partial. AI credits are interpreted as cents by user
convention; premium requests remain a separate evaluator unit. Distributed
cost without canonical accounting remains incomplete. Delta-ablation size and
maintained-win status remain unavailable until the exact declaration,
snapshots, terminal results, and selection are admitted.

## 1. Define the behavioral claim

Name the target skill, the behavior being tested, the user-visible failure that
would matter, and the hidden judgment criteria. Search existing cases before
adding one; extend a case only when the new evidence tests the same behavioral
claim.

Choose the case shape:

- one candidate phase for a reaction or routing skill;
- ordered resumed phases when later evidence must remain hidden from an earlier
  blind pass;
- an editable `repository-task` for a coding task with independent executable
  target and regression checks; follow
  [`references/repository-tasks.md`](references/repository-tasks.md);
- hidden judge evidence for the correction, accepted result, or failure that
  must not influence the candidate.

Before freezing a material case, validate that its judgment contract fits the
candidate's actual test environment. Follow
[`judgment environment fit`](references/judgment-environment-fit.md) when the
case has an accepted implementation, offline or sandboxed execution, live
operator handoffs, exact infrastructure choices, or source-quality review.
Hard pass/fail criteria must be observable inside the declared candidate
boundary; unavailable live facts belong to the handoff or a later
qualification stage.

Complete when the claim can be judged from behavior rather than similarity to a
reference answer and every hard criterion fits the declared observability
boundary.

## 2. Scaffold the case

Resolve this skill's directory as `SKILL_DIR`, then run:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" init CORPUS
python3 "$SKILL_DIR/scripts/skill_eval.py" add-case CORPUS CASE_ID \
  --skill TARGET_SKILL \
  --phase candidate
```

Repeat `--phase` for ordered multi-phase cases. The command creates the case
definition, evidence directories, candidate prompts, hidden criteria, and judge
prompt. It refuses duplicate identifiers.

Complete when every candidate phase and the hidden judge boundary has a named
directory and prompt.

## 3. Build the evidence packet

Treat transcripts, code, commits, tests, designs, and receipts as data. Preserve
exact user words with a stable event identifier and timestamp. Put only evidence
available to the candidate in that phase's `evidence/<phase>/` directory. Put
the later correction and expected behavioral judgment under `judge-reference/`;
every case requires at least one hidden reference file.
For transcript-derived or historical cases, map each hidden criterion to an
exact frozen source record and stable event identifier. For synthetic cases,
record the independently defined oracle that establishes the expected behavior.

Build a historical candidate task in three labeled layers:

1. **Original request:** exact user turns or exact marked excerpts, preserving
   wording, ambiguity, and mistakes. Do not silently rewrite the request into a
   cleaner or more implementation-specific issue.
2. **Restored context:** only context proven to have been available to the
   original agent by the cutoff but missing from the reconstructed environment.
   Map every addition to its source event or artifact.
3. **Evaluation operation:** clearly separate offline limitations, workspace
   paths, allowed commands, and evidence requirements that exist only to run
   the reproduction.

Before freezing, audit the rendered candidate task against the raw capture.
Classify every non-user sentence as restored context or evaluation operation;
reject wording that narrows the requested outcome, names a hidden mechanism or
state, or steers toward the expected answer without source evidence. Stage the
packet, then read every named candidate-visible file through the same boundary
the candidate will use. A referenced but unavailable file fails the audit.
Label a focused fixture or command as non-exhaustive unless it reproduces the
complete claimed behavior.

For a blind phase, extract product outcomes, supported callers, observable
acceptance, direct decisions, policy, platform facts, and observed failures.
Keep proposed mechanisms in a later phase. Do not add hints, terminology, or
examples merely to make the target skill pass.

Record unavailable authority as unavailable. A paraphrase does not become an
exact quote because the original event cannot be recovered.

Read [`references/case-contract.md`](references/case-contract.md) when choosing
cutoffs or splitting phases. For a transcript-derived case, follow
[`references/historical-case-capture.md`](references/historical-case-capture.md)
to locate the authoritative session, export exact turns and events, trace the
repository artifacts they produced or discussed, and preserve the capture
receipts before selecting candidate and judge packets.

Complete when the candidate task passes the text-packet audit, a candidate
cannot read the expected answer, every named candidate-visible file is
readable through the staged boundary, and a judge can trace every required
behavior to frozen evidence. For a material case, completion also requires the
environment-fit criteria ledger and its applicable challenge/review gate.

## 4. Freeze and verify

Run:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" freeze CORPUS --case CASE_ID
python3 "$SKILL_DIR/scripts/skill_eval.py" verify CORPUS --case CASE_ID
```

Freezing copies exact bytes into an immutable
`frozen/<case>/revisions/<root-digest>/`, writes one manifest per phase, and
writes a per-case root manifest. `current.json` atomically selects the newest
revision. The root binds only that case, so adding another case does not
invalidate old receipts. `--replace` publishes a new revision without deleting
prior frozen bytes or invalidating their receipts.

Complete when every frozen byte matches its manifest and no source path escapes
the case directory.

## 5. Run the target skill unchanged

Run against an installed or development plugin:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run CORPUS \
  --case CASE_ID \
  --plugin-dir /path/to/plugin
```

After changing a skill with a maintained regression corpus, run every frozen
case together:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run-suite CORPUS \
  --plugin-dir /path/to/plugin
```

Use `--case CASE_ID` repeatedly for a deliberate subset and `--workers N` to
bound concurrent cases. Treat a subset as focused iteration, never as the
release regression gate. For stochastic model or judge variance, use
`--max-attempts N` to retry only cases that did not reach unanimous `PASS`;
every attempt remains preserved and the report identifies cases that passed
after retry. The suite command writes one aggregate report while preserving
each case's independent run, receipts, and judgments.

For a corpus-wide improvement, begin with the published skill or skill set,
inventory existing experimental passes, and consolidate eligible general
lessons through the cumulative hill climb before new searches. Branch every new
task and experiment from the latest integrated draft. Older, neutral, and lean skills are comparison controls,
not independent starting points for a new task.

When a valid evaluator exists and more than one credible mechanism could
improve stochastic skill behavior, follow
[`references/parallel-treatment-search.md`](references/parallel-treatment-search.md).
Build a frozen population of source-backed, single-mechanism treatments with
controls and pre-registered repetitions before editing a preferred candidate.

Use the local suite runner for ordinary corpora. When the corpus contains full
repositories, native builds, product exercises, multiple treatments, or enough
observations that one host would become the bottleneck, follow
[`references/large-actions-campaign.md`](references/large-actions-campaign.md).
Choose execution, experiment recording, and candidate proposal tools separately.
Adopt or extend one only when a bounded comparison with the current method shows
a concrete benefit in results, feedback time, total cost, or coordination work.
Keep qualification unchanged, record differences in model, tools and environment,
and include integration overhead. A faster launch alone does not prove faster
evaluation; use an approved data destination before sending private evidence.
Use the reusable scripts and workflow template described in
[`references/distributed-campaign-tooling.md`](references/distributed-campaign-tooling.md)
rather than copying a historical campaign repository.
Use the bounded [run observer](references/run-observation.md) for batched
read-only metadata collection when it reduces the measured individual-read
cost. Preserve exact run and attempt bindings; an absent, incomplete or
mismatched observation is not a completed attempt.
The distributed campaign procedure seals one immutable release with separately addressed
candidate and hidden payloads, fans unfinished attempts out through private
GitHub Actions, preserves first model outcomes, resumes only invalid downstream
stages, checksum-verifies retained artifacts, and reconciles one exact
effective-result map. When changing the evaluator itself, prove each changed
stage first with the cheapest representative canary, counting package
construction, upload and download volume, runner time, native builds, model
calls, and judge calls as test cost. Reuse retained upstream evidence instead
of launching a fresh model attempt when only a downstream stage changed.

The runner:

1. verifies the frozen case;
2. snapshots the plugin and runs the exact pinned target-skill files it digests;
3. gives each candidate phase only its allowlisted evidence;
4. resumes the same candidate session across ordered phases;
5. keeps judge evidence in separate sessions;
6. records prompts, raw logs, outputs, model settings, harness and CLI identity,
   command configuration, tool-boundary audit, and receipts; and
7. produces `REPORT.md`.

Required skill loading needs a matching successful tool completion. A denied
call or a start without completion does not prove loading, even if the CLI
exits successfully. When target-skill invocation is forbidden, an attempt is
enough to reject the run, whether or not that call succeeds.

Use `--home-mode isolated` when `COPILOT_GITHUB_TOKEN` is available. The default
`existing` mode uses the current authenticated Copilot home while still
disabling custom instructions and built-in MCP servers; its receipt states that
the authentication home was shared.

Repository tasks require successful `validate-case` admission and caller-supplied
`COPILOT_GITHUB_TOKEN`. They always use an isolated Docker candidate and
isolated judge homes. `--arm baseline` exposes no target plugin; `--arm skill`
invokes the unchanged skill. Their executable score, behavioral verdict, and
first-attempt suite success are reported separately. Candidate timeouts are
scored failures; retries do not improve pass@1.

Frozen workflow comparisons may add a strict direct treatment descriptor:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run CORPUS \
  --case CASE_ID --plugin-dir /path/to/complete/plugin \
  --arm skill --treatment-file /path/to/treatment.json
```

The descriptor records immutable source, adapter, intervention, compatibility,
and entry-skill identity. Its `entry_skill` overrides the case's historical
`target_skill` for candidate invocation without changing the case or plugin
snapshot. Unsupported fields, runner kinds, compatibility predicates, and
incompatible case/treatment pairs fail before model execution.

Before a reportable repository run, execute the same command once with
`--treatment-admission`. Admission attempts are retained under
`treatment-admission-runs/`, excluded from comparison history, and bind the
case, treatment and adapter snapshots, complete plugin snapshot, plugin entry
skill, harness, model, and effort. A later reportable run refuses to start
without the matching successful admission receipt.

The only external candidate runner is the reviewed Sandcastle sequential
reviewer adapter:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run CORPUS \
  --case TYPESCRIPT_CASE --plugin-dir /path/to/plugin \
  --arm skill --model gpt-5.6-sol-fast \
  --sandcastle-treatment-file /path/to/frozen/treatment.json \
  --sandcastle-adapter-dir /path/to/frozen/adapter
```

Its ID, package revision, version, command, model, adapter digest, and
implementer/reviewer subroles are fixed in the evaluator. The evaluator
preallocates both possible session UUIDs. Missing, malformed, duplicate,
wrong-model, or undeclared session evidence remains incomplete and cannot
produce exact candidate credits.

Every attempt records owned usage observations and elapsed timing, including
failed invocations, judgments and cleanup. Clock implementation and sleep
coverage distinguish observed elapsed from verified sleep-inclusive timing.
Missing credits or full-wall coverage remain unknown.
For repository tasks, `--quality-review` adds paid, independent source-only
shipping assessments without changing correctness or retry policy.

Read local results with:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" history CORPUS --format markdown
python3 "$SKILL_DIR/scripts/skill_eval.py" history CORPUS --format json
```

See [`references/measurement.md`](references/measurement.md) for accounting
coverage, resumed-session totals, quality evidence and matched history
populations. Do not interpret a partial subtotal as a final bill or compare
different task revisions as the same experiment.

Complete when the report identifies the exact skill revision, case revision,
candidate outputs, treatment and compatibility identity, and independent
judgments. After a skill change, completion
also requires the maintained full suite to pass when one exists.

## 6. Interpret and improve

Mechanical success means the run completed and its receipts match. Behavioral
success requires unanimous `PASS` from independent Claude and GPT judges
without seeing case-specific language in the skill. Any `FAIL` makes the result
`FAIL`; otherwise any `UNANSWERABLE` makes it `UNANSWERABLE`.

For a suite with bounded retries, each attempt keeps those semantics. The case
passes when one identical-byte attempt reaches unanimous `PASS`; otherwise its
last completed attempt determines the case result. Never discard failed
attempts or describe a retry-assisted pass as deterministic.

For a separately scoped release, declare its repeated-run qualification rule
before dispatch. Report qualification separately from each original outcome,
instruction uptake, and causal or generalization claims. Retain every failure;
do not change the threshold after seeing results or call a qualified artifact
deterministic. This is distinct from the suite runner's retry-until-one-`PASS`
policy and does not alter any attempt's verdict.

For an experiment that changes a skill, compare two layers separately:

1. **Instruction uptake:** for each changed rule that applies to the case,
   record `OBSERVED`, `PARTIAL`, `ABSENT`, or `NOT_APPLICABLE`, citing candidate
   actions or artifacts. This shows whether the skill changed the agent's
   process even when the case remains red.
2. **Product movement:** compare executable gates, recurrence of the known
   defect, preserved behavior, and the earliest remaining failure frontier
   against the unchanged control. Credit product improvement only when the
   known defect disappears or the frontier moves later without an equal or
   earlier regression.

Keep both layers in the report. Instruction uptake does not turn an unchanged
product failure into progress, and a product pass without evidence that the
changed rule was used does not establish a reusable skill improvement. Use
`Conquered`, `Strict improvement`, `Mixed`, `No signal`, or `Regression` for
product movement; retain the per-rule uptake rows underneath that
classification.

### Qualify released generalization claims

When claiming that a skill helps versus no skill, transfers beyond its source
task, or remains general after packaging scripts and references, follow the
[`release qualification and generalization`](references/release-qualification-and-generalization.md)
branch. It owns the matched no-skill control, exact released-byte identity,
tool-usefulness cases, portability and abstention coverage, and the independent
overfitting review.

A passing skill arm, an improvement over an older skill, and deterministic
script tests establish different claims. Name only the claim whose complete
gate passed.

Complete when the exact released artifact either supports the named comparative
or generalization claim at its declared scope, or the report narrows the claim
to the evidence actually obtained.

### Release incremental wins

Treat each published skill revision as the next baseline, not the completion of
the whole task corpus. Independent lanes may solve different tasks concurrently
and propose different generalizable changes, but their results are hypotheses
for one shared skill or skill-set lineage, not separate case-specific releases.
Integrate compatible changes into one coherent candidate and test the combined
bytes against the corpus. Keep a scorecard per exact shared revision and
evaluation contract; a pooled count of passes from different candidates,
models, or case revisions is not that revision's score. Commit experimental
revisions without presenting them as released.

At each credible improvement, reconcile the completed lanes rather than waiting
for every task to be solved. When the integrated candidate conquers a previously
failed full-product task, compare it with the published baseline on the same
frozen case and execution contract, using predeclared repetitions when outcomes
vary. Check that the applicable new rules were used and that the advantage is
not explained by a model, packet, tool, or evaluator change. Run applicable
held-out transfer, maintained-task and newly conquered-task acceptance on the
exact integrated bytes, concurrently where independent. Follow the target
skill's prerequisite gates: when runtime proof must precede implementation
review or broad checks, complete that proof first, then review the same frozen
candidate. A separately authorized check-contract review is not implementation
review.
Publish that revision as soon as those gates pass; unsolved tasks remain open
for the next increment, and independent lanes can continue on isolated
candidates. Record the shared candidate's pass rates, retry dependence, and
remaining failures, then use the published revision as the control for the next
comparison. A newly claimed tactic without an attributable advantage stays
experimental rather than becoming a proven improvement. For explicitly scoped
consolidation or minimization of existing successes, use the corresponding
release branch in the cumulative hill climb; do not invent a new-task campaign
or claim individual-rule causality from artifact qualification.

Before attributing a repeated behavior to the target skill, audit the complete
candidate-visible instruction stack: task wording, repository and custom
instructions, every invoked skill, design or work-order documents, source
comments, existing tests and fixtures, and validation guidance. Record which
sources reinforce or oppose the observed choice. Hidden judge criteria are not
candidate context. When another visible source plausibly selects the same
behavior, classify the interaction or packet bias and isolate it before
strengthening one skill against another instruction.

Do not call difficult or ambiguous task wording a packet defect merely because
it contributes to failure. Compare the frozen packet with the real operating
context it represents. Preserve natural user ambiguity, repository guidance,
source comments, tests, fixtures, and missing information when the real agent
would receive the same context. Repair the packet only when it omits,
misstates, invents, or gives false authority to context relative to that real
situation. If a faithful real-world packet reliably induces the wrong result,
improve the skill or another genuine operating control; changing the case
would only make the evaluation easier.

Do not convert a reference implementation, reviewer preference, or unavailable
production fact into a behavioral failure. Reconcile surprising judgments
against the frozen environment-fit ledger before editing the skill. A quality
finding changes behavioral correctness only after evidence shows that its
reachable defect violates a hard criterion. When the judgment contract itself
is wrong, publish a new frozen case revision, retain the old result, and reuse
the retained candidate patch for regrading or rejudging when the evaluator can
bind it safely; do not spend another candidate run solely to repair downstream
criteria.

Classify a failure before editing:

- **Skill defect:** general instructions omit or misstate a reusable reasoning
  step.
- **Instruction interaction:** another candidate-visible instruction or
  fixture reinforces, narrows, or contradicts the target skill.
- **Execution variance:** the skill already requires the missed behavior.
- **Packet defect:** decisive evidence is missing, leaked, or assigned to the
  wrong phase, or the packet materially misrepresents the real operating
  context.
- **Harness defect:** the candidate or judge did not receive the frozen inputs
  named by the receipt.
- **Grading defect:** a check rejects behavior permitted by the task or accepts
  behavior that fails its requirements.

Repair packet, harness, and grading defects outside the target skill, preserving
original outcomes and identifying corrected evaluations separately. If the
evidence establishes exactly one independently required skill correction and no
competing treatment remains, repair it with general language, rerun the
unchanged case, and retain the prior run. When multiple credible mechanisms
remain, freeze them as treatment arms before editing a preferred candidate.

When the evaluator is valid but the corrective mechanism is uncertain, default
to parallel treatment search rather than serial revision. Search multiple
independent skills and proven practices by generalized behavior class, not by
case vocabulary. Use those sources to generate falsifiable treatment
hypotheses, preserve source and license provenance, and extract only the
smallest reusable tactic. The parallel-treatment procedure owns controls,
dose-matching, planned replication, mechanism scoring, finalist selection, and
held-out transfer.

For corpus consolidation, preserve the declared prior-win set on the combined
draft before minimizing it, following the cumulative hill climb. When observed
instruction dilution or contradiction warrants rebuilding the whole skill,
compare a neutral baseline, a lean replacement, and the unchanged full skill instead of
assuming incremental editing is safest. Follow
[`references/ablation-campaign.md`](references/ablation-campaign.md): start the
lean arm from the smallest load-bearing rules, run one discriminating case,
then add back a rule only when a repeated corpus regression proves it is
missing. When more than one credible add-back could close the regression, use
parallel treatment search with the lean arm as a control. Existing prose earns
retention through behavior, not age.

Complete when the result is labeled `PASS`, `FAIL`, or `UNANSWERABLE`, with the
reason and any generalized skill defect stated separately. For a skill-change
experiment, completion also requires the instruction-uptake rows and product-
movement classification above.

## 7. Report the capability delta

End each skill-change evaluation with a report that says what changed, what the
candidate can now do that the baseline could not, how much the shipped skill
changed, and how strong the proof is. Use
[`references/completion-report.md`](references/completion-report.md).

Link each claimed capability to the prior user-visible failure, the general
rule that changed, and the exact case or product check that proves the effect.
Label it as proven, observed, or intended according to the completed gates.
Report first-attempt and retry-dependent passes separately.

Measure bytes and text lines with the same method on the exact baseline and
candidate. Separate shipped skill instructions and references from evaluator
code, cases, generated files, run artifacts, and project documentation. Size
alone does not prove that a change is simpler or better; only an applicable
ablation or maintained-task check can support that claim.

Keep the report proportional, but never invent a baseline, capability, size,
causal claim, or confidence level that the retained evidence does not support.

## Verification

The evaluation is complete only when:

- the target skill under test is identified by file digests;
- every candidate phase reads only its frozen allowlist;
- hidden judge evidence is absent from candidate workdirs and structured logs
  prove candidate reads stayed inside those workdirs;
- every run has raw output and a receipt;
- every material case classifies hard criteria as candidate-observable,
  handoff-owned, or post-environment and completes its applicable
  constraint-challenge or dual-review gate;
- at least two independent judges assess behavioral correctness for a material
  skill change;
- a new case does not change any older case root digest; and
- a maintained regression suite runs through one command and every included
  case meets its predeclared qualification rule after a target-skill change,
  with complete original attempt outcomes retained; and
- every no-skill advantage, broad transfer, or packaged-generalization claim
  about a published revision completes the applicable
  [`generalization gate`](references/release-qualification-and-generalization.md)
  on the exact released artifact; and
- no evaluation repair introduces case-specific hints into the target skill.
- a large distributed campaign, when used, has one checksum-bound effective
  result per expected attempt ID, with no missing, extra, or duplicate
  observations and no model outcome replaced by an infrastructure retry.
- a parallel treatment search, when used, has pre-declared controls,
  hypotheses, repetitions, source provenance, mechanism observations,
  selection rules, and held-out transfer for any promoted treatment.
