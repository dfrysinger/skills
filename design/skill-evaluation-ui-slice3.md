# Skill Evaluation UI Slice 3: Lineage and Task Progress

## Status

Approved for implementation. The independent constraint challenge and dual
design review are clear.

## Objective

Extend the merged read-only local dashboard so a user can understand the exact
shared skill-set lineage and the real progress within each corpus task. The
slice must bind every claim to an immutable skill snapshot, frozen case
revision, evaluator result, or explicit workflow-authored progress record. It
must never turn directory names, Git state, candidate prose, or partial live
activity into release or correctness authority.

## User value

The campaign view will answer:

- Which exact skill-set revision is original, published, integrated,
  experimental, passing, or released?
- What changed between the original, a selected parent, and the current shared
  revision?
- Which tasks are green, failing, blocked, stale, or missing progress evidence?
- For a failing task, where is the earliest remaining failure frontier, how is
  the failure classified, did the changed instructions affect behavior, and
  did the product move?
- Which tasks need attention now?

## Scope

This slice adds:

1. immutable snapshots containing exact bytes only from explicitly named
   target-skill roots, with typed manifests and no browser file or raw-byte
   route; content-addressed storage is optional and is not an acceptance
   requirement;
2. strict lineage event variants in the existing append-only dashboard journal
   binding snapshots to roles and parents;
3. exact typed comparisons needed by a lineage or task view between explicitly
   referenced admitted snapshots;
4. strict task-progress event variants in the existing journal, bound to an
   exact case revision and skill snapshot;
5. a campaign lineage summary and attention queue;
6. a task-detail view with completed outcomes, current activity, progress
   evidence, and relevant skill comparisons;
7. deterministic unit, integration, installed-plugin, browser, and visual
   proof.

## Non-goals

- Starting, stopping, retrying, publishing, editing, or qualifying work from
  the browser.
- Cloud or distributed-run discovery and control.
- Experiment hypotheses, treatment arms, repetitions, finalist selection, or
  causal claims.
- Ablation campaigns or retained-rule accounting.
- Inferring publication or release from Git branches, tags, directory names,
  timestamps, installed-plugin recency, or candidate output.
- Browsing arbitrary repositories, plugin trees, corpus files, candidate
  workdirs, judge references, raw logs, or content-addressed blobs.
- Replacing immutable evaluator history as correctness authority.

## System classification

This is **systemic and security-sensitive**. It introduces a persistent
artifact contract, concurrent writers, and a new surface that summarizes skill
source changes. The design therefore requires fail-closed typed readers,
content-bound identities, an independent constraint challenge, dual design
review, installed-plugin proof, and implementation review before landing.

## Decision hierarchy

1. Exact user decisions in
   `design/skill-evaluation-ui-slice3-decisions.json`.
2. The Foundation boundaries and authority order in
   `design/skill-evaluation-ui.md`.
3. Frozen evaluator artifacts for completed correctness.
4. Validated immutable Slice 3 snapshots, declarations, and progress records.
5. Validated Foundation live session and attempt state.
6. Explicit unavailable, unknown, stale, or conflicted state.

No lower source may upgrade a higher source.

## Constraint provenance and reframe gate

| Constraint | Source | Binding interpretation |
|---|---|---|
| Browser is read-only | User: `"read only"` | No browser mutation endpoint or execution control |
| Many sessions may be active | User: `"yes but there could be many active session"` | Append-only writer-scoped records; no shared mutable current record |
| Show skill changes and per-task progress | Original user request | Exact bounded comparisons and typed progress evidence are in scope |
| Preserve evaluator authority | Foundation design and evaluator contracts | Progress and live records never create PASS |
| No arbitrary browsing or hidden evidence | Foundation objective | Only typed projections; no raw path or blob route |
| Slice 4 and Slice 5 remain separate | Foundation design | No experiment/cloud or ablation mechanics |

Reframe is required before implementation if the design would need to:

