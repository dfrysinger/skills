# Executable repository tasks

A `repository-task` case gives a candidate an editable source snapshot, captures
its patch, and grades that patch in fresh offline containers. Executable results
and independent behavioral judgments are separate. The evaluator does not
change the target skill.

## Author a case

```sh
python3 scripts/skill_eval.py add-case CORPUS CASE \
  --skill TARGET_SKILL --phase candidate --case-type repository-task
```

Keep the existing case metadata, one non-resumed phase, and the `judge` object.
Fill in the scaffold's `repository_task` object:

```json
{
  "snapshot_dir": "repository",
  "source_revision": "immutable-source-revision",
  "provenance_file": "judge-reference/provenance.json",
  "image": "sha256:REPLACE_WITH_64_LOWERCASE_HEX_DIGITS",
  "candidate_setup": [],
  "grading": {
    "setup": [],
    "target": {
      "argv": ["python3", "/grader/target.py"],
      "timeout_seconds": 60,
      "success_output_contains": "TARGET_CHECKS_PASSED: 4"
    },
    "regression": {
      "argv": ["python3", "/grader/regression.py"],
      "timeout_seconds": 60,
      "success_output_contains": "REGRESSION_CHECKS_PASSED: 4"
    }
  },
  "admission": {
    "reference_patch": "judge-reference/reference.patch",
    "base_target_failure": {
      "exit_code": 1,
      "output_contains": "specific assertion identifying the requested defect"
    }
  }
}
```

The image value accepts a local `sha256:...` ID or a repository reference pinned
with `@sha256:...`. The image must already exist locally. There is no automatic
pull or host-execution fallback.

```text
cases/CASE/
  case.json
  repository/
  evidence/candidate/task.md
  prompts/candidate.md
  criteria.md
  prompts/judge.md
  judge-reference/
    provenance.json
    reference.patch
    grading-partition.md
    grader/
      target.py
      regression.py
  capture/
```

Use ordinary source files, preserving executable modes. Symlinks, special
files, and `.git` are rejected when freezing source. Do not include ambient
caches, hidden answers, target-skill instructions, or auto-loaded local
plugins in the repository snapshot. The selected image must contain tools and
dependencies, not application history, hidden graders, reference repairs,
credentials, or ambient Copilot plugins.

Put exact task words and cutoff-available context in `evidence/candidate/`.
Keep the candidate prompt arm-neutral: the runner adds skill invocation only
for the skill arm. Record source event IDs, extraction digests, unavailable
authority, and any fixture adaptations in hidden provenance. An adapted
fixture is not an exact historical replay.

The hidden grader scripts must run substantive tests and reject empty
discovery. Each graded command must exit zero **and** emit its declared
`success_output_contains` text after its checks complete. A success marker
alone is not an adequate oracle. Document which original tests remain
regressions and which expectations intentionally change as part of the target
contract. Do not remove conflicting tests to make the reference green.

Setup commands use `argv` and `timeout_seconds`, without a success marker.
Commands run directly as argument arrays. Select a shell explicitly when
needed, for example `["sh", "-eu", "scripts/setup.sh"]`. Dependencies must
work offline in the pinned image. Candidate setup runs before the model in
its container. Grader setup runs independently before each target/regression
check. Prefer installing dependencies outside the source tree: generated
files inside that tree are included in patch capture, even when ignored by Git.

## Freeze and admit

```sh
python3 scripts/skill_eval.py freeze CORPUS --case CASE
python3 scripts/skill_eval.py verify CORPUS --case CASE
python3 scripts/skill_eval.py validate-case CORPUS --case CASE
```

The source and hidden grading packet join the existing digest-addressed case
root. Repository-task bundle manifests include source modes. Prose case
manifests retain their existing shape.

Admission runs candidate setup on base and reference source, then grades fresh
base and reference checkouts. It requires the declared base target failure,
healthy base regressions, and healthy reference target/regression checks.
Every setup command must succeed. Admission requires no model or credentials.

`admission-runs/` retains commands, exact raw logs, actual container mounts,
network settings, image identity, case revision, harness module digests, and
the admission receipt. A run requires successful admission matching its exact
case, image, and harness. Editing any harness module requires fresh admission.
The run rechecks retained admission artifact hashes.

## Run unchanged arms

The caller supplies `COPILOT_GITHUB_TOKEN` through its process environment.
The evaluator never acquires credentials or writes their values into command
receipts. Do not place credentials in case files or shell command arguments.

```sh
python3 scripts/skill_eval.py run CORPUS --case CASE \
  --plugin-dir PLUGIN --arm baseline --model MODEL --effort high \
  --timeout-seconds 1200

python3 scripts/skill_eval.py run CORPUS --case CASE \
  --plugin-dir PLUGIN --arm skill --model MODEL --effort high \
  --timeout-seconds 1200

python3 scripts/skill_eval.py run-suite CORPUS \
  --plugin-dir PLUGIN --arm skill --workers 3 --max-attempts 1
```

