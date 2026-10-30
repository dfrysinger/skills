# Skill Evaluation One-Time History Migration

**Status:** Reviewed
**Lane:** Critical
**Decision record:** `design/skill-evaluation-ui-one-time-migration-decisions.json`
**Decision revision:** `skill-evaluation-ui-one-time-migration-decisions-r1`
**Sealed evidence packet:** `design/skill-evaluation-ui-one-time-migration-evidence.json`
**Evidence revision:** `skill-evaluation-ui-one-time-migration-evidence-r1`
**Constraint record:** `design/skill-evaluation-ui-one-time-migration-constraint.md`
**Constraint gate:** `CLEARED_FOR_DESIGN_REVIEW`
**Reframe status:** `CLEAR`

```yaml
design_incubation:
  status: approved
  cycle: 1
  objective_file: /Users/dfrysinger/.copilot/session-state/6f7726ad-c851-4da9-bd16-ffbd015dd0f1/files/skill-evaluation-ui-one-time-migration-design-objective.txt
  reminder:
    kind: design_progress
    id: 15
    interval: 30m
    status: stopped
```

## Objective

Migrate Assistant's existing eight-task evaluation history into the shipped
project dashboard without changing original evidence, and let every task with
sufficient recovered evidence qualify under the same rules as new work.

## User outcome

The user opens one project and sees the eight tasks, their known experiments,
their honest progress and cost, and a correct Passing, Not passing, or
Unavailable result for each task. Missing historical fields say Not recorded
or Unavailable. The migration runs once. New work uses the current project and
experiment contract directly.

## Resolved migration identity

The source handoff fixes this bounded migration as follows:

- project ID: `development-loop-generalization`;
- project title: `Improve Development Loop`;
- project goal: `Find general Development Loop wording that works across all
  eight tasks, then minimize it while retaining qualification.`;
- target skill: `development-loop`;
- evaluated candidate: treatment `h01-probe-interference-bracket`, skill file
  SHA-256
  `6097e3cb8b99d53f420bf5b69d41b85eb7e0c4c28da8bd0afc1ad815913e4e34`;
- historical control: treatment `b01-unchanged-parent`, skill file SHA-256
  `bfbe1aad213ff5b8f58a556173c8a6635dd01c3c284164b1a377aa1a5915f7b0`;
- source experiment: `general-probe-interference-comparison-r2850`; and
- output root:
  `/Users/dfrysinger/.copilot/session-state/92851a91-1223-4c68-b183-f9ba3be0421b/files/migrated-development-loop-corpus`.

The evaluated candidate has all 23 planned outcomes. It passes seven task
thresholds and fails one. It was not historically selected as a final general
revision. The migrated project therefore labels it as the evaluated candidate,
not as a winner or published skill.

The control remains visible experiment history. Its 16 explicit Not executed
stops remain part of its fixed population and cannot be replaced by later
attempts.

The eight project task IDs preserve the safe source case IDs. Their migration
display labels and roles are:

| Task ID | Display title | Role |
|---|---|---|
| `devloop-scope-production-revoke` | Production scope revocation | `development` |
| `devloop-bug-root-scrolling` | Root scrolling | `development` |
| `devloop-bug-sparse-cohort` | Sparse cohort handling | `development` |
| `devloop-proof-neutral-engine` | Proof-neutral evaluation | `development` |
| `devloop-bug-enterprise-hydration` | Enterprise hydration | `development` |
| `devloop-registry-reentrant-regression` | Reentrant registry behavior | `development` |
| `devloop-ci-host-policy-calibration` | CI host policy calibration | `development` |
| `devloop-scope-duplicate-transport` | Duplicate transport handling | `development` |

These are migration-owned project labels. They do not change source task
identity or private task text.

## Non-goals

This work does not:

- create a permanent general importer for arbitrary package formats;
- change Assistant's original files, outcomes, fixed populations, or dates;
- infer task roles, project membership, skill identity, or outcomes from names
  and paths;
