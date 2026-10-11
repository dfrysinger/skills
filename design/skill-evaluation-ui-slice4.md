# Skill Evaluation UI Slice 4: Experiments and Distributed Activity

## Status

Design approved. The constraint gate is clear and both reviewer families closed
every material identity, lifecycle, and selection-authority finding.
Implementation begins only from the committed reviewed design.

## Objective

Extend the merged read-only local dashboard so a user can monitor predeclared
treatment experiments and exact known local or cloud activity without
conflating workflow transport, distributed stages, evaluator correctness,
recovery, effective results, or cost coverage.

## User value

The campaign and task views will answer:

- What experiment is being run, what is its hypothesis, which arms are controls
  or treatments, how many repetitions were planned, and what rule will select a
  finalist?
- How many attempts are observed locally or in GitHub Actions, and which exact
  task revision, admitted skill snapshot, treatment, repetition, model,
  platform, and location does each attempt belong to?
- Which attempts are planned, locally running, queued, waiting, in progress,
  pending product work, ready for finalization, terminal, missing, invalid, or
  conflicted?
- What was each attempt's first retained outcome, what recovery occurred, and
  which exact terminal result is effective?
- Which outcomes came from evaluator authority, which facts are transport-only,
  and which measurements remain incomplete?
- What did the experiment cost where exact accounting exists, and which
  distributed costs remain unknown?

## Scope

This slice adds:

1. a strict versioned experiment/activity record family in the existing
   corpus-local writer-scoped journal;
2. immutable predeclared experiment plans containing exact treatments,
   controls, attempts, repetitions, ranking metrics, and selection rules;
3. a frozen experiment-plan fingerprint carried through the existing
   distributed execution matrix and receipts before dispatch;
4. a bounded extension of the existing read-only observer that validates exact
   known workflow runs and their exact named matrix jobs;
5. immutable coordinator-owned dispatch bindings connecting one experiment
   plan and its exact attempts to one generated Actions run and expected jobs;
6. bounded publication of validated distributed stage, terminal-result, and
   recovery-lineage projections produced from existing immutable receipts;
7. additive campaign, task, index, attention, cost-coverage, and availability
   projections;
8. responsive read-only experiment and activity views; and
9. deterministic, installed-plugin, browser, visual, and dual-review proof.

## Non-goals

- Dispatching, retrying, canceling, configuring, pausing, resuming, selecting,
  promoting, publishing, or deleting work from the browser.
- A dashboard GitHub client, credential access, workflow discovery, repository
  discovery, organization discovery, capacity checks, quota checks, or polling
  service.
- A mutable result database, queue, scheduler, worker coordinator, lock
  service, or copied second source of evaluator truth.
- Importing or serving raw retained archives, release assets, candidate output,
  repositories, worktrees, logs, transcripts, package payloads, hidden graders,
  judge evidence, credentials, or arbitrary artifact paths.
- Inferring evaluator PASS from workflow status, stage status, conclusion,
  preflight readiness, session prose, treatment prose, or candidate output.
- Inferring monetary cost, AI credits, tokens, premium requests, or runner
  price from model names, timeout, artifact bytes, image bytes, workflow time,
  or platform.
- Replacing a first outcome with a recovery run or effective result.
- Causal attribution, release qualification, promotion, or generalization
  beyond displaying the predeclared rule and deterministic experiment
  selection.
- Ablation qualification, retained-rule accounting, or size minimization.
- Raw evidence drill-down, pagination, virtualization, or a new API route
  without measured demand.
- Adding experiment flags or bindings to local evaluator runs, suites,
  `attempt.json`, lifecycle records, or local history. Existing local activity
  remains visible but is not claimed as a predeclared Slice 4 experiment arm.

## System classification

This is **systemic and security-sensitive**. It extends a persistent
multi-writer protocol, binds local and remote activity to immutable evaluation
identity, and projects private-repository transport metadata. The design
requires fail-closed typed readers, exact writer ownership, no credential path
through the dashboard, an independent constraint challenge, dual design
review, installed-plugin proof, and dual implementation review before landing.

## Decision hierarchy

1. Exact user decisions in
   `design/skill-evaluation-ui-slice4-decisions.json`.
2. The Foundation authority and security boundaries in
   `design/skill-evaluation-ui.md`.
3. The Slice 3 immutable snapshot, passing, and task-progress contracts in
   `design/skill-evaluation-ui-slice3.md`.
4. Frozen evaluator artifacts for local correctness, identity, and accounting.
5. Validated distributed execution matrices, stage receipts, retained archive
   identities, completion records, and effective results.
6. Validated exact-known Actions observation snapshots for transport metadata
   only.
7. Validated Slice 4 workflow declarations and activity records.
8. Existing live session and local-attempt records.
9. Explicit unavailable, unknown, incomplete, stale-source, malformed, or
   conflicted state.

No lower source may upgrade a higher source.

## Constraint provenance and reframe gate