Both arms identify the same target plugin revision. Baseline does not mount or
load the plugin. Skill mounts the snapshot read-only and requires target-skill
invocation in the structured trajectory. Model, effort, candidate timeout,
task, and image should match across arms.

Repository candidates always use a fresh container-local home, regardless of
the prose runner's `--home-mode` setting. Independent behavioral judges use
the existing host Copilot executable, fresh isolated Copilot homes, and the
existing Claude/GPT judgment contract. `--copilot` selects that host judge
executable; the repository candidate uses `copilot` from its pinned image.

## Execution boundary

The candidate has `/workspace/repo` writable and `/evidence` read-only.
The skill arm additionally has `/plugin` read-only. The source gets a synthetic
base Git commit, never the original history or remotes. The candidate receives
no corpus root, hidden grader, reference patch, capture directory, sibling
run, host home, or Docker socket. Mount records reject unexpected image
volumes.

The available-tool allowlist includes local coding, shell-session management,
local agent coordination, and session-local SQL. It omits remote history,
web tools, extension management, and external MCP tools. Shell permissions
use the CLI's `shell` category. Custom instructions, built-in MCPs, remote
export/control, automatic updates, and BASH_ENV are disabled.

`--secret-env-vars=COPILOT_GITHUB_TOKEN` asks the CLI to remove that variable
from tool shell environments and redact its value from output. The token is
still present in the CLI process. This is **not** protection against arbitrary
process inspection.

Candidate network access is enabled. Receipts explicitly state
`network: enabled`, `credential_filter: cli-secret-env-vars`, and
`remote_history_isolation: not_enforced`. Local packet separation is not an
egress sandbox or protection against fetching externally available historical
solutions. Candidates are instructed not to retrieve those answers. Inspect
trajectories and judge findings for contamination; an observed retrieval must
not be described as a valid blind success. The executable score alone makes no
blindness claim.

After the candidate is stopped, a separate trusted checkout computes its
patch against frozen source. Candidate Git history, indexes, ignore rules,
attributes, and hooks do not establish that base. Capture includes new and
ignored files, deletions, executable-bit changes, and binary changes; it
excludes Git metadata. Unsupported candidate filesystem entries produce a
scored output failure rather than silently disappearing.

Each grading check gets a fresh patched source tree and the original hidden
entrypoints mounted read-only at `/grader`. Graders have no token or network.
Candidate changes to local test commands cannot replace those entrypoints.
This does not claim resistance to arbitrary candidate code monkeypatching a
test runtime.

The corpus directory must be available to Docker bind mounts. Runtime
directories are created beneath the run artifacts rather than the host's
potentially unshared system temporary directory.

## Results

`execution-result.json` is immutable execution evidence. Independent judges
receive it with the patch, full structured trajectory, logs, and hidden
criteria. `repository-result.json` adds the behavioral verdict without
rewriting the artifact the judges read.

Executable status is `PASS`, `FAIL`, or `INVALID`. Candidate budget exhaustion
is a scored failure. A failed patched grader, including broken setup or a
timeout, is scored against a fresh reference control. Healthy controls make
that a candidate failure; failing controls identify an invalid grading
environment. Missing image/authentication, pre-candidate setup failure, and
executor failures are invalid, not skill failures.

Judge failures are reported separately and do not rewrite executable
correctness. Raw partial output and any recoverable patch remain available
when execution fails or times out. Reported usage is retained verbatim;
unavailable token counts remain null.

Repository suite pass@1 is first-attempt executable passes divided by valid
first attempts. Requested count, valid count, invalid/error count, and coverage
are reported together. A candidate timeout remains in the denominator.
Retries and behavioral judgments cannot improve pass@1. Every retry remains
listed; overall suite success additionally requires independent behavioral
success. Suites snapshot the plugin and all harness modules and refuse a
case revision or harness change between attempts.

Add `--quality-review` to `run` or a repository-only `run-suite` for independent
source-only shipping assessments. This requests additional paid Claude/GPT
invocations using the case's judge models. Findings remain reviewer-reported;
they do not rewrite executable or behavioral results or trigger retries.

All attempts retain role-separated usage and full wall timing. Query their
authoritative artifacts with `history CORPUS --format json|markdown`.
See [measurement and quality history](measurement.md) for coverage, units,
failure handling and comparison populations.

## Toolchain example and focused checks

`examples/Dockerfile` is a generic starting point, not a prebuilt execution
dependency. Build it, inspect its resolved image ID, and put that exact ID in
the case. Add language dependencies deliberately; freeze a new case revision
when the image changes.

```sh
docker build -f examples/Dockerfile -t skill-eval-local .
docker image inspect skill-eval-local --format '{{.Id}}'

cd scripts
python3 -m unittest -q test_skill_eval test_repository_task.RepositoryTaskTests test_measurement
SKILL_EVAL_TEST_IMAGE=sha256:YOUR_IMAGE_ID \
  python3 -m unittest -q test_repository_task.DockerRepositoryTests
```

The optional Docker checks use only synthetic source and offline grading.
They are not evidence of target-skill quality or a real-model evaluation.