- allow an incomplete fixed population to pass through later rescue attempts;
- expose private task, grader, holdout, or answer-shaped evidence;
- add controls to launch, retry, edit, or approve evaluation from the browser;
- redesign the project dashboard or introduce new user-facing vocabulary; or
- make migrated history the format for future experiments.

## Why this is critical

The migration crosses the task identity and qualification boundary. A false
mapping could make the dashboard claim that a skill passed a task it did not
run. A false population could let later experiments repair an earlier failed
or incomplete denominator. The migration therefore fails closed and leaves a
task Unavailable when qualification-critical identity is missing or
conflicting.

Rollback is removal of the new migrated corpus registration and migration
output. Original source evidence remains untouched. A clean reprojection from
the original dashboard state must then return the pre-migration project list.

## Trusted owners

- Assistant owns the source history and supplies an explicit source mapping.
- Existing skill-evaluation validators own task, skill revision, experiment,
  attempt, and result identity.
- The migration command owns deterministic private reconstruction and
  correspondence checks.
- Existing project registration and dashboard projection own the final
  read-only view.

The migration command may intentionally create the bounded corpus,
declarations, and immutable records named by the reviewed migration manifest.
It may not invent additional tasks, outcomes, attempts, or skill revisions.

## Proposed data flow

1. Assistant supplies one explicit migration manifest for the eight tasks.
2. The migration validates every source path and digest before writing output.
3. Each task receives an explicit project task ID, title, role, target skill,
   and verified private full-product case root. Missing required identity stops
   only that task.
4. A deterministic coordinator-private conversion reconstructs one
   current-format authoring task from that packaged case. It copies referenced
   candidate and hidden payload bytes without printing or projecting them.
5. Existing freeze and verification logic creates the new authoritative task
   version used by the project dashboard.
6. The migration writes one project declaration that binds every successfully
   imported task and one lineage declaration marking the evaluated candidate
   snapshot `integrated` into this migrated project.
7. Where the source plan proves a complete fixed experiment population and
   its per-task threshold, the
   migration records that exact experiment and its immutable results through
   existing experiment validators.
8. Where evidence is incomplete, the migration preserves the known experiment
   history but leaves task qualification Unavailable.
9. The dashboard reads the resulting project through its existing API. It
   receives no migration-specific authority.

## Private task reconstruction

No current-format frozen task or original authoring directory was recovered
from the bounded source records. All eight complete full-product packaged task
roots and their archive, package-manifest, case-manifest, and candidate-task
hashes were recovered.

The migration must therefore create a new current-format task revision. For
each task it records three different identities:

- the original logical task revision from the historical contract;
- the packaged execution revision used by the historical runner; and
- the new frozen task revision created by current `skill-evaluation`.

None of these digests is relabeled as another.

The converter is private orchestration. It reads only the manifest fields
needed to locate referenced payloads, verifies every referenced digest, maps
the packaged runtime and grading contract into the existing repository-task
authoring schema, and copies payload bytes into a temporary private authoring
tree. It then calls existing freeze and verification logic. It never writes
task or grader content into the migration manifest, receipt, dashboard events,
API, logs, or review artifacts.

The converter refuses a task when a required packaged field has no exact
current-format equivalent. It does not approximate or omit grading behavior.

### Exact reconstruction contract

The package contains the current-format authoring authority, but not as a
ready authoring directory. Reconstruction assembles that directory without
changing the authority:

| Current authoring input | Exact packaged source |
|---|---|
| `case.json` | `hidden/authority/case.json`, after its manifest digest is verified |
| candidate phase prompt | `candidateTask.path`, copied to the prompt path declared by `case.json` |
| repository snapshot | the verified `candidateSources[].bundle`, extracted under `repository_task.snapshot_dir` |
| authoring source revision | unchanged `repository_task.source_revision` from `hidden/authority/case.json` |
| packaged source identity | `candidateSources[].repositoryId`, `commit`, `tree`, bundle path, and bundle digest, recorded separately from the authoring source revision |
| criteria and judge prompt | the exact paths declared by `case.json` under `hidden/authority` |
| provenance and reference patch | the exact `repository_task.provenance_file` and `repository_task.admission.reference_patch` paths under `hidden/authority` |
| hidden grader entrypoints | `hidden/authority/judge-reference/grader/**`, with every file admitted by `hiddenAuthority.artifacts` |
| image, setup, grading, and admission checks | the unchanged `repository_task` object from `hidden/authority/case.json` |

Every copied file must appear in the packaged case manifest with the same
digest. The converter rejects undeclared files, missing files, digest changes,
multiple candidate source workspaces, an unpinned image, or any mismatch
between the outer package and hidden
authoring authority. The package's host-runtime and full-product metadata is
preserved as historical execution provenance; it does not replace or rewrite
the current authoring contract.

The authoring source revision and packaged source commit are different
namespaces and may differ. The migration preserves both and never treats one
as proof of the other.

### Representative repaired C06 correspondence

The repaired C06 package is the focused reconciliation fixture:

- source case: `devloop-registry-reentrant-regression`;
- original logical revision:
  `822b0954d49de9747b2ab0d0cd94ef62df00d756b3b581dc4735d5ef4f993c88`;
- packaged execution revision:
  `b82e897eacd1ccd5d2c49f2bff351def964db02f29d03f9abd4d788aca4453e8`;
- packaged case manifest:
  `88553f259109c84193bbad64604a994873423a3bfdec90245cbe63f711d0d892`;
- complete package manifest:
  `402e5a8d29001f0e5e93b227653ef79088c5147cc69bfc3f18f02cf7580eff31`;
- complete package archive:
  `e81531e9edbec6b08f176a86d84cd8b29902df4efd2c5358ec947b6eca7de6ea`;
- candidate source archive:
  `75501a5df35d9765b5c0f1d6b4d5ae3ad29c40b9544647627f56f3eccd74a8d2`;
- candidate prompt:
  `c89a23b29e6624d14345e4a63e1dd7ceb8a0fc8f098429c23a1b3924efbace5a`.

The older `dc794d37` carrier is not an allowed input. After reconstruction,
`freeze_case` creates a third, new frozen task revision. The receipt records
all three revisions and never uses one in place of another.

## Migration manifest

The migration accepts one exact JSON manifest. It rejects additional fields.
The manifest contains:

- `schema_version`, fixed at `1`;
- `migration_id`, fixed for this one migration;
- `output_root`, an empty destination owned by Assistant;
- one project ID, title, goal, and target skill;
- one exact evaluated candidate skill identity;
- exactly eight task entries; and
- an explicit list of unknown fields.

Each task entry contains:

- project task ID, title, summary, and required role (`development` or
  `regression`);
- source case ID;
- original logical task revision and packaged execution revision;
- exact complete-package archive, package manifest, packaged-case manifest,
  candidate prompt, and candidate source archive paths and digests;
- the private hidden-authority root and its admitted artifact inventory;
- an allowlist of safe source metadata fields;
- an explicit denylist of private fields and payloads that must not be
  projected;
- zero or more historical experiments; and
- the fields that remain unknown for that task.

Each historical experiment contains:

- experiment ID, immutable plan digest, treatment ID, and tested skill
  snapshot;
- the source-backed required repetitions and required passes for this task;
- the complete planned attempt IDs when known;
- for each attempt, its source result path and digest, terminal outcome, known
  cost and timestamps, and opaque source ID; and
- `population_complete`, which may be true only when the planned attempt set
  and exactly one valid terminal result per attempt are present.

The migration does not accept a guessed task role, inferred skill snapshot,
path-derived outcome, or a partial population marked complete.

