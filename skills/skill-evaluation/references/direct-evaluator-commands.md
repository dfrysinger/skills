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
historical fixture with `schema_version: 3`. This is model-free preparation,
not a behavioral run. It creates an empty namespace through the existing
importer, then stages the materialized recorded projection as native events.
It does not send the final recorded human trigger.

The fixture contains `provenance: "source-bound-historical"` and these fields:

- `recorded_context`: relative `path`, exact `sha256`, `reader_revision`,
  `original_runtime_revision`, and `cutoff_offset`. The reader and original
  runtime revisions are separate identities.
- `restoration`: `source_session_id`, `cutoff_event_id`, and
  `skill_context: "recorded-target-context"`.
- `trigger`: original `event_id`, `timestamp`, raw `content`, and
  `source_line_sha256`.
- `consumer`: selected `cli_version`, `cli_sha256`, and `sdk_sha256`.
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

Readback checks native event payloads and retained skills and reports the actual
permission mode. These checks do not establish the initialized model context.
Cold reasoning retention, system-context composition and the selected runtime's
post-resume projection still require model-free native observation. Internal
approval indices and source annotations are retained separately, not presented
as reconstructed authorization history. An assisted permission mode requires
the corresponding authentic authority evidence before an operation that uses it.

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
