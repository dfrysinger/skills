# Skill Evaluation Project Dashboard

**Status:** Reviewed work order  
**Lane:** Critical  
**Decision record:** `design/skill-evaluation-ui-project-decisions.json`  
**Decision revision:** `skill-evaluation-ui-project-decisions-r2`  
**Sealed evidence packet:** `design/skill-evaluation-ui-project-evidence.json`  
**Evidence revision:** `skill-evaluation-ui-project-evidence-r1`
**Constraint gate:** `CONTINUE`  
**Dual design review:** `design/skill-evaluation-ui-project-dual-review.md`

## Objective

Replace corpus- and retry-centered dashboard navigation with one explicit,
read-only skill-improvement project view that explains the goal, current skill
revision, task progress, generalization, minimization, cost, active work, and
compact run history.

## User outcome

The first screen answers, in ordinary language:

1. Which skill or skills are being improved?
2. What behavior is the project trying to improve or validate?
3. How many declared tasks pass for one exact current skill revision?
4. What is each task, what is its factual result, and which improvement phase
   is it in?
5. How long and how much work did each conquered task require?
6. Has the improvement transferred to reserved holdout work?
7. Has each new increment been minimized without losing earlier wins?
8. What evaluator runs are active or finished, why were they launched, and did
   they execute or fail in infrastructure?

Runs support those answers. They are not the main navigation hierarchy.

## Non-goals

This change does not:

- launch, cancel, retry, approve, publish, or otherwise control evaluation;
- host the dashboard remotely or expose it outside the loopback service;
- discover arbitrary corpora, repositories, or run directories;
- infer projects, tasks, retries, or holdouts from names, paths, timestamps, or
  suffixes;
- auto-migrate legacy campaigns;
- create a mutable result database or replace immutable evaluator artifacts;
- expose hidden judge references, criteria, prompts, private packets, holdout
  identities, or answer-shaped failure details;
- grant candidates or model-controlled tools dashboard authority;
- monitor custom scripts that bypass supported evaluator launchers;
- invent percentages when a safe validated denominator does not exist; or
- turn full neutral/lean/full ablation into a mandatory step after every task.

## Why this is critical

The work is systemic because it changes shared identity, schema, persistence,
cross-corpus projection, local and distributed lifecycle records, and several
user flows. It is critical because it changes browser authorization scope and
projects data derived from hidden evaluation and holdout boundaries.

The trusted owners are:

- evaluator and distributed-launcher code, which validates inputs, runs work,
  writes immutable evidence, and owns result authority;
- dashboard state code, which validates registrations and append-only records;
- dashboard projection code, which reads only allowlisted typed evidence; and
- the loopback server, which mints scoped read capabilities and serves the
  static client.

The browser is not an owner. It cannot create identity, select a winning
revision, record a phase, classify a failure, or mutate an evaluation.

An optimizing agent may intentionally author project metadata and run goals
through supported evaluator commands. It must never add hidden evidence,
rewrite evaluator results, promote a candidate through browser state, or
exercise holdout authority on its own.

## Constraint provenance

| Constraint | Provenance | Binding evidence | Protected outcome | Revisit condition |
|---|---|---|---|---|
| One explicit project is the primary user object | User outcome | `user-project-first-ux-2026-10-19` | Retries do not become projects | The user requests independent top-level histories for retries |
| Project and task grouping is explicit | User decision | `user-explicit-project-identity-2026-10-19`, `user-explicit-task-case-grouping-2026-10-19` | No false joins | A trusted upstream system supplies a stronger stable identity |
| Supported launchers are the monitoring boundary | User decision and repository capability | `user-supported-launcher-run-boundary-2026-10-19`; `skill_eval.py`; `distributed_campaign.py` | Automatic and reliable lifecycle data | A supported caller cannot use these launchers |
| Result and workflow phase are separate | User decision | `user-separate-task-result-and-phase-2026-10-19` | Passing is not confused with finished | The improvement workflow removes post-pass qualification |
| Per-task delta ablation follows each new conquest | Workflow authority | `cumulative-skill-hill-climb.md`; `ablation-campaign.md` | Each increment stays minimal while earlier wins remain | The governing evaluation workflow changes |
| Whole-skill ablation is conditional | Workflow authority | `ablation-campaign.md` | Normal progress is not blocked on unnecessary rebuilding | Whole-skill ablation becomes a release requirement |
| Holdout data is aggregate-only | Delegated user decision and generalization contract | `recommended-aggregate-only-holdouts-2026-10-19`; `release-qualification-and-generalization.md` | Optimizing work cannot learn reserved cases | Holdout execution moves to a separately authorized human-only product |
| Hidden evidence is never projected | Existing critical boundary | `design/skill-evaluation-ui.md`; dashboard hidden-path tests | Candidate and optimizer isolation | The evaluator establishes a stronger physical isolation and separately reviewed privileged UI |
| Browser capabilities are project-scoped and tab-scoped | Delegated user decision and least privilege | `recommended-project-open-and-capability-2026-10-19` | Refresh works without all-project authority | The platform provides equivalent native secure tab state |
| Legacy data is not inferred or migrated | User decision | `"we dont need backfill support"` | Historical evidence is not misgrouped | A separate explicit migration project is authorized |
| Cost remains exact only when coverage is complete | Existing accounting contract | `measurement.py`; `design/skill-evaluation-ui.md` | Partial spend is not presented as total spend | Billing evidence becomes complete by construction |

No hard capacity limit is architectural. Pagination, virtualization, refresh
intervals, lease duration, retention duration, and maximum project size remain
measured implementation choices. A fixed number requires measured demand or a
platform limit before it enters the contract.

## Reframe gate

**Status: `CLEAR`**

The supported callers already pass through trusted evaluator launchers. The
existing dashboard already owns validated local state, safe projection, and
loopback authorization. The minimum design extends those boundaries. It does
not add a database, broker, watcher daemon, approval system, or generic event
platform.

Return to design before implementation adds another component when:

