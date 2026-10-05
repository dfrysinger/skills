# Large private-Actions evaluation campaign

Use this procedure when a corpus is too large, slow, native, or product-heavy
for one local host. GitHub Actions provides elastic execution; the evaluator
still owns case integrity, first-outcome preservation, artifact verification,
and final reconciliation.

For an implementation of this contract, see
[`distributed-campaign-tooling.md`](distributed-campaign-tooling.md). The
included scripts and workflow template are product-neutral. Keep each corpus,
hidden evaluator payload, release asset, and result in a private carrier
repository.

## 1. Freeze the execution universe

Assign one stable attempt ID to every case, treatment, repetition, model, and
platform combination. Write the complete expected matrix before dispatch.

Seal one immutable campaign release with separately addressed candidate and
hidden payloads. The candidate payload contains:

- frozen candidate-visible cases;
- target-skill and treatment snapshots;
- pinned evaluator code;
- pinned tool and dependency identities;
- platform routing;
- timeouts and resource limits; and
- the expected attempt matrix.

The hidden payload contains deterministic graders, judge packets, reference
artifacts, and any evaluator-only fixtures. Publish both as private,
checksum-addressed assets under one manifest. Record archive, manifest,
evaluator commit, CLI, dependency, and container or runner identity. Do not
rebuild either payload to repair an outer orchestration defect when its sealed
inputs remain valid.

The candidate stage materializes only the candidate payload into an isolated
workdir. Hidden payloads remain unavailable to that process and session.
Structured tool logs must prove candidate reads stayed inside the candidate
workdir and its explicit allowlist. Download or materialize hidden payloads
only after candidate execution and patch capture have ended. Use a separate
job or runner for the hidden stage so a process left behind by candidate code
cannot observe later evaluator downloads. Reconstruct the candidate from its
captured patch and verify its Git tree before product proof.

Complete when workers can verify the campaign manifest, candidate execution
cannot address hidden bytes, and the expected attempt set is immutable.

## 2. Separate stages and outcomes

Model the attempt as independently receipted stages:

1. candidate setup and model execution;
2. candidate patch and status capture;
3. product build and exercise;
4. deterministic target and regression grading;
5. independent judges;
6. retention and checksum publication.

Write a receipt before crossing each destructive or expensive boundary. Record
whether the candidate model launched, its terminal state, the retained patch,
and every downstream stage result.

The first launched model outcome is immutable. A later evaluator failure does
not authorize another candidate run. Only a failure proven to occur before
model launch may receive a replacement attempt.

Complete when a failed workflow can be classified from receipts without
guessing whether candidate work occurred.

## 3. Prove one route before fan-out

Treat evaluator development as its own test pyramid. Use the cheapest check
that exercises the changed boundary:

1. unit-test pure planning, receipt, parsing, and validation logic;
2. run a tiny packaged fixture for archive, handoff, filesystem, and process
   behavior;
3. use a no-model canary or retained candidate artifact for runner, platform,
   dependency, product, grader, and judge integration; and
4. spend one real model attempt only after the cheaper layers pass.

Test cost includes package construction and compression, release upload and
artifact download bytes, runner startup, native compilation, model execution,
judge execution, and elapsed feedback time. Prefer a small source tree and
tiny artifacts when they exercise the same boundary. Do not use a long native
build or multi-gigabyte artifact as the first smoke test for receipt parsing,
stage routing, permissions, or recovery.

After the evaluator-only canary passes, run a representative campaign pilot
through each distinct route:

- macOS native;
- Linux native or container;
- browser or desktop product proof;
- cloud-agent or external execution engine; and
- any special multi-workspace transport.

Use the exact campaign payloads, secrets, security flags, pinned binaries, and
artifact paths the full matrix will use. A token or dependency smoke test is
useful only when it reproduces that exact child-process boundary.

When a real pilot has already produced an immutable model result, reuse its
retained candidate or product artifact for every downstream repair. Replay only
the first invalid stage and its dependents. Do not consume another model
attempt to test grader permissions, receipt decoding, judge parsing, retention,
or final reconciliation.

Keep execution-engine cohorts separate from workflow-treatment rankings unless
the experiment was designed to compare them as the same independent variable.
When candidate-safe and hidden payloads are split, use only routes with a
separate candidate job and complete hidden-stage dependency provisioning. The
included reusable workflow rejects split Linux-native attempts and split
attempts that require external dependency archives.

Complete when every route produces a checksum-verified retained receipt and its
result semantics are understood.

## 4. Dispatch unfinished work massively in parallel

Create a completion manifest from already valid observations. The planner
subtracts those exact attempt IDs from the expected matrix and refuses:

- an unknown exclusion;
- duplicate attempt IDs;
- a treatment, case, repetition, or platform mismatch; or
- a plan whose included plus excluded attempts do not equal the frozen matrix.

Set `max-parallel` to the admitted runner capacity. High concurrency is correct
when attempts have isolated workspaces, unique branch or artifact names, and no
shared mutable product fixture. Route platform-specific cases explicitly rather
than serializing the entire matrix behind the rarest runner.