The reconstructed frozen revision is output, not manifest input. The immutable
migration receipt records it after `freeze_case`, linked to the manifest
digest, original logical revision, and packaged execution revision. The
migration emits no historical experiment-selection event and assigns no
winner, published, or released status.

The migration does emit one current lineage declaration for the evaluated
candidate snapshot with role `integrated`. This role records that the snapshot
is the qualification subject integrated into the migrated dashboard project;
it does not assert that the historical experiment selected a winner. Its
summary and provenance identify the one-time migration, and its source
revision is the exact evaluated candidate skill digest. No control snapshot
receives a project lineage role.

### Historical experiment correspondence

The adapter does not invent a current experiment from the outcome alone. For
every historical attempt, it verifies the source handoff, retained result
archive, dispatch record, and proof receipt before constructing current
records.

| Current declaration or result field | Historical authority |
|---|---|
| `case_id` | explicit source case mapping |
| `case_revision` | newly reconstructed frozen revision, joined through the receipt to the original and packaged revisions |
| `treatment_id`, `repetition`, `attempt_id` | fixed source experiment plan |
| `candidate_model`, timeout | source attempt candidate record, cross-checked with dispatch |
| target OS, architecture, route, grading route | retained dispatch record |
| package, candidate-package, image, and dependency digests | retained dispatch controls and attempt identity |
| treatment content and target-skill identity | exact tested skill file plus the current snapshot builder |
| `required_passes_per_case` | `required_original_passes` in the source task's qualifying experiment candidate, cross-checked with `required_original_repetitions` and the fixed attempt IDs |
| terminal result | original terminal outcome, cross-checked with retained verification |
| deterministic target, regression, and product fields | retained verification booleans |
| independent behavioral verdicts | retained named judge verdicts |
| source lineage | retained archive digest and opaque source ID |

The experiment fingerprint, treatment identity, content fingerprint, snapshot
identity, and evaluator fingerprint are deterministic current-format
identities computed from those verified inputs. They are new representation
identities, not historical facts, and the receipt names their source fields.

An attempt is history-only when any mandatory current execution-identity field
cannot be recovered or cross-checked. Missing cost, wall time, or terminal
timestamp remains Not recorded and does not by itself block qualification.
Missing or conflicting required repetitions, required passes, or recorded
historical task verdict makes that task history-only. For a qualifying task,
the projected result must equal
`historical_per_task_threshold_met` from the digested source handoff.
The adapter emits a current terminal result only when
`validate_experiment_declaration`,
`validate_experiment_result_identity`, and the exact-population validator all
accept the reconstructed declaration and result without exceptions.

## Per-task migration states

The receipt records one state for each declared task:

- `migrated_qualifying`: the task and one complete fixed population passed all
  existing validators and may qualify normally;
- `migrated_history_only`: safe experiment history was recovered, but
  qualification-critical evidence is incomplete;
- `not_migrated`: required task identity or safe source evidence is missing or
  conflicting.

These are migration receipt states, not new dashboard result labels. The
dashboard continues to show Passing, Not passing, or Unavailable.

## Reuse contract

The implementation must reuse:

- `freeze_case` and `verify_case` for task versions;
- canonical project declaration and registration for project and task identity;
- experiment declaration and result validators for fixed populations;
- exact experiment population qualification for task results;
- the existing loopback API and browser projection; and
- immutable source digests and source IDs for provenance.

The only new mechanism is a bounded migration manifest and command. It is
needed because the source history predates the project declaration. It is not
a second task or result authority.

## Failure model

The migration can encounter a missing source path, changed digest, ambiguous
task mapping, missing role, missing skill revision, incomplete planned
population, duplicate attempt, conflicting result, or a result from another
task or skill revision. It records the failure for that task and continues
with independent tasks. It never substitutes a plausible value.

The complete migration is idempotent. The first run may receive campaign and
event identifiers from existing create-once owners. The receipt records those
identifiers and every created artifact digest. Running again against the same
output root with the same manifest and source bytes performs verification only:
it writes nothing and every recorded byte digest remains unchanged. Running
with changed input, a missing receipt, or changed output refuses replacement.
Byte identity is not defined as equality between two independently initialized
output roots.