- a supported run cannot emit lifecycle records from its current launcher;
- project grouping requires reading outside registered corpus and state roots;
- safe task progress requires arbitrary adapter code or raw candidate output;
- holdout status cannot be projected without exposing its identity;
- browser refresh requires persistent or all-project credentials;
- source-specific local and distributed records cannot project the same
  required lifecycle fields;
  or
- repeated fixes only move missing authority from one inferred field to
  another.

An open reframe record must answer:

1. Which visible user outcome is blocked?
2. Which recorded constraint creates the blocker?
3. Which invariant fails if that constraint changes?
4. What is the simplest design without it?
5. Which option has fewer trusted parts and maintenance surfaces?

Implementation stops while the status is `OPEN`.

## Reuse contract

The design extends existing owners rather than adding parallel machinery.

| Existing part | Reused responsibility | Required extension |
|---|---|---|
| `skill_eval.py` | Corpus validation, run creation, snapshots, local outcomes, timing, accounting | Validate project declarations; extend source-owned startup and uncovered pre-attempt failure artifacts |
| `distributed_campaign.py` | Distributed package, execution identity, dispatch, stage, result, accounting | Carry the same project identity and normalized lifecycle |
| `dashboard_state.py` | Create-once registration, append-only writer events, conflict rejection | Register projects and validate additions to existing typed extension records |
| `dashboard_projection.py` | Safe typed joins and authority ordering | Build project, task, aggregate holdout, ablation, and compact run projections |
| `dashboard_server.py` | Loopback service and scoped browser authorization | Add project-scoped routes and capabilities |
| `dashboard_cli.py` | Service lifecycle, registration, browser opening | Open once per project per service generation |
| `dashboard.js` | Static read-only rendering | Render project hierarchy and retain capability in `sessionStorage` |
| Existing snapshot and lineage records | Exact skill identity and source comparisons | Select one explicit project revision for the current scorecard |
| Existing immutable result artifacts | PASS, FAIL, timing, accounting, and artifact authority | Remain final authority over live lifecycle |

The new records are required because existing campaign registration says only
where one corpus lives, session heartbeats describe agent presence rather than
evaluator execution, and final suite artifacts do not describe runs that fail
before completion.

## Canonical hierarchy

```text
Project
├── current exact skill or skill-set revision
├── development and regression task scorecard
│   └── explicit evaluator cases and safe subchecks
├── aggregate holdout qualification
├── per-task delta ablation
├── optional whole-skill ablation
└── project runs
    └── attempts and experiments
```

A campaign remains a storage registration for one corpus. It is no longer a
top-level product object when it belongs to a project.

## Project declaration

Each project-aware corpus contains `evaluation-project.json`. The file is
agent-authored, versioned, validated by the evaluator, snapshotted into every
project-bound run, and registered by dashboard state.

```json
{
  "schema_version": 1,
  "supersedes": null,
  "project_id": "unattended-run-generalization",
  "title": "Improve unattended-run",
  "goal": "Pass all declared tasks and reserved transfer checks with the smallest generalized skill.",
  "target_skills": ["unattended-run"],
  "tasks": [
    {
      "task_id": "resume-after-interruption",
      "title": "Resume after interruption",
      "summary": "Continue unfinished work without losing completed evidence.",
      "qualification": {
        "kind": "all_bound_cases",
        "required_roles": ["development", "regression"],
        "minimum_terminal_repetitions_per_case": 1,
        "required_passes_per_case": 1
      }
    }
  ],
  "case_bindings": [
    {
      "binding_id": "resume-after-interruption-local",
      "case_id": "interrupted-local-run",
      "case_revision": "<sha256>",
      "task_id": "resume-after-interruption",
      "role": "development",
      "safe_progress": null
    }
  ],
  "holdout_requirements": [
    {
      "holdout_set_id": "resume-transfer-v1",
      "summary": "Reserved transfer checks",
      "required_claim": "transfer",
      "task_ids": ["resume-after-interruption"],
      "authority_id": "independent-holdout-evaluator"
    }
  ]
}
```

Rules:

- `project_id`, task IDs, binding IDs, case IDs, and holdout-set IDs use the
  existing safe identifier grammar.
- `title` and `goal` are immutable for one `project_id`. A material title or
  goal change creates a new project.
- Multiple corpora may declare the same project. Immutable fields are
  `schema_version`, `project_id`, `title`, `goal`, and sorted `target_skills`.
- Tasks and case bindings merge by stable ID. Omitting an entry from one
  corpus does not delete an entry declared by another corpus.
- Holdout requirements merge by `holdout_set_id`. Omitting a holdout set from
  one corpus does not delete it.
- A task definition conflicts when the same task ID has different `title`,
  `summary`, or `qualification`.
- A case binding conflicts when the same binding ID has a different `case_id`,
  `case_revision`, `task_id`, `role`, or safe-progress declaration.
- A holdout requirement conflicts when the same holdout-set ID has a different
  `summary`, `required_claim`, sorted `task_ids`, or `authority_id`.
- An immutable project-field conflict makes the project unavailable for
  aggregates. A task conflict makes that task unavailable project-wide and
  excludes its bindings. A case-binding conflict makes the binding unavailable
  and therefore makes its task result unavailable when the declared case set
  is incomplete. A holdout conflict makes that holdout set unavailable.
- Conflicts are set-based and independent of registration order. There is no
  first-writer-wins semantic.
- Validation sorts every set-like array and fingerprints the canonical JSON,
  not source formatting.
- Evaluator validation requires each binding's `case_revision` to equal the
  frozen case manifest in that corpus.
- Every non-holdout case belongs to one declared task and has one role:
  `development` or `regression`.
- True holdout case identities do not appear in this file. An independent
  evaluator binds private cases to the opaque `holdout_set_id`.
- Legacy corpora without this file remain valid but unassigned.
- Every run stores the declaration SHA-256. Results from conflicting project
  declarations do not enter totals.

### Declaration revisions

Agents may add tasks, cases, and holdout requirements or correct metadata
without invalidating old runs:

- `supersedes` is `null` for the first declaration and the immediately prior
  canonical declaration SHA-256 for each later declaration in that corpus.