| Constraint | Source | Binding interpretation | Revisit condition |
|---|---|---|---|
| Browser is read-only | User: `"read only"` | No browser mutation endpoint or execution control | User explicitly authorizes a separately designed control plane |
| Many sessions may be active | User: `"yes but there could be many active session"` | Writer-scoped append-only records; no shared mutable current record | Evaluation ownership becomes single-writer |
| Show parallel local/cloud runs and experiments | Original user request | Exact bounded activity and experiment projections are in scope | User removes cloud or experiment visibility |
| Credits display as cents | User: `"credits are cents but agreed"` | Preserve native coverage; display known credits as cents | Authoritative billing replaces the convention |
| Observe only exact known Actions runs and jobs | Existing observer contract, user-visible active cloud requirement, and Foundation boundary | Extend the existing external observer only for exact jobs under caller-known runs; no broad discovery or dashboard network client | A separately reviewed product requirement needs discovery |
| Workflow success is not evaluator success | Existing evaluator and observer contracts | Transport and correctness remain separate fields | Evaluator authority changes |
| Preserve first outcomes | Distributed campaign and parallel-treatment contracts | Recovery is lineage and cannot overwrite original outcomes | Evaluation policy explicitly changes |
| No invented distributed cost | Distributed artifact trace | Resource metadata is not billing data | A canonical distributed accounting artifact exists |
| Reuse additive extension compatibility | Merged Slice 3 contract | New namespace; old readers ignore it and new readers isolate malformed siblings | Existing extension machinery proves insufficient |
| No new activity endpoint without measured demand | Pass-1 challenge | Reuse current campaign/task projections | Measured payload or latency evidence proves the route necessary |
| Global counts stay inside the existing global capability | Foundation global-overview contract and current index projection | Add only bounded registered-campaign counts; no repository or source metadata | Global overview authorization changes |
| Slices 5 and 6 remain separate | Foundation design | No ablation qualification or raw evidence browsing | A re-reviewed dependency proves inseparability |

Reframe is required before implementation if the design would need to:

- give the dashboard GitHub credentials or network observation authority;
- discover workflows, repositories, organizations, accounts, capacity, or
  unknown runs;
- copy raw retained artifacts or evaluator results into a dashboard-owned
  database;
- join records by display names, timestamps, branch similarity, path
  similarity, model-family guesses, or mutable workflow labels;
- infer correctness, qualification, causal effect, promotion, or cost from
  transport metadata;
- rewrite or hide a first outcome after recovery;
- expose arbitrary paths, archives, package data, repositories, candidate
  output, raw logs, or hidden evidence;
- add a new route, queue, poller, background observer, or framework mainly to
  preserve an implementation choice; or
- require ablation or raw evidence mechanics for Slice 4.

**Current status: `CLEAR`.** Round-1 design review proved that the prior
run-only observation and matrix identity could not satisfy exact active
attempt, model, platform, or skill-snapshot joins. The revised design adds an
exact dispatch/job observation contract and versioned distributed identity
contract. A focused challenge narrowed and cleared the exact delta, including
writer ownership and private-metadata checks. Round-2 review then proved that
a caller-authored terminal selection could bypass eligibility. A second
focused challenge retained the deterministic evaluator but closed its inputs
over enumerated evaluator-owned fields, coverage predicates, disqualifiers,
metric names, value types, and directions. Both reviewer families completed
finding-scoped closure with no remaining finding.

## Reuse contract

### Reused unchanged

- Foundation service lifecycle, campaign registration, capabilities, session
  state, local attempt lifecycle, hidden-evidence refusal, and index routes.
- Slice 3 snapshots, lineage, evaluator-backed passing, task progress,
  comparison, task detail, and attention projection.
- `evaluation_history.history()` local result and accounting authority.
- `observe_campaign_runs.py` exact binding, output, exclusive publication,
  completeness, non-atomicity, and refusal semantics for legacy run-only
  snapshots.
- `distributed_campaign.py` matrix, receipt, retention, recovery, completion,
  and effective-result validation.
- Existing dashboard writer directories, canonical JSON, exclusive creation,
  idempotency, conflict retention, typed safe sources, and sibling isolation.
- Existing static HTML/CSS/JavaScript application and campaign/task routes.

### Extended

1. `dashboard_state.py` adds a separate
   `extensions/experiment-activity-v1/` namespace and strict record variants.
2. `dashboard_cli.py` adds trusted publication adapters that accept explicit
   owner-selected files, call the existing validators, and persist only bounded
   typed projections. Source paths never enter browser projection.
3. `distributed_campaign.py` adds a versioned experiment-aware matrix and
   receipt contract carrying the plan fingerprint, candidate model, exact
   treatment content identity, target-skill identities, platform, and route
   through every stage and terminal result.
4. `observe_campaign_runs.py` adds an exact-known-jobs mode that validates
   caller-frozen run bindings and expected named jobs without discovering
   repositories, workflows, or unknown runs.
5. `dashboard_projection.py` joins declarations, existing local activity, distributed
   stages/results, and cloud observations by exact identity.
6. One pure selection evaluator validates eligibility and computes the
   allowlisted ordered metrics, disqualifiers, ties, and terminal result from
   immutable plan/result projections; session prose cannot choose the result.
7. The existing campaign and task UI render compact experiment and activity
   sections. The index adds observed local/cloud counts with explicit as-of and
   non-atomic labels.
8. `SKILL.md` documents declaration, dispatch binding, distributed plan
   binding, observation publication,
   and distributed-result publication at the existing workflow boundaries.

### Newly required

