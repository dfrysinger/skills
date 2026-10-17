# Measurement and quality history

Correctness, resource use and shipping quality are separate results. Usage or
review failures never turn executable `PASS`, `FAIL` or `INVALID` into a
different correctness result. Quality assessments do not change retry policy.

Markdown history begins with a population scorecard, followed by every retained
attempt and each population's complete identity and spending details. Scorecard
labels include case revision and maximum attempts, so different revisions or
retry limits remain visible without opening the full identity. First
outcomes show passes, valid originals and requested originals; behavioral
outcomes separately show reported passes and judgment coverage. Neither summary
is a release qualification. Credits distinguish exact totals from observed
subtotals. Observed trial-elapsed sums include retries and unsuccessful work,
with sleep-inclusive coverage reported separately. They are not parallel
campaign elapsed time or billed runner time. Missing full-wall measurements
remain unknown rather than borrowing the narrower execution duration.
The scorecard is a view over JSON history, not a
new result artifact.

## Usage and timing

Every run has evaluator-owned attempt metadata, a pinned case revision, plugin
and harness identities, and requested model, effort and timeout. Model
invocations have explicit session UUIDs and roles: `candidate`,
`behavioral_judge` or `quality_judge`. Candidate measurements also retain an
additive subrole. Direct runs use `candidate`; the bounded Sandcastle runner
uses `candidate_implementer` and `candidate_reviewer`.

| Artifact | Meaning |
| --- | --- |
| `attempt.json`, `run-context.json` | Attempt, suite ordinal and frozen task configuration |
| `measurements/*.json` | Fixed invocation-end observations, ownership, source, CLI version, coverage and errors |
| `accounting.json` | Candidate, external evaluation and total spending, with session-level coverage |
| `timing.json` | UTC boundaries and observed monotonic elapsed from before preparation through requested judgments and cleanup, with clock implementation and sleep coverage |
| `reporting-timing.json` | Subsequent measurement aggregation and report rendering |
| `suite-timing.json` | Observed suite elapsed including preparation, attempts, reporting and cleanup; sleep coverage is not established |

Stages name preparation, candidate execution, deterministic grading,
behavioral judging, optional quality review and cleanup when those stages run.
Failed and interrupted stages are retained. The outer interval is elapsed
within that producer's scope, not active work or complete campaign feedback.
Overlapping agent/API durations must not be added to it.

`Timeline` records retain `clock: "monotonic"` and `elapsed_seconds`, and
add `clock_implementation` and nullable Boolean `suspend_inclusive`. On Darwin,
the available `CLOCK_MONOTONIC_RAW` source counts time during sleep. One selected
source measures the entire Timeline; a read failure or backward observation is
an explicit measurement error, not a reason to switch clocks silently. Other
unestablished runtimes retain ordinary monotonic elapsed with unknown sleep
coverage. Reporting and suite timers have separate scopes and do not inherit
the attempt's clock coverage.

Records without clock coverage keep their observed elapsed values. A generic monotonic label
does not establish sleep-inclusive wall time. Wall-labeled efficiency metrics
require positive sleep coverage and implementation metadata from the trusted
producer/coordinator projection; absent, unknown or false coverage remains
unknown wall time. This metadata is not authenticated model output or billing
evidence. Malformed metadata is an explicit input error. The history scorecard
reports observed elapsed sums and counts sleep-inclusive attempts separately,
without reconstructing historical sleep or combining independent intervals.

`execution-result.json.elapsed_seconds` measures repository execution through
grading, not subsequent host judging. Command receipts' `elapsed_seconds`
measure that command and its log handling. `suite-result.json.duration_seconds`
ends before suite report writing and cleanup. These existing fields retain
their narrower meanings. Dedicated timing artifacts establish their own elapsed
scope; verified full-wall claims additionally require known sleep coverage.
Historical missing coverage remains unknown.

### Sources, units and coverage

The evaluator reads only the exact invocation-owned
`session-state/UUID/events.jsonl`. Host capture rejects links, non-regular and
multiply linked files and opens path components beneath the selected home
without following links. Container capture stops the writer, then runs one
exact `docker cp` into a scoped temporary spool. It accepts one regular
`events.jsonl`, never extracts archive paths to the host filesystem and rejects
additional entries, links, sparse and special files, truncation and nonzero
padding or trailing data. Capture retains its deadline and bounded stderr;
the spool is closed and removed on success or failure.