- Registration archives every accepted canonical declaration by SHA-256 and
  atomically advances that corpus's current declaration pointer.
- The current cross-corpus merge uses only the latest valid declaration from
  each corpus.
- Historical runs resolve through their stored declaration SHA-256 and retain
  their original task meaning.
- A changed declaration without the exact current `supersedes` value is
  rejected with an actionable stale-revision error.
- A revision cannot change `project_id`, `title`, `goal`, or `target_skills`.
  Such a change requires a new project.
- Schema version 1 revisions are additive: every previously declared task ID,
  binding ID, and holdout-set ID must remain present. Omission is rejected and
  never means deletion. Removal requires a later reviewed schema with explicit
  tombstones.
- Changing a task, case binding, or holdout definition affects only runs bound
  to the new declaration revision. Earlier runs do not satisfy the revised
  definition.

Cross-corpus project registration has at least two supported callers. Use one
project-ID lock plus atomic compare/create while merging canonical declarations.
No other project mutation or general coordination service is introduced.

## Exact current revision

Project totals must describe one exact skill or skill-set revision. They never
pool the best result from different candidates.

Reuse existing `lineage_declared` records written by
`dashboard lineage-snapshot`. No second revision-selection event is added.

The current project revision is the unique descendant tip among snapshots with
`published`, `integrated`, or `released` roles that:

- covers every project target skill;
- belongs to a valid lineage graph;
- is comparable through declared parent relationships; and
- has no conflicting incomparable peer.

Role names do not create a temporal precedence. Graph ancestry does. If there
is no unique tip, the current revision is conflicted or unavailable and the
project scorecard does not pool results.

Project lineage reconciliation unions valid snapshot manifests and
`lineage_declared` edges from every compatible registered corpus:

- the same snapshot ID must resolve to the same canonical snapshot identity;
- repeated declarations for one snapshot must agree on parent relationships;
- valid role sets are additive;
- incompatible snapshot identity or parentage makes project revision selection
  unavailable;
- multiple incomparable role-bearing tips make selection conflicted; and
- ancestry is calculated on this reconciled project graph, never independently
  per campaign.

## Task model

### Result

The factual result for the selected exact revision is:

- `not_passing`;
- `passing`;
- `regressed`; or
- `unavailable`.

`regressed` means the task had a qualified pass on an earlier selected revision
and does not pass on the current selected revision. Session state and run
liveness cannot set these values.

For schema version 1, task qualification uses only
`kind: "all_bound_cases"`. For the selected exact revision:

- `required_roles` is a nonempty unique subset of `development` and
  `regression`;
- both repetition thresholds are positive integers and
  `required_passes_per_case` is no greater than
  `minimum_terminal_repetitions_per_case`;
- the required binding set is every current binding for the task whose role is
  in `required_roles`, and an empty required set invalidates the declaration;
- each required case must have at least
  `minimum_terminal_repetitions_per_case` authoritative terminal attempts; and
- at least `required_passes_per_case` of those attempts must PASS.

For qualification, canonical fingerprints are calculated separately for:

- the task definition: task ID, title, summary, and qualification rule; and
- each binding definition: binding ID, case ID, case revision, task ID, role,
  and safe-progress declaration.

An attempt counts only when its archived project declaration resolves to the
same current task-definition fingerprint and binding-definition fingerprint,
and it binds the selected skill snapshot, source campaign identity, binding ID,
case ID, and exact case revision. The whole-declaration SHA-256 remains
provenance; an unrelated additive declaration revision does not invalidate
unchanged task evidence. A changed task definition invalidates prior evidence
for that task, while adding a binding preserves unchanged binding evidence but
keeps the task incomplete until the new binding qualifies.

The task is `passing` only when every required binding satisfies the rule.
Evaluator FAIL is `not_passing`; missing or incomplete required evidence is
`unavailable`. A task with an earlier qualified pass becomes `regressed` only
when the current selected revision has complete qualifying evidence and fails
the same task-definition fingerprint. A future qualification kind requires a
new reviewed schema version.

First-qualified time orders authoritative terminal attempts by
`completed_at`, then stable attempt ID. It is the completion time of the
earliest prefix that satisfies every required binding. Runs, attempts, credits,
and tokens through qualified PASS use that same prefix.

### Phase

The workflow phase is:

- `not_started`;
- `experimenting`;
- `candidate_pass`;
- `qualifying`;
- `delta_ablation`;
- `regression_check`;
- `holdout_validation`;
- `ready_to_publish`; or
- `published`.

Extend the existing `task_progress_recorded` payload with optional `task_id`,
`project_declaration_sha256`, and typed `phase` fields, and allow an
`experiment` source reference. The existing `dashboard task-progress` command
remains the writer and verifies that its case belongs to `task_id` under that
declaration revision. No second task-phase event family is added.

For legacy progress records without `phase`, projection maps:

- no valid progress record to `not_started`;
- any valid activity record to `experimenting`.

Authoritative derived evidence may then raise the phase to `candidate_pass`,
`qualifying`, `holdout_validation`, `ready_to_publish`, or `published`.

Session-authored explicit phase is limited to intent states:

- `experimenting`;
- `delta_ablation`; and
- `regression_check`.

The other phases are derived:

- `candidate_pass` requires an immutable first observed PASS that has not met
  the task qualification rule;
- `qualifying` requires terminal qualification attempts for the selected
  revision that have not completed the rule;
- `holdout_validation` requires an authenticated active holdout-evaluator
  receipt for the exact selected revision;
- `ready_to_publish` requires task qualification, completed delta ablation,
  maintained regressions, and every holdout requirement that names the task;
- `published` requires those facts plus a `published` or `released` lineage
  role on the selected revision.

Explicit intent records participate only when:

- `task_id` matches the projected task;
- their case belongs to that task under the event's declaration revision; and
- their snapshot is the selected revision, or their referenced
  `delta_ablation` experiment names the task and descends from that revision.

