# Measurement and quality history

Correctness, resource use and shipping quality are separate results. Usage or
review failures never turn executable `PASS`, `FAIL` or `INVALID` into a
different correctness result. Quality assessments do not change retry policy.

Markdown history begins with a population scorecard, followed by every retained
attempt and each population's complete identity and spending details. First
outcomes show passes, valid originals and requested originals; behavioral
outcomes separately show reported passes and judgment coverage. Neither summary
is a release qualification. Credits distinguish exact totals from observed
subtotals. Known trial-wall sums include retries and unsuccessful work and show
timing coverage; they are not parallel campaign elapsed time or billed runner
time. Missing full-wall measurements remain unknown rather than borrowing the
narrower execution duration. The scorecard is a view over JSON history, not a
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
| `timing.json` | UTC boundaries and monotonic wall time from before preparation through requested judgments and cleanup |
| `reporting-timing.json` | Subsequent measurement aggregation and report rendering |
| `suite-timing.json` | Suite wall time including preparation, attempts, reporting and cleanup |

Stages name preparation, candidate execution, deterministic grading,
behavioral judging, optional quality review and cleanup when those stages run.
Failed and interrupted stages are retained. The outer interval is total wall
time; overlapping agent/API durations must not be added to it.

`execution-result.json.elapsed_seconds` measures repository execution through
grading, not subsequent host judging. Command receipts' `elapsed_seconds`
measure that command and its log handling. `suite-result.json.duration_seconds`
ends before suite report writing and cleanup. These existing fields retain
their narrower meanings; use the dedicated timing artifacts for full wall
time. Historical runs without them have unknown full wall time.

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