- expose raw filesystem or blob reads to the browser;
- copy a complete arbitrary plugin tree into shared dashboard state;
- infer released or passing state from an untrusted source;
- introduce a mutable database;
- change evaluator correctness semantics;
- make experiment, cloud, or ablation mechanics necessary for Slice 3.

No revisit condition is currently open.

## Artifact model

All Slice 3 artifacts live in the existing corpus-local dashboard root. The
global service state continues to hold only campaign registrations and service
state:

```text
CORPUS/.skill-evaluation-ui/snapshots/<snapshot-id>/
  manifest.json
  files/<skill-name>/<relative-path>

CORPUS/.skill-evaluation-ui/events/<sha256(canonical-writer)>/
  <foundation-event-id>.json
  extensions/skill-lineage-v1/<event-id>.json
  extensions/skill-lineage-v1/conflicts/...
```

Snapshots use bounded immutable publication. Lineage and progress are new
strictly validated extension-record variants in the existing writer journal.
They reuse `dashboard_state.writer_directory`, writer identity,
exclusive-create publication, idempotency, and visible-conflict behavior.
They are not added to the Foundation `EVENT_TYPES` set and are not written as
top-level event JSON files. Foundation readers enumerate only top-level event
JSON and therefore ignore the versioned extension directory during rollback or
mixed-version operation. The Slice 3 reader enumerates that directory and
isolates each malformed extension record without hiding valid siblings.
Reusing an extension event identity with identical bytes is idempotent.
Reusing it with different bytes is retained as a conflict and never replaces
the first record.

### Skill-set snapshot

A trusted CLI producer publishes a snapshot from:

- one resolved plugin directory;
- one or more exact target-skill names;
- the regular files rooted at `skills/<skill-name>/`.

Capture rules:

- resolve and validate the plugin and skill roots before reading;
- reject absolute or escaping manifest paths;
- reject symlinks at every traversed component;
- reject non-regular files;
- select files with the evaluator's existing target-skill inclusion contract,
  excluding `.git`, `__pycache__`, `*.pyc`, and `.DS_Store`;
- read each file once into a temporary byte object, hash those exact bytes,
  stage those bytes inside a hidden temporary snapshot directory, write and
  fsync the manifest last, then atomically rename the completed directory;
- never expose the source plugin path through the browser projection;
- bind the sorted skill names, relative file paths, modes, byte counts,
  SHA-256 values, aggregate skill fingerprints, and aggregate snapshot
  fingerprint;
- admit binary files to identity and size accounting but render only
  metadata for binary changes;
- admit UTF-8 text to exact line accounting and generated unified diffs;
- verify every referenced snapshot file against the manifest before accepting
  the snapshot.

The snapshot ID is the SHA-256 of canonical identity-bearing manifest data.
Timestamps, source paths, summaries, roles, and parents do not affect it.
Implementations may internally deduplicate identical files, but callers,
projections, acceptance checks, and recovery semantics do not depend on a blob
store.

Each skill entry also stores `evaluator_skill_identity`, calculated exactly as
`evaluation_history` does:

```text
fingerprint({
  "name": skill_name,
  "files": [{"path": relative_path, "sha256": file_sha256}, ...]
})
```

The file list is sorted and contains exactly the evaluator-admitted files.
Modes, byte counts, and the aggregate Slice 3 snapshot ID do not participate in
that per-skill evaluator identity.

### Lineage declaration

A declaration binds one admitted snapshot to:

- one or more declared roles from `original`, `published`, `integrated`,
  `experimental`, or `released`;
- zero or more admitted parent snapshot IDs;
- a parent relation from `derived_from`, `integrates`, or `releases`;
- a bounded human summary;
- optional provenance kind and opaque source revision.

Rules:

- a snapshot may receive additional roles through later declarations;
- `original`, `published`, `integrated`, and `released` require a snapshot whose
  member skill set exactly equals the campaign's current target-skill set;
  `experimental` may identify a strict subset but cannot become a
  campaign-level passing tip;