Projection collects valid intent records across every bound case and registered
corpus for the task. It chooses the greatest dashboard-owned `recorded_at`.
If records at that time disagree on phase, phase is conflicted and unavailable.
`event_id` supplies stable presentation order only; it never breaks a semantic
tie. Session-supplied `observed_at` is displayed but cannot outrank later
dashboard receipt time. Derived phases outrank explicit intent when their
authoritative prerequisites exist. A phase cannot create PASS or override an
evaluator result.

The default presentation combines both axes, for example:

> **Passing · Delta ablation**  
> The evaluator passes this task. The newly added rules are still being
> minimized before publication.

### Safe progress

A percentage appears only when an allowlisted typed reader projects an existing
validated artifact containing:

- a stable check-set identity;
- named safe checks;
- passed, failed, and unavailable counts; and
- evidence references that contain no hidden criteria.

The first reader kinds are bounded to existing safe result shapes:

- deterministic repository checks; and
- validated distributed product stages.

No dynamically loaded adapter code, executable plugin, arbitrary path, or raw
candidate output participates in progress projection.

Prose cases and hidden judges show no percentage unless a later reviewed typed
reader establishes a candidate-safe denominator. The UI says “No safe
subcheck breakdown” rather than `0%`.

### Time and effort

For each task, calculate:

- first supported project run start;
- first observed PASS;
- first qualified PASS;
- elapsed wall time to qualified PASS;
- project run count through qualified PASS;
- attempt count through qualified PASS;
- infrastructure-failed run count;
- observed candidate and judge tokens when authoritative;
- observed credits and cost coverage; and
- retry dependence.

An isolated PASS does not end time-to-pass until the task's typed qualification
rule is complete. Regression, holdout, ablation, and publication time remain
visible in later workflow phases rather than extending the task's
time-to-qualified-pass. Current unfinished tasks show elapsed time since the
first supported run.

## Run lifecycle

Supported launchers expose source-owned lifecycle artifacts that projection
normalizes into one project-run shape. They do not copy every source into a
second generic event stream.

### Startup

For a local single-case run, extend the existing create-once `attempt.json`.
For a local suite, add one minimal create-once `suite-start.json` immediately
after the suite directory is created and before snapshot or candidate setup.
For distributed work, reuse the existing experiment declaration, package,
matrix, and dispatch binding.

Startup intent contains facts already validated before risky setup:

- run ID;
- project ID and declaration fingerprint;
- corpus campaign ID;
- launcher kind: `local_case`, `local_suite`, or `distributed_campaign`;
- required plain-English run goal;
- requested plugin path, treatment reference, and declared arm when applicable;
- selected task and case IDs;
- planned workers, attempts, and experiments;
- source-specific execution identity; and
- local lease generation when applicable; and
- start timestamp.

Later immutable capture artifacts add the exact skill snapshot, treatment, and
execution identities. They complete or supersede startup intent. A setup
failure remains visible even when snapshot capture never succeeded.

Project-bound CLI commands require a meaningful `--run-goal`, or receive it
from an already validated experiment declaration. Legacy unassigned commands
remain compatible.

### Progress

Existing launcher-owned records report:

- attempt planned;
- attempt started;
- safe product stage;
- immutable artifact available; and
- remote dispatch binding when applicable.

Agent-session heartbeats remain visible only as supporting operator activity.
They are never project-run evidence.

Local single-case and suite launchers also own an atomically replaced
`run-lease.json`:

```json
{
  "schema_version": 1,
  "run_id": "<run id>",
  "generation": "<random generation>",
  "renewed_at": "<ISO-8601 timestamp>",
  "expires_at": "<ISO-8601 timestamp>"
}
```

The launcher generates the lease generation before publishing startup and
binds it immutably into both the startup artifact and every renewal. It creates
and renews the lease through atomic regular-file replacement in a background
heartbeat throughout setup, candidate execution, and reporting. Renewal stops
only after an authoritative terminal or failure artifact is durable. The
configured renewal interval must be shorter than half the lease duration;
tests inject the clock and duration rather than fixing an architectural number.

If initial lease creation fails after startup is durable, the launcher writes a
typed `lease_unavailable` infrastructure failure when possible. If renewal
fails, the launcher stops starting new work and writes the same typed failure
when possible. A renewal with a different generation is invalid. Authoritative
terminal and failure artifacts always outrank an unexpired lease.

### Terminal state

Completion derives from immutable attempt, suite, distributed-result, and
selection artifacts. Infrastructure failure derives from existing typed
failure, timing, transport, and stage receipts.

The local suite adds `suite-failure.json` only for failures after
`suite-start.json` that currently leave no typed artifact before an attempt can
start. It records the earliest failed stage, error class, safe message, and
timestamp. It does not classify behavioral outcomes.

A local nonterminal run is active only while its matching lease generation has
not expired. An expired lease with no authoritative terminal or failure
artifact is projected as `liveness_lost`, not as a definite interruption. The
projection retains the last lease and states that the process may have died or
lost durable-state access. An explicit typed interruption artifact may show
`interrupted`. Neither derived state is rewritten as an emitted terminal
result. A healthy long attempt remains active because lease renewal is
independent of attempt output. No `cancelled` state is introduced because no
supported cancellation operation or artifact exists.

Evaluator PASS, FAIL, and UNANSWERABLE are attempt outcomes under a completed
run. They are not infrastructure states.

### Compact row

Each run row shows:

- start timestamp and duration;
- run goal;
- local or distributed source;
- selected tasks;
- planned and observed parallelism;
- planned, started, completed, passing, failing, and unavailable attempts;
- infrastructure state and earliest failure stage;
- exact selected skill revision;
- observed cost with completeness; and
- an optional detail route.

No empty field is rendered. Unknown is shown only when the missing fact changes
the meaning of the row.

## Holdout qualification

Holdout execution runs under a separate principal or isolated environment whose
private corpus and signing key are outside the optimizing agent's filesystem,
process, tool, and credential boundary. If that boundary is unavailable, the
dashboard reports holdout qualification as unavailable rather than accepting
an unauthenticated aggregate.

An operator provisions trust with:

```text
dashboard trust-holdout-authority \
  --registry <protected-authority-root> \
  --authority-id <id> \
  --public-key <ed25519-public-key> \
  --maximum-run-seconds <owner-policy-bound>
```