Host events, invocation stdout and archive members share a streaming JSONL
parser. Each raw record, including its line terminator, is limited to 32 MiB
before UTF-8 decoding. There is no whole-eventfile or archive byte quota.
Accounting retains its line and blank-record grammar; native quality validation
requires LF-delimited records without blank records, duplicate keys or
non-finite JSON constants. Only filtered observations and required native
validation state survive record processing. Earlier CLI subprocess-output
buffering is separate and is not made constant-memory by this collector.
Rejected source bytes are not retained as measurement artifacts.

Only allowlisted usage counters and model/agent breakdowns are retained.
Authentication homes, configuration, tokens, databases and unrelated sessions
are not exported. Container telemetry is candidate-controlled and **not
tamper-proof billing evidence**. Source fields cannot replace evaluator-owned
case, attempt, role, session, plugin, harness or requested-model identity.

Terminal shutdown is preferred over a partial checkpoint; invocation stdout
is fallback evidence. No successful answer or result parser is required to
collect usage. A missing timeout eventfile is supported. Malformed numeric
or structural evidence is an explicit measurement error, not zero spending.
Resume capture snapshots the prior byte length and SHA-256 digest without
retaining the transcript. The successor must contain that identical prefix;
missing, changed or truncated prefixes are errors. Phase observations start at
the exact snapshot byte offset, so an earlier shutdown cannot establish terminal
coverage for a later failed invocation.

Documented `totalNanoAiu` fields use mapping `copilot-sdk-nano-aiu-1e9`, with
SDK source revision `d3755535869e97d2bcf5aa6a5b8c35de79f5a7d8`: one AI credit is
1,000,000,000 nano-AIU. The observed CLI version is retained with the mapping.
Premium requests remain a separate unit. No premium-request conversion,
currency price or dollar total is inferred.

Each invocation preserves its cumulative observation. Resumed phases of the
same candidate session are counted once, using the latest known cumulative
total, not fabricated per-phase deltas. Nested candidate agents are already
included in that total. Breakdowns are descriptive, never additional charges.
Failed external judges remain external evaluation spending.

For Sandcastle, the evaluator allocates the implementer and conditional
reviewer UUIDs before the adapter starts. The retained treatment result must
match those UUIDs, the fixed model, and the allowed subroles. Exact candidate
credits require terminal event coverage for every expected allocated session.
Missing expected events, malformed or duplicate declarations, a wrong model,
or observed undeclared session files remain explicit incomplete or contaminated
coverage. Candidate-authored declarations and the absence of another observed
file never establish exhaustive accounting.

A failed post-candidate session inventory still stops the writer and preserves
measurements for allocated or observed sessions. Its error marks coverage
incomplete; launched work cannot become exact zero spending because inventory
failed.

`credits` in the accounting summary is an exact total only when every relevant
session has known credits and terminal coverage. Otherwise it is null and
`observed_credits` is the explicitly partial subtotal, also null if nothing is
known. An attempt with no model invocations has zero model spend; an invocation
with no usage evidence does not. Terminal coverage with premium-request-only
usage still cannot establish credits. Evidence is fixed at invocation end;
there is no delayed collector or reconciliation command.

### Project retained candidate counters

For a completed local retained archive, select the JSON documents known to be
copies of one candidate's cumulative usage:

```sh
python3 scripts/distributed_campaign.py recover-retained-usage \
  retained.tar.gz retained.tar.gz.sha256 \
  --member run-root/usage.json --member run-root/usage-copy.json
```

The checksum must name the archive's basename. Selected relative POSIX paths
must be unique and unambiguous. The archive's `evidence/retention-manifest.json`
must declare `schemaVersion: 1` and matching `path`, `bytes` and `sha256` records
for each present selected member. Members and the manifest must be ordinary
nonsparse files. The command reads data only: it does not extract, execute,
download, discover sessions or modify original evidence.