- `original` and `published` are campaign baselines, not PASS claims;
- `released` is an explicit workflow declaration, not a correctness claim;
- `passing` is never declared; it is derived only from immutable evaluator
  populations carrying the exact admitted Slice 3 snapshot ID;
- a declaration cannot point outside the campaign;
- self-parenting and cycles are invalid;
- missing parents leave the declaration unavailable rather than silently
  creating a root;
- conflicting current integrated or released tips remain visibly conflicted.

### Task-progress record

A progress record binds:

- campaign ID;
- frozen case ID and exact case root digest;
- exact skill-set snapshot ID;
- optional comparison snapshot ID;
- failure frontier stage and bounded summary;
- failure classification;
- instruction-uptake rows;
- product-movement classification;
- optional blocker and next safe action;
- safe source identifiers;
- writer identity and event identity.

Enums:

- failure classification:
  `skill_defect`, `instruction_interaction`, `execution_variance`,
  `packet_defect`, `harness_defect`, `grading_defect`, `authority_limit`,
  `product_limit`, or `unknown`;
- uptake:
  `OBSERVED`, `PARTIAL`, `ABSENT`, or `NOT_APPLICABLE`;
- movement:
  `Conquered`, `Strict improvement`, `Mixed`, `No signal`, `Regression`, or
  `Unknown`;
- frontier stage:
  `admission`, `candidate`, `executable`, `behavioral`, `quality`,
  `qualification`, `release`, or `unknown`.

Safe source identifiers are typed references to admitted attempt IDs, report
IDs, session event IDs, or review receipt IDs. They are labels only and do not
create a generic file-read route.

The latest valid record for the same case revision and snapshot is selected by
its explicit `observed_at` time. Records for different revisions or snapshots
remain historical. Multiple incompatible records at the maximum
`observed_at` remain conflicted; event identity provides stable display order
only and never resolves the conflict. A later reconciliation uses a strictly
later `observed_at`.

The task's associated snapshot is the unique current `integrated` tip. A
current role tip is a snapshot carrying that role with no descendant carrying
the same role. If there is no integrated tip, the unique current `released`
tip is used. Multiple current tips are conflicted; absence is unavailable.
Task progress and missing-progress attention are evaluated only for that
associated snapshot and the current frozen case revision.

### Evaluator snapshot binding

The evaluator receives an optional explicit dashboard snapshot ID when running
a case or suite. Before model execution it:

1. loads the snapshot from the same registered campaign;
2. creates the evaluator's normal pinned run or suite plugin copy;
3. verifies every snapshot member skill against that pinned copy's exact bytes,
   never against the mutable source plugin directory;
4. verifies the case's effective entry skill is a snapshot member;
5. writes an immutable `lineage-identity.json` run artifact binding campaign
   ID, snapshot ID, the run's complete plugin identity, and every per-skill
   evaluator identity;
6. preserves that artifact through history validation and exposes the exact
   snapshot ID in the completed population.

History validation recomputes every bound member's evaluator identity from the
already validated `plugin-identity.json` file list for the pinned copy by
filtering `skills/<skill-name>/`, stripping that prefix, and fingerprinting the
exact `{name, files:[{path, sha256}]}` shape. Any missing, extra, mismatched, or
ambiguous member invalidates the lineage binding. The dashboard projection
consumes only this independently verified history field, not the raw
`lineage-identity.json` claim.

An unbound run still contributes its normal task outcome but cannot make a
lineage snapshot `passing`. A snapshot is observed campaign-level `passing`
only from one validated aggregate `run-suite` report that:

- is bound to that exact snapshot ID;
- uses one complete plugin identity across the suite;
- covers every current frozen campaign case and exact case revision;
- covers the campaign's complete current target-skill set;
- reports authoritative PASS for every included case; and
- binds the suite's one model, effort, arm, treatment, runner, adapter, harness,
  timeout, image, and quality-review contract.