Only one process writes the migration output. Existing atomic file creation and
immutable event conflict checks are sufficient; no migration lock service or
multi-writer protocol is added.

## Constraint provenance

| Constraint | Provenance | Protected outcome | Revisit condition |
|---|---|---|---|
| One-time bounded migration | User: "cant we just do a one time migration of their data?" | Avoids a permanent legacy subsystem | A second supported producer needs the same import |
| Incomplete data is allowed | User: "its ok if its incomplete" | Preserves useful history without fabrication | Required project identity cannot be supplied |
| Sufficient migrated evidence may qualify | User challenge: "why cant it qualify a task?" | Treats old and new valid evidence consistently | Existing validators cannot represent the recovered fixed population |
| Approved vocabulary only | User: "didnt we standardize our terms?" | Keeps the UI understandable | None for this migration |
| No source mutation | Existing immutable evidence authority | Preserves original outcomes and auditability | Never; use a new migration revision instead |

## Reframe gate

`CLEAR`: pass two found that the source contains packaged cases rather than
ready current-format roots. The corrected design specifies deterministic
private reconstruction, three separate task revisions, and field-by-field
experiment correspondence. Focused reconciliation cleared this exact action
for design review. Reframe again if qualification requires a new result type,
a second mutable store, inferred task identity, approximate grading, or
browser-owned authority.

## Acceptance criteria and check contract

| Acceptance criterion | Deterministic check |
|---|---|
| The migration is bounded to the declared eight tasks | A manifest schema rejects undeclared tasks and output contains no additional task IDs |
| Original evidence is unchanged | Source digests before and after migration are identical |
| Re-running is safe | A second invocation against the same receipt and output root performs no writes and all receipt-owned digests remain identical; changed input refuses replacement |
| Incomplete history remains useful | A fixture with missing cost and duration still renders known experiments |
| Sufficient history can qualify | A complete fixed population fixture produces Passing or Not passing according to its original results |
| Qualification uses an honest current subject | The evaluated candidate has one `integrated` lineage declaration, no experiment-selection event, and no winner, published, or released label |
| Historical thresholds are preserved | Every qualifying task's projected result equals its source `historical_per_task_threshold_met`; missing or conflicting thresholds produce Unavailable |
| Incomplete qualification stays unavailable | A missing, duplicate, extra, conflicting, or mismatched result produces Unavailable |
| Rescue attempts cannot alter the population | A later experiment does not change the migrated fixed denominator |
| Private evidence stays private | API and browser assertions reject private field names and values |
| The installed dashboard works end to end | A fresh installed-plugin projection shows the eight migrated tasks and expected results |
| Rollback is complete | Removing the migration registration and output restores the pre-migration project index |

## Migration and rollback

The migration writes a new bounded output root and registers it through the
existing local dashboard state. It refuses a pre-existing campaign or project
registration. Its receipt contains the manifest digest, source digests,
campaign identity, project declaration, every created registration path and
digest, and every per-task status.

Rollback first verifies that every receipt-owned path still has the recorded
identity and digest. Under the existing project lock, it removes only the
receipt-owned project registration file and archived global declaration, then
removes the project directory only when no foreign registrations or
declarations remain. Under the output corpus campaign lock, it removes only
the receipt-owned global campaign registration. It then verifies that the
project index equals its recorded pre-migration value before removing the
exact named output root. A mismatch or foreign artifact stops rollback without
deleting it. Source history is never edited.

## Design review

The critical design review is complete.

- Constraint challenge:
  - pass 1: `NARROW`;
  - pass 2: `REFRAME`;
  - corrected-action reconciliation: `NARROW`, cleared for review;
  - post-review reconciliation: `CONTINUE`, gate `CLEAR`.