Only optional top-level `totalNanoAiu` and `totalApiDurationMs` counters are
projected. Missing members, missing fields and nulls remain unknown; explicit
zero remains zero. Equal normalized copies count once, regardless of other
metadata. Conflicting counters, malformed JSON, duplicate keys, invalid numeric
values or failed integrity checks exit nonzero without a recovered report.

Stdout contains a separate JSON report with archive/member provenance,
`reported_nano_aiu`, `reported_api_duration_ms`, unknown fields and selected
present/missing members. Its trust is `candidate-reported`; the caller asserts
the shared cumulative scope. Checksums establish byte integrity, not truth or
authentication. The report never supplies sessions, terminal coverage, grades
or `accounting.credits`. API duration is not candidate wall time, and recovered
counters are not exact full evaluation cost.

## Continuous execution efficiency

The existing distributed command reports over a coordinator-authored projection:

```sh
python3 scripts/distributed_campaign.py audit-efficiency synthetic-view.json \
  --baseline synthetic-baseline.json --policy synthetic-policy.json
```

Baseline and policy are optional. The command reads only these explicit JSON
inputs, does not resolve their references, and never changes results, starts
work, accepts a repair or grants admission. Coordinator projections are
conditional observations, not authenticated arbitrary grades or billing.
Candidate-reported product outcomes remain unresolved.

For routine inspection of a saved report, show coverage counts instead of
repeating every identity. If `jq` is available:

```sh
jq '
  . + {display_only: true}
  | if .coverage then
      .coverage |= with_entries(
        if (.value | type) == "array"
        then .value = {count: (.value | length)}
        else . end)
    else . end
' report.json
```

Keep the full report and the auditor's process exit status as audit evidence.
This display preserves metrics, triggers, readiness, policy and errors; it is
not a replacement report or reconciliation input. The `jq` exit status reports
only whether inspection succeeded. Read exact identities from the saved report
when a coverage count needs investigation.

### Projection contract

The view requires `schema_version: 1`, nonempty `scope_id` and
`source_fingerprint`, `comparison_contract`, `expected_decision_ids`,
`decisions`, `expected_work_ids`, `work`, nullable `outer_timing`, and `control`.
Expected identity lists are unique and exhaustive for the declared scope.
Missing records remain explicit unknown coverage. Unexpected identities,
conflicting records, duplicate JSON keys, malformed types and negative,
nonfinite or out-of-range measurements produce an explicit JSON error.
Identical repeated records count once. Supplemental fields cannot replace
defined policy, outcome or control fields.

`comparison_contract` is a coordinator-authored object containing
`comparison_mode: retained_replay|fresh_window` and the fixed authorized case
revisions, planned population/multiplicities, model, effort, timeout, checks,
thresholds, repetitions, retry and verification rules. Exact normalized
equality defines comparability; source fingerprints can differ for an
overhead-only change. The owner is responsible for declaring the complete
population and rules, not filtering the view to successful attempts.

Each decision has `id`, `class: product|audit`,
`status: PASS|FAIL|PENDING|INVALID|UNKNOWN`, and
`provenance: {reference, digest, trust}`. References and digests are nonempty
opaque strings; trust is `coordinator_projection` or `candidate_reported`.
Unique coordinator-projected product `PASS` and valid `FAIL` count equally as
useful decisions. Audit outcomes are counted separately; invalid, pending,
unknown, missing and candidate-reported product outcomes remain unresolved.
Retained replay requires identical expected identities, classes, statuses
and canonical outcome digests. A changed retained outcome is an integrity
trigger, including a present trusted reclassification to an unresolved or invalid
status. Missing or untrusted retained outcome evidence is incomplete coverage,
not proof of mutation. Fresh windows may have different attempt identities and realized
outcomes under the same complete planned population and rules.

Each work record requires `id`, `owner`, nullable `parent_id`,
`category: coordination|infrastructure|execution|reporting`, nullable
`seconds`, `source_reference`, `inclusion: leaf|aggregate`, and
`purpose: recurring|repair_investment`. Parent links must be present, acyclic
and point to aggregate records. Only leaves are charged. Distinct owners'
overlapping work is work, not elapsed wall time. Include unsuccessful audit,
implementation, review, measurement and retry investment once in the declared
scope; missing investment is unknown, not free.
An unsupported work category returns an error naming the work record, rejected
value and supported categories. Correct the projection; the auditor never
reclassifies work automatically.
Ordinary per-run preparation and correspondence checks are recurring work,
even when they create a fresh metadata or proof root. Charge repair investment
separately rather than hiding repeated preparation in that category.