Individual case runs remain visible on task detail but never combine into a
campaign-level passing claim. Separate suite reports also never pool outcomes.
This prevents passes from different combined skill revisions or evaluation
contracts from manufacturing one green shared revision. Missing, mismatched,
partial, mixed, or legacy bindings leave snapshot passing unavailable.

## Projection and authority

The dashboard projection validates artifacts independently:

1. load and validate snapshot manifests and their bounded immutable files;
2. load declarations, reject missing references and cyclic graphs;
3. verify evaluator `lineage-identity.json` artifacts and match completed
   populations to the exact bound snapshot ID;
4. load progress records only when case revision and snapshot are admitted;
5. reconcile Foundation live state without upgrading correctness;
6. emit typed lineage, task-detail, and attention projections.

The projection exposes:

- snapshot IDs and aggregate fingerprints;
- declared and observed roles with explicit authority labels;
- parent relationships;
- per-skill and per-file change metadata;
- exact unified text diffs only for admitted snapshot pairs explicitly needed
  by a declared lineage or task projection;
- binary-change metadata without bytes;
- task outcomes and progress fields;
- conflict and unavailable reasons.

It never exposes source plugin paths, snapshot file paths, arbitrary paths,
stored file bytes, raw evaluator files, hidden references, or unrestricted
candidate content.

## Diff semantics

A comparison is valid only when both snapshots are explicitly referenced by a
lineage or task view and admitted to the same campaign. Files are keyed by
`(skill_name, relative_path)`. The projection does not provide a general
snapshot browser or arbitrary comparison selector.

The exact summary reports:

- skills added, removed, and retained;
- files added, removed, modified, and unchanged;
- byte delta;
- text line additions and deletions;
- binary changes;
- aggregate fingerprints for both sides.

For UTF-8 text without NUL bytes, the server generates a deterministic unified
diff from validated blob bytes using stable labels:

```text
<skill>/<path>@<short-from-id>
<skill>/<path>@<short-to-id>
```

For binary or undecodable content, the API returns hashes, modes, and byte
counts only. No comparison route accepts filesystem paths. A request for an
unknown, cross-campaign, malformed, or unvalidated snapshot fails closed.

## Read-only API

Existing authenticated campaign APIs are extended with typed lineage, focused
task, and bounded comparison projections. Route decomposition is an
implementation choice. The existing generation-scoped capability is required.
No route accepts a filesystem path or serves stored snapshot bytes.

## CLI producer surface

The dashboard UI remains read-only. Trusted workflow producers use explicit
CLI commands:

```sh
python3 skill_eval.py dashboard lineage-snapshot CORPUS \
  --plugin-dir PLUGIN --skill SKILL [--skill SKILL] \
  --session-id SESSION_UUID --event-id EVENT_ID \
  --role integrated --parent SNAPSHOT_ID \
  --summary "Combined the proven task fixes"

python3 skill_eval.py dashboard task-progress CORPUS \
  --session-id SESSION_UUID --event-id EVENT_ID \
  --case CASE_ID --snapshot SNAPSHOT_ID \
  --frontier behavioral \
  --classification skill_defect \
  --movement "Strict improvement" \
  --summary "Executable checks pass; behavioral review still fails"

python3 skill_eval.py run-suite CORPUS \
  --plugin-dir PLUGIN --dashboard-snapshot SNAPSHOT_ID
```

Instruction-uptake rows and safe source identifiers use repeatable structured
arguments or a strict JSON input file. The command validates the frozen case,
exact case digest, campaign membership, snapshot, enums, and bounds before
publishing. `run` and `run-suite` validate the snapshot binding before any
model execution and preserve it in immutable history.

## User interface

### Campaign view

Add:

- a lineage strip showing original, published, integrated, passing, and
  released tips with authority badges;
- a compact comparison card for original-to-integrated and
  integrated-to-released movement when available;
- a compact attention view containing explicit blockers, conflicted evidence,
  current authoritative FAIL/UNANSWERABLE, stale active work, and missing
  progress evidence only for active or currently failing tasks;