The protected registry is outside corpus, session, plugin, and ordinary
dashboard state. Its directory and create-once authority files are owned by a
principal or managed configuration boundary unavailable to the optimizing
agent. Provisioning refuses a registry writable by the evaluator or optimizing
principal. One authority ID maps create-once to one public-key fingerprint and
one owner-set maximum run window. Key replacement or policy replacement uses a
new authority ID. Corpus metadata cannot provision, replace, revoke, or weaken
an authority. Without this independent boundary, holdout qualification is
unavailable.

The isolated evaluator uses a project-aware private mode:

```text
skill_eval.py run-suite <private-holdout-corpus> ... \
  --holdout-project-declaration <canonical-project-declaration> \
  --holdout-set <holdout-set-id> \
  --holdout-signing-key <private-key> \
  --holdout-receipt <export-path> \
  --run-goal <plain-English-goal>
```

The evaluator process can read the private frozen holdout corpus and its
ordinary suite artifacts. The optimizing agent and dashboard cannot. The mode
does not print or export the private corpus path, suite root, case identities,
or per-case results through stdout, stderr, or the receipt.

Before private execution, the evaluator writes a signed `started` receipt that
binds the public declaration, holdout set, exact candidate snapshot, run ID,
and expiry. After an immutable terminal result, it writes a separate signed
`completed` or `infrastructure_failed` aggregate receipt. A public
`dashboard holdout-qualification` command verifies the configured authority,
signature, project declaration, holdout set, exact candidate snapshot, and
receipt transition before publishing records with writer kind
`holdout_importer`. Projection authority comes from the verified signature and
transition chain, not from the local importer identity.

Every receipt contains:

- schema version and receipt kind;
- a unique 32-hex receipt ID;
- issued timestamp;
- run ID;
- authority ID and public-key fingerprint;
- project declaration SHA-256;
- holdout-set ID;
- exact candidate snapshot;
- evaluator version; and
- base64url-without-padding Ed25519 signature.

The `started` receipt also contains `expires_at`. Its lifetime must be positive
and no greater than the authority registry's `maximum_run_seconds`.

The terminal receipt contains:

- `started_receipt_sha256`;
- terminal kind: `completed` or `infrastructure_failed`;
- completion timestamp; and
- the terminal aggregate fields below.

The terminal aggregate contains:

- project ID and declaration fingerprint;
- opaque holdout-set ID;
- exact candidate snapshot;
- required claim;
- planned, completed, passing, failing, and unavailable counts;
- overall qualification result;
- timing and accounting;
- infrastructure status; and
- authority ID and public-key fingerprint;
- opaque private-corpus fingerprint; and
- Ed25519 signature over the canonical unsigned receipt.

The terminal receipt must bind the exact canonical SHA-256 of one accepted
started receipt and only one terminal receipt may consume that start. It may be
imported after the start expires only when its signed completion timestamp is
not later than the signed `expires_at`.

The signed body is UTF-8 canonical JSON with sorted object keys, no insignificant
whitespace, no duplicate keys, and no floating-point values. It reuses the
canonical serializer underlying `json_fingerprint`; accounting quantities use
integers or canonical decimal strings. The signature field is omitted from the
signed bytes.

Signing and verification use Ed25519 through the pinned Python
`cryptography` implementation. Missing or unusable verification support fails
closed; it does not downgrade to hashes or unsigned records.

The signed bodies bind the public project declaration fingerprint, holdout-set
ID, exact candidate snapshot, evaluator version, authority ID, key fingerprint,
run ID, and receipt ID. The terminal body also binds the started-receipt
digest, opaque private frozen-corpus fingerprint, immutable private
suite-result SHA-256, and all aggregate fields.

The verified receipt is written under the existing writer-owned extension
directory using `holdout-qualification-v1`. Import rejects an unknown or
mismatched authority, signature or canonicalization failure, project or
snapshot mismatch, invalid or duplicate transition, out-of-policy lifetime,
late completion, replayed receipt ID, and every forbidden field before write.
Projection verifies the stored signature, transition chain, and allowlist again
before use.

The dashboard does not receive case identities, descriptions, prompts,
criteria, outputs, or per-case behavioral failures. Infrastructure errors may
identify the failed system stage.

If holdout details influence skill changes, the set is no longer held out. The
workflow must relabel it as development evidence and use a fresh reserved set
for later transfer claims.

## Ablation

### Per-task delta ablation

After a newly conquered task reaches its predeclared pass rule, the task enters
`delta_ablation`.

Represent a delta ablation as an existing experiment declaration with
`experiment_kind: "delta_ablation"` and a required project task ID. Existing
treatments, attempts, distributed activity, results, and selection records
remain authoritative. The declaration and final selection bind:

- task ID;
- prior published baseline snapshot;
- exploratory passing snapshot;
- minimized candidate snapshots;
- exact maintained-task set;
- exact qualification runs;
- removed, retained, and restored instruction identities;
- the final qualified snapshot.

Before and after bytes, text lines, and file counts are derived from exact
existing skill snapshots. They are not copied into a second result record.

The UI shows:

- exploratory passing size;
- current minimized size;
- final qualified size when available;
- absolute and percentage reduction;
- maintained wins passed and failed; and
- why a removed rule was restored.

A task may remain factually passing while its phase is delta ablation or
regression checking.

### Whole-skill ablation

Whole-skill ablation is a separate project stage. It is declared only when the
accumulated procedure appears to dilute or contradict load-bearing behavior.

Represent whole-skill ablation as an existing experiment declaration with
`experiment_kind: "whole_skill_ablation"`. It compares exact:

- original;
- current passing;
- neutral;
- lean;
- full; and
- final selected

skill snapshots. Existing experiment results and selection remain authority.
The declaration adds only the ablation kind and required qualification
references when those facts are not already represented. The UI shows size,
complete task and holdout qualification, retry dependence, and selection
reason for each available arm. Missing arms remain absent rather than
synthesized.

## Browser lifecycle and authorization

### Open once