`outer_timing` retains the Timeline shape: `clock`, nullable `elapsed_seconds`,
and `stages`. Optional stage `start_seconds` and `end_seconds` are offsets
within that same monotonic outer interval, with explicit work categories.
An overhead wall fraction requires sorted, disjoint, contained intervals
covering exactly `0..elapsed_seconds`, known categories and consistent
optional stage durations. Explicit stage clock/scope mismatches, missing
offsets, gaps, overlap, zero elapsed or foreign clocks yield a null fraction
with reasons. UTC timestamps alone do not establish those offsets.

Capture the actual clock implementation and suspend behavior before the window
starts. Cross-process windows also need a common origin and boot identity.
Full feedback latency requires a clock that includes
host suspension. On macOS, Python's monotonic clock may use
`mach_absolute_time()`, which excludes system sleep; Darwin's
`CLOCK_MONOTONIC_RAW`, where exposed by `time.clock_gettime_ns`, includes it.
Keep awake elapsed separately: it is neither CPU time nor active work, and
passive waits still need their own scope. The `clock: "monotonic"` marker alone
does not declare coverage: retain the actual `clock_implementation` and
`suspend_inclusive` observation, or leave full wall unknown. Start, end and
stage offsets must use the same clock origin. UTC comparisons can diagnose
a coverage gap, but cannot reconstruct an uncaptured clock start or turn
awake elapsed into verified full feedback latency.

The report separates outer wall per useful product decision, recurring
coordination/reporting leaf work per useful decision, total leaf work per
useful decision, and the exact overhead wall fraction. Ratios require a
positive complete product denominator and complete relevant coverage.
Observed work subtotals, recurring versus one-time investment, category sums
and unresolved identity sets remain visible even when exact ratios are null.
Work divided by wall is never used as a wall fraction.

### Policy, events and reconciliation

Policy JSON may override the following explicit defaults; unknown policy
fields are errors. Defaults are provisional owner policy, not grading rules:

| Field | Default |
| --- | --- |
| `policy_id` | `execution-efficiency-provisional-v1` |
| `improvement_fraction` | `0.2` |
| `regression_multiplier` | `1.25`, strictly greater triggers |
| `consecutive_complete_windows` | `3` |
| `unproductive_same_operation_cycles` | `2` |
| `routine_copies_target` | `0` |
| `quality_regressions_allowed` | `0` |
| `required_metrics` | `["overhead_work_per_decision"]` |
| `require_baseline` | `false` |

Required metrics may name `outer_wall_per_decision`,
`overhead_work_per_decision`, `total_work_per_decision`, or
`overhead_wall_fraction`. Window/cycle counts are positive integers;
copy/quality counts are nonnegative integers. Improvement is in `[0,1)`,
and the regression multiplier is at least one. Keep policy changes and
baseline identities with their evidence in the owner's existing charter;
do not silently reset either.

`control` requires coordinator-owned boolean `scope_hold` and `open_repair`.
Optional boolean `integrity_violation`, nonnegative integer
`quality_regressions`, and nonempty-string `recurrence_signatures` retain
quality/integrity and recurrence causes separately.

Optional `consecutive_windows` contains complete prior views, oldest first;
the current view is appended by the command. Scope identities must be unique,
and nested window history is refused. Three adjacent eligible windows above
the multiplier trigger regression; an ineligible or non-regressing intervening
window breaks the run rather than being skipped. A missing or incompatible
baseline is ineligible, not by itself corruption or regression. Standing holds
and open repairs do not make otherwise comparable prior windows ineligible:
measurement continues during repair, so a persistent regression cannot clear
its own reconciliation check.

Optional `operation_materializations` records `operation_id`,
`operation_digest`, boolean `implementation_changed`, and integer
`new_executable_copies`. Unchanged operations exceeding the copy target
trigger a pause. Optional ordered `same_operation_cycles` records
`operation_id`, `operation_digest`, boolean `new_decision_evidence` and opaque
`evidence_reference`. The final consecutive no-new-evidence sequence of the
same operation/digest triggers at the cycle limit; changed digest, changed
operation or new evidence resets it. Omitted event lists mean no reported
events, not independently authenticated absence.