- task rows linking to detail while retaining Foundation outcomes, live state,
  cost, and timing.

### Task detail

Show:

- frozen case identity and current immutable outcome;
- current local assignments and attempts;
- the task's associated snapshot and one relevant admitted lineage comparison;
- earliest failure frontier;
- failure classification;
- instruction-uptake rows;
- product movement;
- blocker and next safe action;
- source identifiers as inert labels;
- explicit unavailable, stale, or conflicted states.

The visual hierarchy must make correctness authority distinguishable from
workflow progress. A green uptake badge must never look like a PASS verdict.
Source identifiers remain inert labels. The task view does not provide
arbitrary snapshot selection or evidence browsing. Exact attention ordering is
presentation logic, not a persistent contract.

## Failure model

- Invalid snapshot capture publishes nothing.
- A snapshot file hash mismatch invalidates the dependent snapshot.
- A malformed Slice 3 extension record is isolated; it does not hide valid
  Foundation events or valid sibling extension records.
- Conflicting identifiers are retained under conflicts and surfaced.
- Missing or cyclic parents invalidate only the affected lineage declaration.
- A mismatched case revision or snapshot invalidates the progress record.
- A declared released role without exact snapshot-bound evaluator PASS remains
  released-by-workflow and not passing.
- Legacy campaigns render Foundation data and explicit lineage/progress
  unavailability.
- Server restart rebuilds the projection from immutable artifacts.

## Rollback

The slice is additive. Foundation event schemas and top-level event files remain
unchanged. Rollback removes the new producer commands, readers, routes, and UI
projections; Foundation readers ignore `snapshots/` and the versioned extension
subdirectories, leaving lineage state unread and harmless. Foundation artifacts
and routes remain valid. A failed rollout must not rewrite or migrate
Foundation state. The tolerant Slice 3 extension reader and projection ship
before or with the first Slice 3 writer.

## Delivery slices

Slice 3 is one smallest useful end-to-end release:

1. design, challenge, and dual review;
2. snapshot/declaration/progress schemas and safe writers;
3. typed projection and read-only API;
4. campaign and task-detail UI;
5. deterministic tests and installed-plugin proof;
6. visual proof and dual implementation review;
7. commit, push, PR, green checks, merge, and merged-byte verification.

No Slice 4 work begins before Slice 3 is merged.

## Check contract

The candidate is the exact commit proposed for merge. Required checks:

1. targeted state, projection, server, CLI, evaluator, and UI tests;
2. full existing `skill-evaluation` test matrix;
3. state-boundary tests for traversal, symlink, non-regular file, hash
   mismatch, conflict, cycle, cross-campaign, and revision mismatch;
4. installed-plugin producer-to-browser proof using a populated corpus and at
   least two exact snapshots;
5. installed-plugin proof that immutable PASS authority cannot be manufactured
   by a lineage or progress declaration;
6. browser proof for campaign lineage, attention queue, task detail, exact
   text diff, binary metadata, unavailable legacy state, and invalid
   capability;
7. responsive light, dark, and mobile captures;
8. dual implementation review against the exact committed candidate;
9. PR checks green and merged content verified byte-for-byte.

The acceptance fixtures must additionally prove:

- an exact target-skill snapshot remains comparable after its source changes;
- capture uses the same exclusions and per-skill identity algorithm as the
  evaluator, including a source tree containing ignored cache/Finder files;
- whole-plugin capture and symlink, escape, or non-regular target-skill input
  are refused;
- Foundation readers ignore Slice 3 extension records, malformed Slice 3
  siblings do not hide valid records, and existing journal idempotency and
  visible-conflict behavior are preserved;
- no event or unbound/mismatched evaluator result can manufacture PASS;
- a multi-skill snapshot cannot pool passing cases from different snapshots,
  plugin identities, suite reports, or evaluation contracts;
