# Measurement and quality history

Correctness, resource use and shipping quality are separate results. Usage or
review failures never turn executable `PASS`, `FAIL` or `INVALID` into a
different correctness result. Quality assessments do not change retry policy.

## Usage and timing

Every run has evaluator-owned attempt metadata, a pinned case revision, plugin
and harness identities, and requested model, effort and timeout. Model
invocations have explicit session UUIDs and roles: `candidate`,
`behavioral_judge` or `quality_judge`.

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
exact `docker cp` into a bounded in-memory archive reader. It accepts one
regular `events.jsonl`, never extracts to the host filesystem and rejects
additional entries, links and special files. Event content is limited to
32 MiB; archive transport allows another 1 MiB for headers and padding.
Rejected source bytes are not persisted by the collector.

Only allowlisted usage counters and model/agent breakdowns are retained.
Authentication homes, configuration, tokens, databases and unrelated sessions
are not exported. Container telemetry is candidate-controlled and **not
tamper-proof billing evidence**. Source fields cannot replace evaluator-owned
case, attempt, role, session, plugin, harness or requested-model identity.

Terminal shutdown is preferred over a partial checkpoint; invocation stdout
is fallback evidence. No successful answer or result parser is required to
collect usage. A missing timeout eventfile is supported. Malformed numeric
or structural evidence is an explicit measurement error, not zero spending.
Resume capture reads only newly appended events, so an earlier shutdown cannot
establish terminal coverage for a later failed invocation.

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
refused. There is no standalone reassessment command.

After a successful CLI exit, quality validation reads the exact owned native
session before its temporary home is deleted. It requires a matching fresh
session, selected and observed assistant models, terminal shutdown, paired
allowlisted tools, in-packet successful views and a final answer. A failed view
does not count as a source read. Missing, corrupt or incomplete events fail the
review without falling back to stdout; rejection by the unchanged 32 MiB reader
limit also fails quality validation.

The reviewer's `validation` record identifies native session events, their byte
digest and record count, and successful process completion. The digest marks
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

Reports show per-attempt correctness, behavioral verdict, accounting coverage,
quality and duration. Aggregates keep exact task revision, arm/skill identity,
harness, image, model/effort, timeout, retry budget and evaluation configuration
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