`register_dashboard` may auto-open a project only when that project has not
been opened in the current dashboard service generation. New agent sessions,
retry corpora, and new runs update the existing project without opening tabs.

Two or more supported session registrations may race for the same project.
Use one project-open lock and a create-once receipt:

```json
{
  "schema_version": 1,
  "service_generation": "<hex generation>",
  "project_id": "<safe id>",
  "opened_at": "<ISO-8601 timestamp>"
}
```

While holding the lock, registration checks for the receipt, opens the browser,
and writes the receipt only after `browser_open` succeeds. A failed opener
writes no receipt, so a later registration may retry. This is the only new
coordination required for browser opening.

`dashboard open --project <id>` always remains available.

Unassigned legacy evaluations do not auto-open.

### Project-scoped capability

The control endpoint mints a capability with one exact scope:

- `project_index`;
- `project:<project-id>`; or
- `unassigned`.

All capabilities are also bound to one dashboard service generation.

`project_index` is an explicit owner grant to list project summaries and select
one project. An authenticated index request may mint a child
`project:<project-id>` capability only for a project present in that index.
The operation changes browser read authority, not evaluation state. It cannot
mint unassigned, legacy, control, or cross-generation authority.

The static client:

1. reads `#cap=...`;
2. validates that it is a nonempty capability string;
3. stores it in `sessionStorage` under the service generation and complete
   scope identifier (`project_index`, `project:<id>`, or `unassigned`);
4. removes it from the visible URL; and
5. restores it from `sessionStorage` on refresh.

It never stores capabilities in `localStorage`, cookies, disk-backed dashboard
state, logs, query strings, or referrers. A prior-generation capability fails
closed.

## Routes and capability matrix

| Scope | Allowed routes |
|---|---|
| `project_index` | `/`, `/api/projects`, and the child-project capability endpoint |
| `project:<id>` | `/project/<id>`, its task and run routes, and matching project APIs |
| `unassigned` | `/unassigned`, `/api/unassigned`, and legacy campaign routes only while that campaign remains unassigned |

Static shells contain no project data without a matching capability. A project
capability cannot call the project index, unassigned, legacy campaign, or
another project API.

The project index client requests a child capability before navigating to a
project. It never reuses the index capability on project routes.

The unassigned projection revalidates project membership on every request. If
an agent adds valid project metadata, the campaign immediately disappears from
unassigned APIs and old unassigned capabilities cannot read it through legacy
routes.

Runs in that corpus without a project declaration fingerprint remain visible
under the project's **Pre-project history** section because the corpus now has
explicit project membership. They never enter task status, cost, timing,
generalization, ablation, or project-run totals. Project capability may read
only those immutable legacy run projections, not infer task or revision
bindings for them. History is not migrated or deleted.

## Main project layout

1. **Project header**
   - target skill or skill set;
   - one-sentence goal;
   - exact selected revision and role;
   - started time and last evaluator activity.
2. **Outcome strip**
   - tasks passing and not passing;
   - tasks still qualifying or minimizing;
   - aggregate holdout qualification;
   - observed total cost and coverage;
   - active local and distributed runs.
3. **Task list**
   - English title and summary;
   - result and phase;
   - safe subprogress when available;
   - time, runs, attempts, infrastructure failures, credits, and tokens;
   - delta-ablation reduction.
4. **Generalization**
   - aggregate holdout result only.
5. **Ablation**
   - task delta-ablation summaries;
   - optional whole-skill comparison.
6. **Runs**
   - one compact row per supported execution run.
7. **Pre-project history**
   - legacy runs from explicitly assigned corpora, clearly excluded from every
     project aggregate.
8. **Data limits**
   - only active conflicts, partial accounting, unavailable source, or stale
     nonterminal lifecycle that changes interpretation.

The page does not reserve empty space for optional schemas.

## End-to-end journey

**Illustrative example:** An agent starts a project-aware local suite with:

```text
skill_eval.py run-suite <corpus> ... \
  --run-goal "Check whether the interruption fix preserves all 15 tasks"
```

The evaluator validates `evaluation-project.json`, writes the applicable
source-owned startup artifact, snapshots the exact skill bytes, and emits
existing attempt progress. The existing project tab updates to show one active
run with 15 planned attempts and the declared goal. It does not open another
tab.

If setup fails before any candidate starts, the run becomes
`infrastructure_failed`, shows zero started attempts, and names the failed
stage. It does not make any task red.

If all attempts complete, immutable evaluator results replace live progress.
The project scorecard changes only for the exact selected revision. When a task
first reaches its qualification rule, its result becomes `passing` and its
phase moves to `delta_ablation`. The task row shows elapsed time, run and
attempt counts, observed spend, and later the size reduction of the smallest
qualified increment.

An independent holdout run later publishes only aggregate transfer counts for
the same exact snapshot. The project can become ready to publish without
revealing which reserved cases passed or failed.

## Failure model

| Failure | Required behavior |
|---|---|
| Project files share an ID but disagree on goal or task meaning | Exclude conflicting registrations from totals and show the conflict |
| A corpus changes its declaration without the current `supersedes` fingerprint | Reject the revision; retain the prior current declaration |
| A schema-v1 revision omits a prior stable ID | Reject the revision; omission is not deletion |
| A case maps to no task or several tasks | Reject the project declaration |
| A project run omits its declaration fingerprint | Treat it as unassigned or unsupported; never guess |
| Run startup succeeds but process dies before an authoritative terminal artifact | Show `liveness_lost`; preserve all immutable attempt artifacts and do not claim a cause |
| A healthy long attempt emits no candidate artifact before the lease interval | Lease renewal keeps it active |
| Lease creation or renewal fails | Show liveness unavailable or the typed lease infrastructure failure; never infer interruption |
| Source progress disagrees with immutable result artifacts | Immutable artifacts win; show the source-progress conflict |
| Current selected revision has no result for a task | Show unavailable, not failing |
| A previously qualified task fails on the selected revision | Show regressed |
| A session declares a derived-only task phase | Reject the event |
| Case-scoped phase records disagree at the latest observation | Show phase conflict and make phase unavailable |
| Safe subprogress reader receives an unknown schema | Omit percentage and show unsupported progress data |
| Accounting covers only some attempts | Show observed subtotal and coverage |
| Holdout record contains forbidden identity or detail fields | Reject the entire record and expose no holdout data |
| Holdout authority is unknown or the signature is invalid | Reject the receipt and show qualification unavailable |
| Holdout registry is writable by the optimizing or evaluator principal | Refuse authority provisioning and keep qualification unavailable |
| Browser capability is missing, malformed, wrong-project, or stale | Return no project data |
| `sessionStorage` is unavailable | Page works until refresh and tells the user to run explicit open again |
| Browser open fails | Evaluation continues; CLI prints the token-free explicit-open command |
| Legacy corpus lacks project metadata | Keep it under unassigned evaluations |
| Existing corpus gains project metadata | Show fingerprint-less runs as pre-project history and exclude them from every aggregate |
| Distributed transport is active without evaluator completion | Show transport activity without claiming attempts completed |