Private repositories and private release assets prevent external disclosure;
they do not establish candidate isolation. Candidate jobs receive only their
allowlisted payload and workdir. Hidden evidence and secrets enter only the
later stage that requires them.
Strip host-selection variables from model child processes when those variables
would redirect authentication to the wrong service.

Complete when every unfinished attempt is requested once and Actions shows the
expected fan-out.

## 5. Treat artifacts as the transport

Every job uploads a final retained archive even when a later stage fails.
Include:

- stage receipts;
- candidate transcript and identity;
- candidate patch and status;
- deterministic logs;
- product logs and evidence;
- judge outputs;
- workflow and evaluator identity; and
- a retention manifest with SHA-256 values.

Download artifacts by exact run and artifact identity. Verify the published
checksum before extraction. Use fail-closed extraction, absolute patch paths,
and a fresh destination. Preserve source run IDs and archive hashes through
every recovery.

Do not infer worker status from a dirty directory or partial artifact listing.
Use the workflow result and embedded receipts.

Complete when retained bytes can reconstruct the exact candidate and every
stage used in the result.

## 6. Recover stages without replaying candidates

Classify failures:

- **pre-model infrastructure**: setup, publication, credential, or runner
  failure before the model launched;
- **candidate outcome**: timeout, model failure, or completed candidate work;
- **product failure**: candidate retained, product build or exercise failed;
- **grader failure**: candidate and product retained, deterministic grading
  failed to run;
- **judge failure**: executable evidence retained, judge invocation or format
  failed;
- **retention failure**: earlier stages completed, final archive publication
  failed.

Recovery rules:

- replace only proven pre-model failures;
- resume product, grader, judge, or finalization stages from retained evidence;
- never convert a failed executable gate into a pass because judges liked the
  patch;
- preserve predecessor failure evidence and record `candidateRerun: false`;
- bind recovery to exact attempt ID, case revision, treatment, repetition,
  source run, source commit, artifact name, and checksum; and
- use bounded retries for transient pre-model publication, network, or runner
  failures while retaining full diagnostics.

An overall workflow may show failure while an authoritative recovery finalizer
succeeds. Use the retained effective receipt, not the workflow color alone.

Complete when each effective observation has one traceable first model outcome
and any recovery changes only invalid downstream infrastructure.

## 7. Reconcile exactly

After all dispatches settle:

1. download every candidate effective artifact;
2. verify its checksum;
3. classify failed jobs by model-launch state;
4. build the replacement lineage for proven pre-model failures;
5. select exactly one effective receipt per expected attempt ID; and
6. reject the map unless expected, effective, missing, extra, and duplicate
   counts reconcile.

Do not use broad recent-run queries as the source of truth. Persist exact
dispatch ledgers and source-run lineage.

The final map records:

- effective attempt ID;
- source kind;
- source and recovery run IDs;
- archive checksum;
- candidate rerun status;
- stage outcomes;
- judge outcomes; and
- composite result.

Complete when there are zero missing, extra, or duplicate effective
observations.

## 8. Analyze failures before changing the skill

Aggregate by case, treatment, repetition, stage, timeout, target, regression,
product proof, judge agreement, runtime, and source kind. Paired comparisons
against a baseline are more informative than raw totals when the same cases and
repetitions are shared.

For skill-change treatments, score two layers independently:

- **Instruction uptake:** whether each applicable changed rule is observed,
  partial, absent, or not applicable in candidate actions and artifacts.
- **Product movement:** whether the known defect disappeared, preservation
  held, and the earliest failure frontier moved later than the paired control.

Keep useful uptake evidence even when the case remains red. Do not call it
product improvement when the same defect recurs at the same frontier. Classify
product movement as `Conquered`, `Strict improvement`, `Mixed`, `No signal`,
or `Regression`, and retain the per-rule uptake rows beneath it.

Inspect repeated failures by case. Separate:

- skill defects;
- execution variance;
- packet ambiguity;
- harness setup defects;
- reference-implementation coupling; and
- genuine product difficulty.

If every treatment fails at the same setup boundary, repair the case rather
than teaching the skill to accommodate the broken evaluator. Publish a new case
revision; never rewrite the historical result.

Complete when proposed skill changes are grounded in valid executable signals.

## 9. Report with evidence integrity

The report states:

- matrix shape and exact completeness;
- campaign-release and result-map identity;
- first-outcome and recovery rules;
- execution-level outcomes;
- target, regression, product, and judge outcomes separately;
- instruction uptake for each applicable changed skill rule;
- product-movement classification and earliest failure frontier;
- paired treatment effects;
- repeatability;
- per-case concentration;
- runtime and available cost proxies;
- invalid or inconclusive case findings; and
- uncertainty from sample size, retries, unavailable telemetry, or repaired
  judge formats.

Judges never override executable failures. Plausible code with a failed target,
regression, or product gate remains a failure.

Have independent model families review the final report against the result map
and analysis data. Correct factual or interpretive drift without changing the
underlying observations.

Complete when the report can be regenerated from the checksum-bound effective
map and every conclusion states its evidence limits.
