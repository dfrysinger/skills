# Direct evaluator commands

These commands execute on the machine that starts them. Use them inside an
Actions task runtime, or locally when the user explicitly selects local model
execution under the [execution default](../SKILL.md#2-make-the-test-capable-of-observing-that-behavior).
They do not provision a VM or dispatch an Actions workflow.

The prose case path provides `skill` and `view`, not editing or command
execution. For coding tasks, follow the
[repository-task guide](repository-tasks.md). The task runtime must expose the
tools required by the task, regardless of where it runs.

Resolve `SKILL_DIR` to the evaluator skill directory, separate from the target
plugin snapshot.

## Recorded native context preparation

The existing `_run_native_context_calibration` producer accepts an owner-only
historical fixture with `schema_version: 3`. Without explicit continuation,
this is model-free preparation, not a behavioral run. It creates an empty namespace through the existing
importer using a session-header-only transport with the operational title
`owned-recorded-context`, then stages the materialized recorded projection as
native events. The title is not a source-original title claim. Import acceptance
does not replace verification of an actual owned journal before staging.
It does not send the final recorded human trigger.

The fixture contains `provenance: "source-bound-historical"` and these fields:

- `recorded_context`: relative `path`, exact `sha256`, `reader_revision`,
  `original_runtime_revision`, and `cutoff_offset`. The reader and original
  runtime revisions are separate identities.
- `restoration`: `source_session_id`, `cutoff_event_id`, and
  `skill_context: "recorded-target-context"`.
- `trigger`: original `event_id`, `timestamp`, raw `content`,
  `source_line_sha256`, and relative `source_event_path`. The path must name an
  owned, owner-only, unaliased single-link file under the fixture root containing
  the exact source `user.message` JSON line bytes without whitespace or line-ending normalization.
  Its hash, ID, timestamp and raw `data.content` must match the trigger.
  `data.transformedContent` must equal the final canonical user message; only an
  absent field falls back to raw content. Staging copies the exact bytes to
  `owner/source-trigger-event.jsonl`; native readback checks the same binding.
- `consumer`: selected `cli_version`, `cli_sha256`, and `sdk_sha256`.
- Optional `completed_objective`: relative `path` and exact `sha256` for an
  owned, owner-only, unaliased single-link source file under the fixture root.
  Staging copies its exact bytes to the fresh namespace's
  `autopilot-objective.json` before the first resume and retains an owner copy.
  An existing destination is never replaced.
- `snapshot`, `required_tools`, `limitations`, `personal_instructions`, and
  `candidate_permissions`, using the existing task and permission contracts.

Direct validation requires
`_validate_historical_context_fixture(fixture, root=fixture_file.parent)`.
The producer supplies this owner root itself. The task snapshot schema is
unchanged.

Staging retains the original artifact bytes, records canonical collection/index
and field digests, and refuses unknown message fields or unsupported selected
native schemas. Skill bodies, paths, source identifiers and invocation-turn
metadata remain captured data; the retained population is not fixed at seven.
The last user message stays in an owner-only deferred-trigger artifact.

The optional completed store has exactly `version: 1`, positive `nextId` and
`current`. Its completed `current` contains `id`, `objective`, `status`,
`autopilotOrigin`, `continuationCount`, `turnCount`, `tokenCount`,
`creditCountNanoAiu`, `resumeCount`, `createdAt` and `updatedAt`, with optional
string `completionSummary` and `pauseReason`. IDs/counters must be safe JSON
integers, `nextId` must exceed `id`, and credits must be a nonnegative decimal
string within the native signed 64-bit range. Timestamps must include a timezone.
Unknown fields, legacy/defaulted shapes and credit-limit objects are not accepted.
Warm/cold checks compare the complete persisted JSON values and the current-state
projection exposed by native `autopilotObjective.getState`; that getter does not
expose every stored field. Cleanup preserves the completed store without an
objective transition. Fixtures without this input remain goal-free.

Readback checks native event payloads and retained skills and reports the actual
permission mode. These checks do not establish the initialized model context.
Cold reasoning retention, system-context composition and the selected runtime's
post-resume projection still require model-free native observation. Internal
approval indices and source annotations are retained separately, not presented
as reconstructed authorization history. An assisted permission mode requires
the corresponding authentic authority evidence before an operation that uses it.

## Continue a recorded native session

The same producer accepts `continuation_file: Path | None = None`. Set
`model_send=True`, `source_preparation_only=False` and omit `calibration_root`
to continue schema3 input. Setup closes its writer before the candidate resumes
the same fresh UUID. The candidate sends the bound raw human event once, without
reimporting, changing the session mode, reactivating an objective or invoking a
skill on the owner's behalf. Model and effort must match the recorded selection.

The continuation file is an owned, owner-only, unaliased single-link JSON file:

```json
{
  "schema_version": 1,
  "purpose": "setup-canary",
  "running_in_interactive_mode": true,
  "session_capabilities": [
    "tui-hints", "plan-mode", "memory", "cli-documentation", "ask-user",
    "interactive-mode", "system-notifications", "elicitation", "session-store"
  ],
  "cli_preamble": "You are the GitHub Copilot CLI, a terminal assistant built by GitHub.",
  "executable_path": "/usr/local/bin:/usr/bin:/bin",
  "locale": "C.UTF-8",
  "timeout_ms": 180000,
  "package_root": "/owned/input",
  "workflow_commit": "<selected workflow's 40-character commit>",
  "workflow_sha256": "<expected workflow source SHA256>",
  "canary_receipt": null,
  "canary_checks": {
    "file": {"path": "result.txt", "sha256": "<expected file SHA256>"},
    "shell": {"command": "<exact authored shell command>"},
    "sql": {"query": "<exact authored SELECT query>"}
  }
}
```

`package_root` contains only `evaluator/`, `plugins/` and `owner/`.
Owner inputs are `context-fixture.json`, `completed-objective.json`,
`recorded-context.json`, `source-event.json`, `continuation.json` and optional
`calibration-evidence/`. Keep the fresh run directory outside this package.
Repository checkouts, symlinks, judge/criteria files and later diagnoses are
refused. These checks are not a filesystem sandbox or a complete content audit.
The owner must omit private inputs from the job. The selected workflow commit
must match `GITHUB_WORKFLOW_SHA` when available. Retain and verify its exact
source through the existing authenticated read after the candidate stops.
The owner must verify `workflow_sha256` before admitting its result or using
the compact canary receipt. Common configuration binds those source bytes,
not unrelated changes elsewhere in the workflow repository.

The synthetic `setup-canary` purpose needs minimal prior context, an ordinary
bound source event, and an authored file/shell/SQL request. It does not need
the historical transcript or a target-skill invocation. A successful result
requires an actual changed file with the expected hash, a matching successful
shell event with native `shellExecution.exitCode=0`, and a matching successful
SQL event with nonempty result content and positive native row telemetry.
No retry is automatic.

The producer returns `candidate`, `observe`, `cleanup` and, for a successful
canary, a compact `continuation_receipt`. For `purpose="historical"`, set
`canary_checks=null` and embed that exact receipt in `canary_receipt`.
Admission binds evaluator and helper bytes, CLI/SDK hashes, plugin and personal
instructions and personal skill collections, model/effort, interactive options,
PATH, locale, timeout and workflow source hash.
Fresh UUIDs and the different tiny/historical task inputs are not common settings.
Missing, mismatched and noninteractive receipts refuse before historical send.

Continuation uses native interactive options and preamble-only customization,
not an identity-group transform. Native permission RPCs must successfully select
`allow-all`, configure unrestricted paths/URLs and report that mode. Managed
policy remains enabled; there is no `approveAll` callback. The explicit child
environment retains reasoning and the normal inference authentication channel,
without `COPILOT_PLAN_THEN_AUTOPILOT` or retained authentication values.

The candidate retains fresh primary system events, including content blocks,
correlated to the new user's interaction. Interactive identity is checked after
dispatch. This passive observation is not a pre-provider barrier. Wrong primary
identity, a changed prefix, duplicate/substituted user input or changed frozen
inputs invalidate the attempt as setup/fidelity evidence, not a skill result.
Ordinary completion requires a correlated root assistant response and idle.
A real input callback instead yields `HUMAN_INPUT_PENDING`; no answer or
automatic continuation is supplied. The owner freezes its interpretation.

After model actions, tools, skill loads and task/objective edits are retained as
behavior. Final native state and tool effects are recorded before owned shutdown
and separate cleanup observation. Cleanup does not reinstall the source snapshot.
`CANDIDATE_OBSERVED` and canary success do not establish full discovery, all CLI
defaults, complete historical state or a behavioral baseline.

## Prepare a case

Scaffold a new corpus and case when no reusable frozen case exists:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" init CORPUS
python3 "$SKILL_DIR/scripts/skill_eval.py" add-case CORPUS CASE_ID \
  --skill TARGET_SKILL --phase candidate
```

Repeat `--phase` for ordered phases. Populate the candidate evidence and hidden
criteria using the [case contract](case-contract.md), then freeze and verify
before execution. Historical packets keep original request, restored context
and evaluation-only operations distinct; map each addition to source evidence.

## Run a case or suite

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
release regression gate. For predeclared bounded retries, use `--max-attempts N`
to retry only cases that did not reach unanimous `PASS`; every attempt remains
preserved and the report identifies cases that passed after retry. The suite
command writes one aggregate report while preserving each case's independent
run, receipts, and judgments.

Use `--home-mode isolated` when `COPILOT_GITHUB_TOKEN` is available. The default
`existing` mode uses the current authenticated Copilot home while still
disabling custom instructions and built-in MCP servers; its receipt states that
the authentication home was shared.

For dashboard-tracked work, bind the exact snapshot and give the run a goal:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run-suite CORPUS \
  --plugin-dir /path/to/plugin \
  --dashboard-snapshot SNAPSHOT_ID \
  --run-goal "Check whether the current revision passes every declared task"
```

Project-aware `run` and `run-suite` refuse to start without `--run-goal`.

## Repository tasks and treatments

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

The only external candidate runner supported by these direct commands is the
Sandcastle sequential reviewer adapter:

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
produce exact candidate credits. This adapter does not authorize an execution
method change.

For repository tasks, `--quality-review` adds paid, independent source-only
shipping assessments without changing correctness or retry policy.

## Inspect local result files

These commands read history; they do not launch model calls:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" history CORPUS --format markdown
python3 "$SKILL_DIR/scripts/skill_eval.py" history CORPUS --format json
```