## Migration and rollback

### Migration

- Existing campaign registrations and routes remain readable.
- Existing corpora are not changed automatically.
- An agent opts a corpus into a project by adding a valid
  `evaluation-project.json`.
- Existing completed runs without a project declaration fingerprint become
  labeled pre-project history under the explicitly assigned project. They
  remain excluded from every project aggregate unless a separately reviewed
  migration creates exact bindings.
- Project totals never mix assigned and unassigned evidence.

### Rollback

Rollback disables project routes, project registration, and new lifecycle
projection while retaining every new append-only file. Legacy campaign pages
continue to read existing immutable result artifacts.

The browser falls back to explicit `dashboard open` if open-once state or
`sessionStorage` recovery causes a regression.

The boundary fails closed when:

- project or capability validation fails;
- project declarations conflict;
- holdout authority, signature, transition, or allowlist validation fails;
- new schemas are unknown; or
- a lifecycle record cannot bind to exact evaluator authority.

Proof of fail-closed behavior is that the affected aggregate or route returns
no protected data and no success-shaped value, while unrelated valid projects
remain readable.

## Delivery slices

Each slice is independently useful and demonstrable before it is considered
complete. Dependency order remains A, then B, then C. Merge and installation
timing follow the governing development workflow rather than defining product
correctness.

### Slice A: Project identity, browser repair, and local run truth

Deliver:

- explicit project and task declaration;
- project registration, index, route, and basic scorecard;
- one auto-open per project per service generation;
- tab-scoped capability recovery on refresh;
- current exact project revision selection;
- automatic local case and suite lifecycle;
- compact local run rows; and
- unassigned legacy navigation.

Observable value: one project page remains open while local retries and suites
appear automatically with truthful infrastructure and attempt status.

### Slice B: Task journey, distributed runs, and generalization

Deliver:

- separate task result and phase;
- safe declared subprogress;
- time-to-qualified-pass and run, attempt, token, credit, and infrastructure
  rollups;
- normalized distributed lifecycle;
- aggregate-only holdout qualification; and
- current-revision regression detection.

Observable value: the task list explains what is passing, what is still being
worked on, how much it took, and whether the exact candidate transferred.

### Slice C: Delta and whole-skill ablation

Deliver:

- per-task delta-ablation declarations and results;
- before, current, and final exact size comparisons;
- maintained-win qualification;
- optional whole-skill neutral, lean, full, and selected comparisons; and
- integrated project presentation.

Observable value: a passing task can visibly move through minimization, and the
project shows whether the final skill became smaller without losing wins.

## Acceptance criteria

1. Two corpora with the same valid project ID and compatible declarations
   appear as one project; name similarity alone never groups corpora.
2. A conflicting project goal or task definition is visible and excluded from
   aggregates.
3. Legacy corpora remain readable only under unassigned evaluations until
   explicitly declared.
4. Registering several sessions, retries, and runs opens at most one tab for
   the project in one service generation.
5. Refreshing a project tab restores its project-scoped capability from
   `sessionStorage`; another project remains unreadable.
6. A supported local suite appears after startup, before final suite results
   exist.
7. A handled infrastructure failure produces one compact failed run row and
   does not change task results.
8. An expired nonterminal run appears as `liveness_lost` without a fabricated
   interruption or terminal event.
9. A completed run row shows planned, started, completed, passing, and failing
   attempt counts from authoritative evidence.
10. Project task totals describe one exact selected skill revision and never
    pool passes from different revisions.
11. A previously qualified task that fails on the selected revision appears as
    regressed.
12. A task can display `passing` and `delta_ablation` at the same time.
13. Time-to-qualified-pass, run count, attempt count, infrastructure failures,
    tokens, and cost use only authoritative covered evidence.
14. A prose case without safe declared checks displays no percentage.
15. A valid safe-progress typed reader displays its named denominator and
    counts.
16. Distributed runs use the same compact lifecycle fields while preserving
    source-specific execution identity.
17. Holdout projection contains only aggregate counts, exact candidate
    identity, timing, accounting, infrastructure state, and qualification.
18. Any holdout record containing a case identity, prompt, criterion, output,
    or per-case behavioral failure is rejected.
19. Per-task delta ablation compares exact exploratory and qualified snapshots,
    reports size reduction, and binds maintained-win results.
20. Whole-skill ablation remains absent until explicitly declared.
21. Immutable evaluator artifacts supersede conflicting live lifecycle.
22. Partial cost remains labeled partial and never appears as an exact total.
23. No project route can resolve arbitrary paths or expose hidden evidence.
24. Each slice has one focused installed-plugin fixture for its new behavior,
    and the final product has one representative installed journey spanning a
    multi-corpus project, local and distributed run history, aggregate holdout
    status, delta ablation, and refresh-safe browser authority.
25. Task PASS, regression, and time-to-qualified-pass follow the declaration's
    typed qualification rule over the selected exact revision.
26. Session-authored phase records cannot claim qualifying, holdout-validating,
    ready-to-publish, or published state; those phases require their named
    authoritative evidence.