Only one new dashboard protocol namespace and additive versions of two existing
artifact contracts are required. No new process, service, endpoint, database,
dashboard cloud client, dependency, or frontend build step is introduced.

## Artifact model

All Slice 4 records use:

```text
CORPUS/.skill-evaluation-ui/events/<sha256(canonical-writer)>/
  extensions/experiment-activity-v1/<event-id>.json
  extensions/experiment-activity-v1/conflicts/...
```

The envelope reuses the Slice 3 extension shape:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "event_type": "experiment_declared",
  "campaign_id": "uuid",
  "writer": {
    "kind": "session",
    "id": "copilot-session-uuid",
    "generation": "opaque"
  },
  "observed_at": "ISO-8601 source time",
  "recorded_at": "ISO-8601 publisher time",
  "subject": {},
  "payload": {}
}
```

The namespace is additive. Foundation and Slice 3 readers ignore it. Slice 4
enumerates it independently, validates exact field sets, isolates malformed
records, preserves identical-byte idempotency, and retains differing-byte
reuse as a visible conflict.

### Writer ownership

Record variants have non-overlapping writer kinds:

| Variant | Required writer kind |
|---|---|
| `experiment_declared` | `session` |
| `cloud_dispatch_bound` | `distributed_coordinator` |
| `cloud_transport_observed` | `cloud_observer` |
| `distributed_stage_recorded` | `distributed_coordinator` |
| `distributed_result_recorded` | `distributed_coordinator` |
| `experiment_selection_recorded` | `experiment_evaluator` |

The validator refuses every variant written by another kind. A writer may
publish only its own immutable event IDs. Identical publication by the same
writer is idempotent; reuse with different bytes is retained as that writer's
conflict. Records from different authorized writers remain separate and are
reconciled only through exact subject identity; no writer can replace another
writer's record.

### `experiment_declared`

One trusted workflow session publishes one immutable plan before any bound
attempt may execute or be admitted:

- `experiment_id`;
- bounded title and summary;
- exact admitted `snapshot_id`;
- exact case IDs and frozen case revisions;
- exact candidate model, timeout, target OS, architecture, and route;
- treatments with `treatment_id`, role, hypothesis, snapshot or treatment
  identity, exact content fingerprint, exact target-skill identities, and safe
  provenance identifiers;
- exact distributed attempts with `attempt_id`, case tuple, treatment ID,
  repetition, platform, model, and snapshot ID;
- ranking metrics, direction, eligibility requirements, tie-breakers, and
  disqualifiers;

Unknown fields, duplicate IDs, unsupported roles, mismatched case/snapshot
references, unregistered skills, missing controls, zero repetitions, and
inconsistent tuples are refused. Text is bounded display metadata and never
correctness authority.

An experiment is content-bound by a fingerprint over all identity-bearing plan
fields. Reusing its event or experiment ID with different bytes conflicts.

### Distributed plan and execution identity

The declaration's canonical fingerprint is computed before dispatch.
Experiment-aware packages use execution-matrix schema version 2. Its top level
carries `experimentPlanSha256`; each attempt additionally carries:

- `candidateModel`;
- `treatmentFingerprint`;
- sorted `targetSkillIdentities` with exact skill name and evaluator
  fingerprint;
- `targetOs` and `architecture`;
- route and grading-route constraints derivable from the frozen case.

The canonical v2 execution identity is defined once and reused by every
validator:

```text
experimentPlanSha256
attemptId, caseId, caseRevision, treatmentId, repetition
candidateModel, candidateTimeoutSeconds
treatmentFingerprint
targetSkillIdentitiesFingerprint
targetOs, architecture, route, gradingRoute
packageArchiveSha256, candidatePackageArchiveSha256, packageManifestSha256
```

`targetSkillIdentitiesFingerprint` is the canonical fingerprint of the sorted
skill-name/evaluator-fingerprint pairs. Matrix jobs carry the attempt-level
fields and the dispatch plan adds the package identities. Candidate, stage,
preflight, product, terminal, completion, and recovery records carry the same
canonical identity object or its fingerprint plus the complete source object
needed to recompute it. One shared validator recomputes and compares canonical
values at every boundary; copied display labels never establish identity.

The package manifest schema version 2 contains one treatment inventory keyed by
`treatmentId`, with the exact treatment content fingerprint and sorted
target-skill identities. Each inventory entry contains safe package-relative
regular-file paths and SHA-256 values. `package_distributed_campaign.py`
verifies those exact files before creating either archive, rejects symlinks,
escapes, missing files, extra identity fields, and digest mismatches, and
requires the candidate-safe and full package manifests to remain identical.

The private package runtime reports the exact loaded candidate model, treatment
fingerprint, and target-skill identities in the candidate receipt. The public
carrier passes the declared candidate model into the runtime and validates all
three returned identities against the matrix and package inventory before
accepting the stage.

`distributed_campaign.py` carries the plan fingerprint and these exact
execution fields through:

- the frozen dispatch plan and named matrix jobs;
- every stage invocation and dispatch receipt;
- candidate, stage, preflight, product, and terminal receipts;
- completion and effective-result reconciliation.

Legacy schema-version-1 campaigns remain executable and visible as ordinary
distributed activity, but their plan, model, treatment-content, and skill
snapshot joins are explicitly unavailable. They cannot contribute to a Slice 4
experiment.

A missing or changed plan, model, treatment, target-skill, platform, or route
identity refuses dispatch, stage admission, or reconciliation. The dashboard
accepts an experiment result only when the declaration snapshot's exact target
skill identities match the package treatment inventory, matrix, candidate
receipt, and terminal receipt. This proves predeclaration and executed identity
through content binding rather than copied labels or timestamps.

Existing local runs remain visible through Foundation activity and immutable
history. They may be grouped by their existing exact task, skill, treatment,
model, and platform fields, but they do not join a Slice 4 experiment and do
not contribute to its repetitions or selection.

### `cloud_dispatch_bound`

The trusted coordinator that dispatches the existing workflow publishes one
immutable binding after GitHub allocates the run and before observation:

- experiment ID and fingerprint;
- package, matrix, and workflow revision identities;
- exact repository ID and full name;
- exact workflow ID and safe workflow path;
- head SHA, head branch, event, run ID, and run attempt;
- the exact expected matrix-job names generated from stage kind and
  `attemptId`; and
- the attempt IDs and stage kinds each job represents.

The workflow template gives every matrix job an explicit deterministic name,
for example `macos-stage / <attemptId>` and
`linux-final / <attemptId>`. The trusted publisher consumes the private repository, workflow, run, branch,
and source-revision fields only to validate the dispatch receipt. The persisted
dashboard record stores:

- a canonical `runBindingFingerprint` over those complete private fields;
- the experiment and plan fingerprints;
- the safe attempt/stage/job-name mapping; and
- an opaque source ID.

It does not persist repository names, workflow IDs or paths, branch names, run
IDs, source revisions, URLs, or artifact locators. A later observation
publisher recomputes the same binding fingerprint from its owner-selected
source and matches it before publication. Browser projection exposes only the
opaque source ID.

The dispatch planner is the single job-name generator. From the frozen route
for every attempt it emits the complete expected workflow job-name set,
including the static plan job and every applicable stage, product,
finalization, or resume job. The workflow template consumes those exact names;
the coordinator binding copies that frozen set. No publisher independently
reconstructs names.

The immutable uniqueness key is experiment fingerprint plus repository ID,
workflow ID/path, head SHA, run ID, and run attempt. One run may bind many
attempts and stages. The same key may have only one immutable binding.
Identical publication is idempotent; different bytes, duplicate job names,
duplicate attempt/stage pairs, wrong workflow revision/path, run-attempt
substitution, or rebinding one run or attempt become visible conflicts and
cannot authorize observation.

### `cloud_transport_observed`

A trusted local publisher accepts one complete exact-known-jobs output created
by `observe_campaign_runs.py`. It never invokes `gh`. The observer:

- validates the exact caller-known workflow run binding;
- performs bounded GETs only for that run and the complete jobs listing for
  that run;
- projects run metadata plus job ID, exact name, status, conclusion, run ID,
  run attempt, head SHA, started/completed timestamps, and provenance;
- requires exact set equality with the complete expected job-name set from the
  dispatch binding;
- rejects missing, extra, duplicate, renamed, rerun, or mismatched jobs; and
- writes one complete immutable snapshot or no output.

For the complete snapshot the dashboard publisher:

1. validates the observer schema and exact output field set;
2. loads one non-conflicted `cloud_dispatch_bound` record;
3. revalidates repository, run, workflow, SHA, branch, event, attempt, and
   caller-frozen workflow path;
4. maps every exact job name to its declared attempt and stage;
5. stores one immutable batch record containing only bounded metadata required
   for the dashboard;
6. preserves `non_atomic`, coverage, provenance, call count, projected response
   bytes, and client wall seconds;
7. excludes credentials, actors, URLs, workflow inputs, artifacts, logs, and
   source filesystem paths.

The persisted observation record also omits repository, workflow, branch,
run, source-revision, URL, and path values. It carries the matched
`runBindingFingerprint`, safe job-name/attempt/stage mappings, transport
statuses, timestamps, coverage, accounting, and an opaque source ID.

The record carries a fingerprint of the complete observer snapshot and each
exact source observation index. Projection fans the batch out by attempt only
after validating the complete record. Interruption exposes no partial snapshot.

Run and job statuses are exactly `queued`, `in_progress`, `completed`,
`waiting`, `requested`, or `pending`. A completed conclusion remains transport
metadata.
The UI says "observed as of" rather than "currently" because the source is
non-atomic and does not prove state after collection.

### `distributed_stage_recorded`

A trusted distributed coordinator publisher accepts an owner-selected,
checksum-verified retained artifact and existing validated stage receipt. It
stores only:

- exact experiment and five-field attempt identity;
- package and candidate-package identities;
- execution identity: plan fingerprint, candidate model, treatment fingerprint,
  target-skill identities, timeout, target OS, architecture, route, grading
  route, image identity, and dependency identity;
- stage kind and status;
- `terminal`;
- `candidateRerunRequired`;
- bounded deterministic/product/judge summaries already admitted by the
  distributed validator;
- retention-manifest digest and source artifact digest; and
- safe source identifiers that cannot open an archive or path.

Nonterminal statuses include `PENDING_MACOS_PRODUCT`,
`PENDING_LINUX_FINALIZATION`, and `READY_FOR_FINALIZATION`.
`READY_FOR_FINALIZATION` retains `qualification: NOT_EVALUATED`.

### `distributed_result_recorded`

The same coordinator may publish a validated terminal receipt:

- terminal status `PASS` or `FAIL`;
- exact candidate, deterministic, product, and judge summaries;
- exact package and execution identities;
- exact candidate model, treatment fingerprint, target-skill identities,
  platform, and route;
- first retained stage identity;
- optional `sourceLineage` with source run ID, source revision, retained archive
  digest, and candidate reconstruction;
- `candidateRerun: false` for recovered paths; and
- effective-result identity.

The original first stage remains separately visible. A terminal or recovered
result never overwrites it. The effective result points to both the terminal
receipt and any source lineage.

### `experiment_selection_recorded`

Selection is computed, not session-authored. A deterministic trusted
`experiment_evaluator` publisher loads the immutable declaration and exact
terminal results, then applies the declaration's machine-readable rule.

The rule may use only an allowlisted set of result-derived metrics:

- valid terminal repetition count;
- terminal PASS count or rate;
- deterministic target and regression pass count or rate;
- product pass count or rate;
- unanimous behavioral PASS count or rate;
- invalid or missing attempt count; and
- judge disagreement count.

Metric names are a closed enum. Count values are nonnegative integers. Rate
values are canonical `{numerator, denominator}` integer pairs and are compared
without floating-point conversion. Each ordered metric declares only ascending
or descending direction.

Eligibility may reference only these evaluator-owned field enums:

- terminal status;
- deterministic target pass;
- deterministic regression pass;
- product pass; and
- independent behavioral verdicts.

Coverage predicates are limited to all planned attempts terminal, minimum valid
repetitions per treatment, and presence of one of those enumerated fields.
Disqualifiers are limited to invalid attempt, missing required field,
deterministic regression failure, product failure, and judge disagreement over
a declared integer bound. Unknown metrics, field names, formulas, arbitrary
JSON paths, display identifiers, treatment names, session prose, or selection
record data are refused. Ties after every declared metric yield
`no_selection`; treatment display text or IDs never break a tie.

Only after recomputing complete eligibility and the exact rule outcome may the
publisher create one terminal selection:

- exact experiment fingerprint;
- selected and eliminated treatment IDs;
- exact attempt/result source IDs used;
- recomputed per-treatment metric values and rule outcome;
- uncertainty or no-selection reason; and
- status `selected` or `no_selection`.

`selectedTreatmentId`, `eliminatedTreatmentIds`, metric values, and reasons are
outputs of the deterministic evaluator only and are never accepted as caller
inputs.

The publisher verifies every referenced attempt and result belongs to the
experiment, recomputes eligibility, metric values, disqualifiers, ordering,
ties, and the selected/no-selection outcome, and requires the exact
selection-rule identity. A premature invocation writes no terminal record and
returns explicit `selection_incomplete`. The dashboard labels an admitted
record "experiment selection". It is not causal attribution, qualification,
promotion, release, or passing authority.

Absence of a terminal selection is derived as `pending` or `incomplete` from
attempt and eligibility coverage; no mutable progress selection is stored. The
selection subject is the exact experiment fingerprint plus selection-rule
identity. Identical publication is idempotent. Different terminal selections,
or terminal selections from different writers, remain explicit conflicts; no
timestamp, writer priority, or latest-wins rule chooses one.

Selection projection precedence is:

1. malformed or foreign records are isolated and do not affect valid siblings;
2. no valid terminal record yields derived `pending` or `incomplete`;
3. one unique valid terminal record yields `selected` or `no_selection`;
4. identical duplicate bytes remain idempotent; and
5. multiple distinct valid terminal records yield `conflicted` and no selected
   treatment.

## Projection and joins

Every join is exact:

| Projection | Exact join |
|---|---|
| Experiment | campaign ID + experiment ID + experiment fingerprint |
| Treatment | experiment fingerprint + treatment ID |
| Attempt | experiment fingerprint + attempt ID + case ID/revision + treatment ID + repetition |
| Skill | admitted snapshot ID and validated evaluator skill identity |
| Local lifecycle | existing evaluator-owned task, skill, treatment, model, and platform tuple; never an experiment join |
| Cloud transport | attempt tuple + exact known Actions run binding |
| Cloud job | dispatch binding + exact run + exact deterministic job name |
| Distributed stage | attempt tuple + plan + package + model + treatment + target-skill + platform + route + retained artifact identity |
| Effective result | attempt tuple + terminal receipt + source lineage |
| Selection | experiment fingerprint + treatment/result source IDs + selection-rule identity |
| Cost | exact evaluator population/attempt identity and measurement coverage |

No join uses display text, timestamps, branches without the full run binding,
directory names, artifact-name similarity, process state, or path similarity.

### Experiment state

The projection returns:

- declaration identity and availability;
- treatments and roles;
- planned, observed, terminal, valid, invalid, and missing distributed attempt counts;
- repetition progress;
- predeclared rule and deterministic selection state;
- per-treatment outcome distributions;
- first outcomes and effective outcomes separately;
- uncertainty and incomplete reasons; and
- exact known cost with coverage.

No single lucky attempt becomes a winner. A treatment is not displayed as
selected unless an admitted selection record exists. A selection is not
displayed as qualified or released.

### Distributed activity

Each row separately exposes:

- location: local or cloud;
- lifecycle authority: evaluator, Actions observation, distributed stage, or
  immutable terminal result;
- transport status and conclusion;
- stage status and terminal flag;
- evaluator result when independently available;
- first-outcome identity;
- recovery lineage and effective-result identity;
- task, revision, skill snapshot, treatment, repetition, model, platform, and
  route;
- observation as-of time, explicit non-atomicity, and coverage; and
- safe source identifiers.

Campaign and index counts distinguish:

- local active evaluator attempts;
- cloud attempts observed nonterminal;
- cloud attempts observed completed but awaiting evaluator/final receipts;
- distributed attempts pending product/finalization;
- terminal effective results; and
- invalid, missing, or conflicted records.

The UI never labels an Actions observation as live after its as-of time and
never treats confirmed observation as confirmed current state.

### Cost

Existing local work continues to reuse evaluator accounting. Distributed
experiment attempts without canonical accounting contribute unknown coverage,
not zero. Campaign cost and experiment coverage display:

- exact/observed AI credits and the user-convention cents transform;
- premium requests separately;
- role/subrole totals where available;
- known attempt count versus total attempt count; and
- explicit incomplete coverage.

Model, timeout, image bytes, dependency bytes, artifact bytes, workflow time,
and platform remain resource facts only.

## UI

The campaign route adds:

- an experiment summary strip;
- treatment cards showing role, hypothesis, planned/observed repetitions,
  outcome distribution, cost coverage, and deterministic selection state;
- a distributed activity table grouped by task, snapshot, treatment, model,
  platform, and location;
- separate transport, stage, evaluator, first-outcome, recovery, and effective
  result columns;
- "observed as of" and non-atomic badges for cloud metadata;
- an experiment attention section for missing attempts, incomplete
  observations, identity mismatches, conflicts, missing effective results,
  judge disagreement, and incomplete accounting.

The task route adds the experiment attempts relevant to that exact case
revision and preserves the existing lineage and progress sections.

The global index adds compact observed local/cloud counts and freshness only
inside the existing explicit global-overview capability. It returns registered
campaign summaries only and omits experiment text, repository identity,
workflow paths, source metadata, and result detail.

Legacy campaigns and campaigns without Slice 4 records show:

- `Experiments unavailable`
- `Cloud activity unavailable`

Existing Slice 3 content remains fully usable.

## Failure model

- A declaration is malformed, conflicting, post-hoc, or references unknown
  snapshots, cases, treatments, or attempts.
- A distributed execution matrix or receipt omits or changes the pre-launch
  experiment plan fingerprint.
- A package, matrix, candidate receipt, stage, or terminal result disagrees on
  candidate model, treatment bytes, target-skill identities, platform, or
  route.
- A workflow run lacks an immutable coordinator binding, one run or attempt is
  rebound, or an observed job is missing, extra, renamed, duplicated, or mapped
  to the wrong attempt.
- An Actions snapshot is incomplete, non-atomic, old, malformed, or
  bound to the wrong repository, workflow, SHA, branch, event, attempt, or
  path.
- A distributed stage or result has a missing or mismatched package, matrix,
  attempt, dispatch, retained archive, receipt, or source-lineage identity.
- A workflow succeeds while evaluator or product evidence failed or is absent.
- A recovery receipt attempts to replace or hide the first outcome.
- A selection record changes the declared rule, references foreign attempts,
  or claims qualification.
- Missing accounting is rendered as zero or distributed resource metadata is
  converted to money.
- One corrupt record hides valid records from another writer.
- Browser projection exposes a source path, repository secret, release locator,
  artifact URL, raw log, archive, candidate data, or hidden evidence.

Every failure remains explicit and local to the affected record, experiment,
or attempt. It never upgrades state or suppresses unrelated valid records.

## Rollback

Rollback removes Slice 4 producers and projections while leaving the versioned
extension directory in place. Foundation and Slice 3 readers ignore it.
Existing evaluator, distributed campaign, observer, local dashboard, lineage,
task progress, and completed-history behavior continue unchanged.

Local evaluator runs and history are unchanged by Slice 4 and continue to
render after rollback.

## Check contract

| Invariant | Setup and trigger | Required pass signal | Required failure signal |
|---|---|---|---|
| Plan is immutable and predeclared | Publish a valid declaration, republish identical bytes, then reuse IDs with changed bytes | First publish succeeds; identical publish is idempotent | Changed bytes become a visible conflict and cannot bind an attempt |
| Writer ownership is enforced | Attempt every record variant with each allowed and disallowed writer kind; republish and cross-write event IDs | Only the designated writer kind publishes; same-writer identical bytes are idempotent | Unauthorized kinds refuse and no writer replaces another writer's record |
| Plan identity is exact | Change one case revision, snapshot, treatment, repetition, model, platform, or selection-rule field | Fingerprint changes and only the exact plan joins | Cross-plan or incomplete joins are unavailable |
| Plan is bound before distributed work | Freeze a plan and matrix, then mutate or omit the plan fingerprint at dispatch, stage, receipt, and reconciliation | Exact fingerprint survives every stage | Every mismatch refuses before dispatch or reconciliation |
| Executed identity matches the plan | Mutate or omit each canonical v2 identity field independently in the package, matrix, dispatch plan, candidate receipt, stage, preflight, product, terminal, completion, and recovery record | One shared canonical identity recomputes identically at every boundary and matches the admitted snapshot | Each isolated mutation or legacy v1 record refuses the experiment join |
| Ordinary local runs remain compatible | Read current and older local fixtures | Existing activity, result, and history semantics are unchanged | No experiment membership is inferred |
| Dispatch binding is immutable and complete | Bind one multi-attempt run, republish identical bytes, then rebind the run, attempt, job name, workflow, or plan | Identical publication is idempotent and every expected job is uniquely mapped | Rebinding or duplicate mapping conflicts and cannot authorize observation |
| Observation is exact-known only | Publish complete listing and direct-known snapshots with terminal and nonterminal statuses | Exact bindings render with as-of, coverage, and non-atomic labels | Partial, malformed, mismatched, unknown-status, or wrong-path inputs publish nothing |
| Observation publication is atomic | Interrupt publication after validating a subset of one complete snapshot | No Slice 4 observation record is visible | No partial per-attempt snapshot can appear |
| Exact jobs drive cloud attempt state | Generate the complete static and matrix job set for a known run, then observe queued, in-progress, completed, missing, extra, renamed, duplicate, wrong-run, and rerun states | Observed job-name set equals the frozen dispatch set and exact attempt/stage jobs map uniquely | Any set or binding difference refuses the whole snapshot |
| Workflow status cannot create PASS | Observe completed/success with no evaluator receipt | Transport completion is visible | Evaluator result remains unavailable and campaign passing is unchanged |
| Distributed stages preserve first outcomes | Publish pending stage, terminal result, and resumed result with source lineage | All records remain visible; effective result points to lineage | Recovery cannot overwrite first stage or set candidate rerun true |
| Receipt authority is exact | Mutate attempt, package, route, archive, stage, result, or lineage identity | Exact record joins | Mismatch is isolated as invalid |
| Selection is computed and non-authoritative | Recompute one eligible selection, then alter a source metric, ordering direction, disqualifier, tie, selected treatment, or add release/qualification fields | The deterministic publisher emits only the exact recomputed selected/no-selection result and labels it experiment selection | Every altered or unsupported result is refused |
| Premature selection cannot suppress incomplete state | Invoke selection before required repetitions, results, fields, coverage, or disqualifier evaluation are complete | No terminal record is written and projection remains derived pending/incomplete | A syntactically valid premature terminal record is refused or isolated invalid |
| Selection lifecycle is unambiguous | Exercise no selection, incomplete eligibility, one terminal selection, identical republication, and conflicting terminal selections | Pending/incomplete is derived; one exact terminal selection renders; identical publication is idempotent | Conflicting terminal selections remain conflicted and no timestamp or writer priority chooses a winner |
| Selection errors remain local | Mix valid terminal selections for one experiment with malformed and foreign records for other experiments | Valid sibling experiments retain their own derived or terminal state | Malformed/foreign records are isolated and cannot create or suppress a selection |
| Cost coverage is honest | Combine exact local accounting with distributed attempts lacking accounting | Known totals and attempt coverage are displayed | Missing distributed cost is not zero and resource bytes are not money |
| Sibling isolation holds | Mix valid, malformed, conflicting, and foreign records from multiple writers | Valid siblings and existing Slice 3 state remain visible | Bad records are individually unavailable/conflicted |
| Private binding metadata stays publisher-side | Seed unique markers in repository/workflow IDs and names, paths, branches, run IDs, source revisions, URLs, artifact locators, and publisher input paths | Publishers validate sources and persisted records retain only binding fingerprints, safe mappings, and opaque IDs | Markers never appear in extension records, projection JSON, global counts, API, HTML, or browser-visible source identifiers |
| Hidden and arbitrary data stay absent | Seed marker strings in logs, archives, candidate and judge files | Safe bounded labels render | Markers, credentials, raw paths, URLs, bytes, and hidden content never appear in API or HTML |
| Existing routes remain authorized | Request index, campaign, task, and session routes with correct, wrong, missing, and replaced-generation capabilities | Correct scope returns only its safe projection | Other requests fail with existing stable refusal codes |
| Global counts preserve scope | Open the explicit global overview and campaign-scoped capabilities against multiple registered campaigns | Overview returns bounded counts; campaign capability returns only its campaign | No private repository, workflow, experiment text, or cross-campaign detail leaks |
| UI separates authorities | Render queued, workflow-success, pending-stage, failed product, recovered PASS, invalid, legacy, and incomplete-cost fixtures | Each state has a distinct label and source | No green styling or aggregate conflates transport and evaluator state |
| Responsive behavior holds | Render desktop dark, mobile light, dense experiment, recovery, invalid, and legacy fixtures | Content remains readable with no page-level overflow | No hidden columns, clipped controls, or inaccessible authority labels |

## Acceptance criteria

1. A trusted workflow can declare one immutable experiment with controls,
   treatments, exact attempts, repetitions, and a selection rule.
2. The exact plan fingerprint, candidate model, treatment content,
   target-skill identities, platform, and route are frozen before dispatch and
   remain identical through the package, matrix, candidate receipt, stages,
   terminal receipts, and reconciliation.
3. One complete exact-known Actions snapshot projects terminal and nonterminal
   run and exact job transport status through an immutable dispatch binding
   without creating evaluator PASS.
4. One distributed attempt shows first stage, terminal or recovered result,
   source lineage, and effective result without replacing the original.
5. Campaign and task views group existing local activity and experiment-bound
   cloud activity by exact task revision, admitted skill snapshot, treatment,
   model, platform, and location; cloud experiment rows also show repetition.
6. Experiment outcomes, deterministic selection, evaluator result, transport, stage,
   recovery, and release/qualification authority remain visibly distinct.
7. Cost totals include only authoritative accounting, display known credits as
   cents, preserve premium requests separately, and mark distributed gaps
   incomplete.
8. Malformed, partial, mismatched, conflicting, cross-campaign, unsupported, or
   stale-source records fail closed without hiding unrelated valid state.
9. No dashboard route exposes credentials, cloud tokens, broad discovery,
   private release locators, arbitrary paths, raw archives, logs, candidate
   output, or hidden evidence.
10. Foundation, Slice 3, legacy, unavailable, dark, light, mobile, dense,
    recovery, invalid, and incomplete states remain usable.

## Current baton

- **Workspace:**
  `/Users/dfrysinger/.copilot/session-state/6f7726ad-c851-4da9-bd16-ffbd015dd0f1/files/skill-eval-ui-slice4-worktree`
- **Branch:** `dfrysinger/skill-eval-ui-slice4`
- **Base:** `898ae893b59219a0640e90d6d7365fc13b6d8780`
- **Reviewed design commit:** `ba70ab6da30d8cdf29249ac5d326861945ea71e8`
- **Critical path:** authority-repair proof -> implementation review -> landing
  -> merged-byte proof
- **Phase:** authority-boundary repair
- **Implementation gate:** open
- **Integrated implementation commits:**
  - `cea9c1e` experiment activity state and deterministic selection
  - `91c6864` distributed execution identity and exact-known observation
  - `3487cc1` campaign/task/index projection and dashboard UI
  - `f0ab2971ca2285b463363d59026ae71dc423dfbb` terminal selection CLI
    repair found by installed proof
- **Superseded proof:** the `f0ab297` installed candidate and its
  `sha256:d6330e1508bbf4fe8e5b80f8fdad23aa42cf60954cc5b85adc14555740d289d9`
  receipts are stale after implementation review found a generic importer
  authority defect.
- **Current validation:** 413 tests pass with 49 skips after replacing the
  generic importer with declaration, dispatch, observation, stage, result, and
  selection adapters. The adapters correlate declared attempts, immutable
  dispatch bindings, exact-known observer output, package and plan identities,
  retained receipts, retained artifacts, and retention manifests. Selection
  discovers all admitted results and fails closed on duplicate or conflicted
  results. Installed proof replay is pending against the committed repair.
- **Last constraint challenge:** the workflow-job, distributed-identity, and
  deterministic-selection deltas returned `NARROW`; all required corrections
  are applied and the gate is `CLEAR`.
- **Event trigger:** exact experiment, cloud-observation, and distributed
  recovery authority boundary
- **Relevant user direction:** `user-slice4-authorization` in the decision
  record
- **Open reframe:** none
- **Design review:** `design/skill-evaluation-ui-slice4-design-review.json`
  records complete Claude Opus 5.5 and GPT 5.6 Terra review. Both applied the
  architecture and scope lens. Finding-scoped closure reports zero unresolved
  material findings.
- **Delegated owners:** both implementation handoffs are integrated and closed.
  The coordinator owns final review, PR, merge, merged-byte verification, and
  schedule cleanup.
- **Next action:** commit the authority repair, reinstall the exact candidate,
  replay all four installed proofs, then run finding-scoped dual review round
  two.

## Definition of Done: Skill Evaluation UI Slice 4

- [x] The focused decision record and sealed architecture-neutral evidence
      packet are complete.
- [x] The independent two-pass constraint challenge permits the exact work
      order.
- [x] Dual design review has no unresolved material finding.
- [x] The reviewed work order and charter are committed before implementation.
- [x] Typed experiment and activity records are implemented with fail-closed
      writer ownership and additive compatibility.
- [x] Distributed plan binding, exact-known Actions observation, distributed
      stage/result projection, first outcomes, recovery lineage, effective
      results, and honest cost coverage are implemented.
- [x] Campaign, task, and index views expose the accepted experiment and
      local/cloud activity states without authority conflation.
- [x] Focused and full deterministic checks pass on one exact candidate.
- [ ] Installed-plugin proof demonstrates one experiment, existing local
      activity, one exact-known cloud observation, one distributed recovery path,
      malformed isolation, legacy behavior, and security refusal.
- [ ] Dark, light, mobile, dense, recovery, invalid, unavailable, and
      incomplete-cost states are visually inspected and accepted.
- [ ] Dual implementation review reports no unresolved material finding
      against the exact proved candidate.
- [ ] The slice is committed, pushed, reviewed in a PR, passes required checks,
      is merged, and actual merged bytes retain the accepted behavior.
- [ ] The baton records final commits, receipts, reviews, PR, merge identity,
      installed identity, and schedule cleanup.
- [ ] Both unattended schedules are stopped and verified absent.