JSON and process status agree, with this priority:

| Exit | State | Meaning |
| --- | --- | --- |
| `1` | `ERROR` | Malformed JSON, projection or policy |
| `2` | `PAUSE_NEW_WORK` | Any integrity, recurrence, open repair, standing hold, measured regression, copy or cycle trigger |
| `3` | `MEASUREMENT_REQUIRED` | Missing decisive current quality/metrics or required comparable baseline |
| `0` | `PROCEED` | No reported trigger or missing decisive measurement |

`drain_allowed` remains true: collection and already-running work may drain.
All trigger and measurement reasons are emitted independently of priority.
`reconciliation_ready` ignores only standing hold and open repair; required
current quality/metrics and all other triggers must be clear. Thus a held view
can return exit `2` with readiness true. Readiness does not accept a repair.
The coordinator requires separate accepted focused proof and scoped
applicability, records explicit reconciliation, then clears its hold and open
repair flags and audits again. Only that later audit can return `0`; neither
field supplies independent execution authority.

Recurring-overhead and complete-total comparisons are separate. The improvement
target requires the requested recurring-overhead reduction, complete total
work reduction including all declared investment, comparable no-worse outer
wall, and clear non-standing triggers/decisive coverage. Zero baseline yields an undefined ratio.
Missing financial, historical wall or investment coverage disables related
claims, not forward instrumentation. No billing, amortized benefit beyond an
actual observed horizon, or whole-process savings is inferred.

Run one finite smallest attempt to fill decisive missing measurement. A failed
or inconclusive attempt retains its gap and scoped remedy without an identical
automatic retry. Preserve validated, unsupported, inconclusive and blocked
remedies in the existing charter with source/boundary identities, policy,
baseline, proof, investment coverage and reopening conditions. Same-source
recurrence reopens repair; changed source or actor/authority/operation/effects/
protected boundary requires scoped applicability before reuse.

The public `scripts/fixtures/efficiency-event-flow.json` documents a synthetic
owner event sequence, exercised against the actual CLI by
`python3 -m unittest -q test_execution_efficiency` from `scripts`. It is not a
new coordinator or an automatic repair engine.

## Independent source quality

```sh
python3 scripts/skill_eval.py run CORPUS --case CASE \
  --plugin-dir PLUGIN --arm skill --model MODEL --effort high \
  --timeout-seconds 1200 --quality-review

python3 scripts/skill_eval.py run-suite CORPUS \
  --plugin-dir PLUGIN --arm baseline --workers 2 --max-attempts 1 \
  --quality-review
```

This option is for repository tasks. The case's existing Claude/GPT judge
convention supplies the models, each with a separate session and high effort.
The option adds paid evaluation; candidate spend remains separate.

Each reviewer sees only public requirements, frozen baseline source and source
replayed from the candidate patch. The packet excludes hidden graders,
reference answers, trajectory, cost and experiment metadata. Reviewers receive
an empty plugin, no intentionally supplied target-skill instructions, and only
the read tool. Read paths and tool calls are audited. They cannot run candidate
code or tests. Candidate-authored source may mention a skill, so this is
source-only blinding, not a promise of perfect anonymity.

`quality/assessment.json` binds the case revision, patch digest, packet
manifest and versioned prompt hash. Individual `quality/review-*.json`
artifacts preserve each reviewer, outcome, failure and finding without
consolidation. Assessment destinations are write-once; a second write is
refused. The generated `requirements/task.md` manifest record identifies its
source with a `kind`, a `root` (`packet` or `frozen_case`) and a path relative
to that root. There is no standalone reassessment command.

After a successful CLI exit, quality validation reads the exact owned native
session before its temporary home is deleted. It requires a matching fresh
session, selected and observed assistant models, terminal shutdown, paired
allowlisted tools, in-packet successful views and a final answer. A failed view
does not count as a source read. Missing, corrupt or incomplete events fail the
review without falling back to stdout; an over-bound raw record also fails
quality validation.