27. Multi-case and cross-corpus task phase reduction is deterministic, and
    equal-time disagreement is visible as a conflict.
28. A healthy long local run remains active through lease renewal, while an
    expired run becomes `liveness_lost`; only an explicit artifact may call it
    interrupted.
29. Forged, unknown-authority, replayed, or detail-bearing holdout receipts are
    rejected; invalid transitions, lifetimes, and late completions fail closed;
    and private holdout mode emits no private path or case detail.
30. Adding project metadata to a legacy corpus preserves its old runs as
    readable pre-project history without allowing them into aggregates.
31. Declaration revisions require an exact `supersedes` chain; historical runs
    retain their archived declaration semantics.

## Check contract

| Check | Protects | Setup | Pass signal | Failure proves |
|---|---|---|---|---|
| Project schema unit tests | Explicit identity and conflict rejection | Valid, missing, duplicate, conflicting, and legacy declarations | Exact accepted or rejected records | Invalid grouping can enter state |
| Declaration revision tests | Safe metadata evolution | Additive revision, corrected task, stale supersedes, and historical run | Current merge advances only on exact chain; history keeps old semantics | Routine metadata edits can corrupt totals |
| Cross-corpus projection test | One project, no inferred joins | Two compatible project corpora plus similarly named unrelated corpus | Only explicit pair joins | Names can create false projects |
| Revision scorecard test | No pooled candidate wins | Different snapshots pass different tasks | Neither snapshot shows all tasks passing | Projection fabricates a winner |
| Task qualification tests | Deterministic PASS and regression | Multi-case and two-corpus tasks with repetitions, incomplete evidence, prior pass, current failure, unrelated additive declaration revision, changed task definition, and added binding | Unchanged task and binding evidence survives unrelated revisions; changed definitions and new bindings affect only their task; result and first-qualified time follow the typed rule | Implementers invent incompatible pass rules or whole-declaration hashes erase valid evidence |
| Local lifecycle integration | Early run visibility | Pause a suite after startup record | Active row exists before final artifacts | Dashboard still follows only final files |
| Infrastructure-path tests | Truthful failure state | Fail setup, runner, artifact, and evaluator stages | Correct earliest stage; task result unchanged | Infrastructure is confused with behavior |
| Lease and crash recovery test | Honest local liveness | Run a healthy long attempt, terminate another after startup, and make renewal storage fail | Healthy lease remains active; expired lease becomes `liveness_lost`; explicit lease failure remains infrastructure failure | Projection guesses cause from elapsed silence |
| Distributed normalization test | Shared run semantics | Valid package through dispatch, stage, and result | Same normalized fields and exact source identity | Local and cloud totals are incomparable |
| Task phase authority tests | Separate result and trustworthy phase | Multi-case task, explicit intent, derived qualification, equal-time conflict, and later regression | Only allowed intent is accepted; derived phases require authority; reduction is deterministic | Session prose can manufacture workflow completion |
| Safe-progress typed-reader tests | No fabricated or hidden percentages | Valid declared checks, prose case, malformed artifact | Counts only for a valid allowlisted reader | UI can leak or invent progress |
| Task efficiency tests | Correct time and spend | Retries, partial accounting, first observed and qualified passes | Exact bounded rollup and coverage | Dashboard misstates effort |
| Holdout authority and allowlist tests | Authentic aggregate-only generalization | Protected and writable registries; valid start/terminal chain; forged signature; unknown or replaced authority; replay; duplicate terminal; expired and late completion; missing verifier; private-mode output capture; every forbidden field | Only the owner-provisioned authentic chain is accepted; no private path or detail emitted | Holdout status can be forged, replayed, or leaked |
| Ablation identity tests | Exact size and maintained wins | Exploratory, minimized, regressed, and qualified snapshots | Correct reduction only for qualified identity | UI rewards smaller but unqualified skills |
| Capability scope integration | Least privilege and refresh | Two projects, refresh, stale generation, wrong scope | Only same tab/project/generation succeeds | Browser authority crosses projects |
| Open-once integration | No tab storm | Multiple sessions and runs in one generation, then restart | One open before restart; one after restart | Retries still open tabs |
| Legacy opt-in transition | Preserve old evidence without false totals | Existing corpus with completed runs gains project metadata | Old runs appear as pre-project history; only fingerprinted runs aggregate | Opt-in hides history or contaminates project results |
| Hidden-path refusal suite | Existing critical boundary | Traversal, symlink, unknown schema, hidden markers | All refused; no marker reaches JSON or HTML | Critical evidence boundary fails open |
| Installed-plugin visual proof | Actual user outcome | Required multi-corpus project fixture at desktop and mobile widths | Plain-English hierarchy and compact rows match the work order | Unit behavior does not produce usable product |

The holdout allowlist and project capability scope tests exist before their
production implementations because they constrain the critical boundary.
Other checks are added with their implementation slice.

## Definition of Done: Skill Evaluation Project Dashboard

This work is complete when:

1. all three delivery slices are implemented and independently demonstrated;
2. the smallest combined automated checks prove every acceptance criterion;
3. the installed-plugin proofs in criterion 24 are captured and reviewed in
   light, dark, desktop, and narrow layouts;
4. reviewed source, installed files, and executed files correspond exactly;
5. hidden-path, holdout, and capability tests prove the boundary fails closed;
6. dual implementation review has no unresolved material finding;
7. the project page contains no unsupported empty metrics or inferred identity;
8. legacy data remains available without entering project totals;
9. documentation names the supported launch commands, required project
   declaration, run-goal contract, and unassigned behavior.

## Known limits

This design is specific to the skill-evaluation tool and its trusted launchers.
Reusing it for another evaluation product would require equivalent exact
artifact identity, immutable results, lifecycle ownership, hidden-evidence
separation, and accounting contracts.

The design intentionally duplicates a small project declaration across corpus
roots so each corpus and distributed package is portable. Registration rejects
conflicts. A central mutable project service would remove that duplication but
would add a trusted component and a migration problem that the current user
outcome does not require.

Large-project rendering may later need pagination or virtualization. No
measured corpus currently justifies fixing a limit or adding that machinery.