- Dual review round 1:
  - both Claude Opus and GPT Terra completed with the design lens applied;
  - material findings covered lineage qualification, source-backed task
    thresholds, idempotence, and receipt-owned rollback.
- Dual review round 2:
  - both families verified every prior finding as resolved;
  - no material findings remain.

The reviewed implementation boundary is the one-time manifest, private
reconstruction adapter, existing validators and lineage owner, immutable
receipt, and exact rollback path described above.

## Current baton

- Phase: approved implementation under `development-loop`.
- External owner: `assistant@macbook-pro`
- Assignment: `assistant-one-time-migration-source-r1`
- Owned source boundary: Assistant's existing session artifacts; no repository
  writes.
- Consumed handoff:
  `/Users/dfrysinger/.copilot/session-state/6f7726ad-c851-4da9-bd16-ffbd015dd0f1/files/one-time-migration-source/eight-task-migration-source-r1.json`,
  SHA-256
  `e4fdb56b20d02549013b97b70733f2479cd425da82b4e41a749b2a0f13f6184a`.
- Source result: 46 fixed attempts; 30 completed outcomes (28 Positive and
  2 Negative); 16 explicit Not executed stops. The evaluated candidate has a
  complete 23-attempt population and the control does not.
- Consumed reconstruction handoff:
  `/Users/dfrysinger/.copilot/session-state/6f7726ad-c851-4da9-bd16-ffbd015dd0f1/files/one-time-migration-source/eight-task-private-reconstruction-roots.json`,
  SHA-256
  `ffa79be81efaa26916f85e2fe03e483301d53f560f9250167c6fa12fb11988e1`.
  No canonical roots were recovered; all eight verified private packaged roots
  are available for deterministic reconstruction.
- Coordinator workspace:
  `/Users/dfrysinger/.copilot/session-state/6f7726ad-c851-4da9-bd16-ffbd015dd0f1/files/skill-eval-ui-round5-worktree`
- Coordinator branch: `dfrysinger/skill-eval-one-time-migration`
- Implementation status: the bounded adapter, pre-judge Negative result
  contract, exact fixed-population admission, source-bundle reconstruction,
  source-alias correspondence audit, immutable receipt, no-write rerun, and
  receipt-owned rollback are implemented.
- Live source proof: the isolated migration reconstructed all eight tasks from
  the admitted packages and projected 46 fixed attempts, 30 completed
  measurements, candidate 22 Positive and 1 Negative, control 6 Positive and
  1 Negative with 16 incomplete attempts, seven Passing tasks, and C07 Not
  passing. Public projection contained no private path or grader detail.
- Validation status: 31 focused migration and result-contract regressions pass;
  the frozen full suite passes 548 tests with 56 skipped. Immutable rerun,
  receipt-owned rollback, verified absence, and clean replay all pass.
- Review status: both round-one findings and the round-two cleanup findings are
  resolved. Claude Opus and GPT Terra completed finding-scoped closure checks
  with no remaining material findings.
- Exact next action: commit, merge, install, run the real migration, verify
  installed correspondence and projection, and hand the supported route to
  Assistant.

## Definition of Done: One-Time Skill Evaluation History Migration

- The reviewed work order has a current constraint gate and dual design review.
- Assistant supplies an explicit eight-task source mapping with unknown fields
  identified.
- One bounded, idempotent migration imports the recoverable history without
  modifying source evidence.
- Every task with sufficient evidence receives the correct Passing or Not
  passing result; incomplete qualification-critical evidence is Unavailable.
- Later rescue experiments cannot change a migrated fixed population.
- The project dashboard shows the migrated project using only the approved
  vocabulary and without private evidence.
- Focused and full validation pass.
- Live source and installed-plugin proof pass against the same final candidate.
- Reviewed changes merge through a focused pull request.
- Exact merged files are installed and verified.
- Assistant receives and adopts the current project and experiment route for
  future work.
- The design and implementation reminders are stopped and verified absent.