The reviewer's `validation` record identifies native session events, their byte
digest of all original file bytes and record count, and successful process completion.
The digest is computed incrementally, without filtering or re-encoding. It marks
bytes inspected in process, not independently re-verifiable durable integrity
evidence. No separate native transcript or tool-payload copy is retained. The existing
stdout artifact, its digest and measurement errors remain intact.
Native review success does not upgrade accounting completeness or change
historical assessments. Candidate and behavioral judging keep their separate
stdout validation contract.

Shipping judgments are `acceptable`, `needs_revision`,
`fundamentally_incorrect` or `unassessable`. Findings require a baseline or
candidate file, inclusive one-based line range, matching source quotation,
severity, concrete trigger and explanation. Reviews consider requirement
completeness, scope, maintainability and test adequacy without ordinal ratings
or weighted scores.

Findings are **reviewer-reported**, not independently adjudicated. Disagreement
is retained. A failed or missing reviewer makes the assessment incomplete and
cannot erase a successful reviewer or imply a complete acceptable assessment.
An unavailable patch produces an explicit incomplete assessment without
starting reviewers.

### Supplemental reviewer fields

Quality and behavioral callers select the defined assessment fields before
strict validation. Additional quality finding fields are also excluded.
Missing fields, incorrect types, invalid source citations and invalid
invocation evidence still fail; fields are never repaired or defaulted.

`supplemental_fields_ignored` on quality reviewer records and behavioral
receipts lists excluded locations as arrays of keys and list indices. An empty
list means interpretation ran and found no additional fields. Excluded values
are unvalidated commentary, not assessment data or caller-owned provenance.

Each selected answer is saved exactly in an `{"answer": "..."}` envelope named
`*-response.json`. The caller's `selected_response` contains its run-relative
path and file hash. This preserves supplemental values, fences and trailing
prose without retaining native tool or reasoning payloads. If required output
validation fails after selection, the failed reviewer record or failure receipt
still links the answer. Failures before selection have no answer artifact.

Canonical behavioral judgments retain their defined fields and caller-selected
model. History does not interpret or rewrite older records, including rejected
responses. Absence of these diagnostics on older records does not mean they
were interpreted. Behavioral failure isolation is unchanged.

## Read historical results

```sh
python3 scripts/skill_eval.py history CORPUS --format markdown
python3 scripts/skill_eval.py history CORPUS --format json > history.json
python3 scripts/skill_eval.py history CORPUS --case CASE --arm skill \
  --model MODEL --format markdown > history.md
```

History reads original run artifacts and existing suite attempt ownership
directly. It neither creates an index nor rewrites evidence. A suite reference
and standalone discovery of the same run produce one row. Runs without new
measurement artifacts remain visible with unknown accounting and full timing.
Malformed records and conflicting ownership fail visibly rather than being
silently omitted.

Compatibility-`BLOCKED` and preparation-`INVALID` attempts can precede treatment
snapshot capture. History retains their declared identity and original result,
marks `treatment_artifacts_verified` false, and does not treat missing snapshots
as execution evidence. Executed attempts still require matching descriptor,
source and adapter artifacts.

Reports show per-attempt correctness, behavioral verdict, accounting coverage,
quality and duration. Treatment-aware reports also project treatment,
intervention policy, compatibility, candidate credits, and evaluator credits
as separate fields. Aggregates keep exact task revision, treatment and adapter
identity, compatibility predicates and result, arm/skill identity, harness,
image, model/effort, timeout, retry budget and evaluation configuration
separate. Do not treat changing task mixes or unknown configurations as a
matched experiment.

First-attempt executable success is separate from eventual and retry-assisted
success. Credits per successful first attempt use all requested first-attempt
spending in that exact population, including failures and invalid attempts.
Retry, invalid and unsuccessful spending are also reported separately; these
overlapping views are not additive. Zero first-attempt successes or incomplete
relevant credits yields no exact ratio. A low observed subtotal with poor
coverage is not evidence of a cheap successful run.

Generic focused checks require only the existing Python unittest runner:

```sh
cd scripts
python3 -m unittest -q test_skill_eval test_repository_task.RepositoryTaskTests test_measurement
```