- mutating the source plugin after snapshot publication but before evaluator
  pinning either produces an exact matching pinned copy or aborts the binding
  before model execution; it can never bless different executed bytes;
- task and attention projections expose no arbitrary path or stored bytes.

## Current baton

- **Workspace:**
  `/Users/dfrysinger/.copilot/session-state/6f7726ad-c851-4da9-bd16-ffbd015dd0f1/files/skill-eval-ui-slice3-worktree`
- **Branch:** `dfrysinger/skill-eval-ui-slice3`
- **Base:** `68f289a098286f8980161097e64ee53e21feba53`
- **Critical path:** implementation -> installed proof -> dual implementation
  review -> landing
- **Phase:** dual implementation review
- **Implementation gate:** open
- **Last constraint challenge:** focused reconciliation and completed dual
  design review permit the exact bounded implementation.
- **Event trigger:** none unserviced
- **Relevant user direction:** `user-slice3-authorization` in the decision
  record
- **Open reframe:** none
- **Delegated owners:** none
- **Design review:** Claude Opus 5.5 and GPT 5.6 Terra completed three bounded
  rounds. Round 3 verified the pinned-byte authority repair; no material
  finding remains.
- **Implementation evidence:** immutable snapshot and extension state,
  pinned-byte evaluator binding, independently validated history, lineage and
  task projection, trusted CLI producers, campaign and task UI, and 77 focused
  tests are complete.
- **Deterministic evidence:** the eight-module matrix passes 387 tests with 49
  skipped; Python compilation, JavaScript syntax, and diff checks pass.
- **Installed proof:** four validator-accepted receipts under
  `files/slice3-lineage-proof-commit/` cover campaign lineage, exact task
  detail, conflict plus legacy behavior, and invalid capability refusal.
  Desktop dark, mobile light, task light, conflict dark, legacy light, and
  refusal light captures were opened and passed pixel-spread and overflow
  checks.
- **Implementation commit:** `bbb312fdfb6ea2c67e77b2e44ca2dab13ed8007b`
- **Committed proof candidate:**
  `sha256:518d4763f9b4c142e9bab9b7a6ea16cb2c5e330c9f2c62aab21406b002550de6`
- **Next action:** run dual implementation review against the exact committed
  candidate, close any verified material findings, then push and open the PR.

## Definition of Done: Skill Evaluation UI Slice 3

- [x] The focused decision record, sealed evidence packet, constraint
      provenance, reframe gate, and work order are complete.
- [x] An independent two-pass constraint challenge permits the exact
      implementation scope.
- [x] Dual design review has no unresolved material finding.
- [x] Immutable bounded skill-set snapshots plus lineage and task-progress
      variants in the existing append-only journal are implemented fail
      closed.
- [x] Passing is derived only from immutable exact-identity evaluator results.
- [x] The read-only campaign view shows exact lineage, useful comparisons, and
      a derived attention queue.
- [x] The read-only task-detail view shows exact outcome, live activity,
      frontier, classification, uptake, movement, blocker, and safe source
      identifiers.
- [x] No route exposes arbitrary paths, stored snapshot bytes, plugin trees,
      hidden judge evidence, candidate workdirs, or raw logs.
- [x] Legacy Foundation campaigns remain supported with explicit unavailable
      lineage/progress state.
- [x] Targeted and full test matrices pass on the exact candidate.
- [x] Installed-plugin proof demonstrates publication, reconciliation,
      comparison, conflict, recovery, browser, and security boundaries.
- [x] Light, dark, mobile, unavailable, conflicted, and invalid-capability
      states are visually inspected and accepted.
- [ ] Dual implementation review reports no unresolved material finding
      against the exact committed candidate.
- [ ] The slice is committed, pushed, reviewed in a PR, passes required checks,
      is merged, and merged bytes match the reviewed candidate.
- [ ] The plan baton records the final commit, proof receipts, review receipts,
      PR, merge commit, and schedule cleanup.
- [ ] Both unattended schedules are stopped and verified absent.
