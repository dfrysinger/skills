# Editable work with native state tools

## Objective and scope

Let one isolated resumed candidate patch an approved file, run an approved
check, and use its native SQL and scheduling tools through the existing SDK
execution path.

This is an evaluator capability change. It does not establish a historical
reproduction, a skill improvement, or completion of an original product task.
The supported caller is an imported native-workflow phase with a small
editable workspace and literal owner-approved commands.

Non-goals: a new runner, controller, service, dashboard, arbitrary tool grants,
another permission system, blanket approvals, credential collection, live-agent
control, production changes, waking schedules, native objective completion,
full repository-task/SDK unification, or a new historical-state schema.
The ordinary repository CLI route remains unchanged. Full repository-task
handoff and original task/controller fidelity remain separate requirements;
this focused capability fixture does not satisfy them.

## Status, lane and ownership

Lane: **critical**, because this extends model-controlled write and shell
authority. Design status: `ACCEPTED`. Reframe status: `CLEAR`.

Both independent design families closed the fixed-check finding on contract
SHA256 `3aebe7b107658712e33b99d0ec6578c2fedda20228311496b1b8aa01cb058242`
after current constraint reconciliation. This status-only handoff permits
the existing development-loop to implement the accepted contract under the
standing instruction. It does not establish A1-A6 or clear runtime invocation.

The existing evaluator owns invocation, input staging and artifact collection.
The existing native-workflow Python module owns phase validation and SDK
configuration. Its existing Node helper owns SDK session options, permission
decisions, native metadata, model completion, state observation and cleanup.
One coordinator owns source and integration. Reviewers remain read-only.
The candidate owns only its isolated fixture and session state. No conflicting
writers or shared-state coordination mechanism is introduced.

## Evidence and reuse contract

The ordinary repository invocation already supports literal file and command
grants, but does not enter the SDK state-tool path. Adding CLI flags alone is
not a supported composition.

The existing SDK path enables scheduling, observes real native metadata and
uses an approve-once permission handler. It selects exactly `skill`, `view`,
`sql` and `manage_schedule`; its handler has no write or shell branch.
Retained execution proves that four-tool path, correlated read approval and
refusal, native SQL/schedule effects, unchanged goal/mode and cleanup. It does
not prove editable SDK operations.

Reuse those owners. Extend the phase's existing `native_workflow` object with
optional `candidate_permissions`, containing exactly `write_paths` and
`shell_commands`. Reuse `session_restore.permission_rules` for its established
literal-input validation, not its CLI flag encoding as SDK authority.
Keep permissions outside candidate-visible evidence in the existing owned
configuration. Do not change the native state schema or profile identity.

Absent permissions preserve the current four-tool configuration and read-only
handler. With a valid nonempty `write_paths`, add only `apply_patch`; with
nonempty `shell_commands`, add only `bash`. Empty lists add no capability.
Pass the validated profile through existing phase/configuration owners to the
existing helper. Derive metadata expectations and event/tool auditing from
that same selection. Do not hard-code a new independent allowlist elsewhere.

Affected files are the existing native-workflow Python module and test,
the existing Node helper and test, and the existing evaluator's reached
invocation/event-parsing tests. No new execution entry point is needed.

## Constraint provenance

| Constraint | Authority and protected result | Revisit condition |
| --- | --- | --- |
| Existing private Actions evaluator | Direct user execution boundary; avoids duplicate infrastructure | User selects a different execution method |
| Actual combined operations under normal permissions | User outcome; availability alone cannot establish executed recovery | Required operation or caller changes |
| Explicit literal writes and commands; unchanged defaults | Existing supported permission contract and no-bypass boundary | Evidence shows a permitted caller cannot use that contract |
| Isolated workspace, homes and native session | User excludes live-agent/production mutation; model actions must not reach those assets | A required dependency exists outside the isolated fixture |
| Preserve history, instruction sources and goal/mode | Existing native caller contract; prevents coached or fabricated continuation | A separately reviewed claim requires a different native transition |
| Non-executing fixed check for this setup fixture | Current containment claim; matching a command does not bound effects of executing mutable input | A check imports, sources, executes or otherwise interprets candidate-written code |
| Four default tools | Compatibility behavior, not a universal security ceiling | A deliberately approved caller needs another tool |
| Current profile's state limits | Implementation facts, not proof that those limits are necessary | An admitted real task reaches a limit |

The owner may deliberately grant the named bounded tools. A model may not
expand its grant, add a bypass, alter configuration, or select another session.
No additional external policy ceiling is evidenced. The user prohibitions on
credential capture, live-agent control and production mutation also constrain
owner-approved actions.

## Permission behavior

Keep current session and tool-call identity checks. Reject malformed requests,
managed human-only approvals, sandbox bypass/permissive retries, sandbox path
grants and unknown permission kinds. Do not introduce permanent or session-wide
approval. A permitted decision remains `approve-once`.

For writes, use the paired SDK's `PermissionRequestWrite`: `fileName`, optional
`resolvedPath`, and every supplied before/after `fileEdits` path identify the
effect. Resolve against the candidate workspace and require the exact approved
file. Reject aliases, parent/leaf symlinks, directories and paths outside the
workspace. A new file requires an existing regular, unaliased parent directory.
This caller patches files; moves to another path are not supported.
Content previews are data, not grants.

For shell, use `PermissionRequestShell.fullCommandText`, not an invented
`command` field or parsed executable name alone. Require exact equality to an
approved literal command. Validate the SDK request's required fields and
declared optional fields. Reject redirection, policy overrides, bypass,
unapproved URL effects and a different resolved working directory.
Do not infer permission from the SDK's `readOnly` label.
The current setup supports only a fixed check that consumes mutable bytes as
data. The check must not execute, import, source, evaluate or deserialize code
from the mutable file, or select programs/dependencies from its content.
An immutable script alone does not establish this property.
The script is owner-staged, bound to the frozen case and outside the write
grant. The interpreter and standard library come from the existing workflow
runtime, not the candidate's files. Record the resolved interpreter/version;
do not copy or add a separate interpreter/dependency verification system.
Use Python isolated mode to avoid candidate-controlled module search.
Do not add a generic script-safety
detector: the reviewed fixed checker below supplies this narrow property.
Owner-approved checks that execute candidate-written code are not forbidden
in general, but require a separately reviewed execution/containment contract.
This fixture does not establish that capability.

Read and native state behavior retain the current owner boundary. State
tools operate only on the fixture's isolated native home/session. Coordinator
and original-session stores are not mounted or passed to the candidate.
Do not claim query-level mediation that this tool grant does not implement.

## Concrete journey and failure model

Use `target.txt`, initially the bytes `pending\n`, as the only writable file.
The only shell grant is `python3 -I check.py`. The owner stages this exact
non-executing `check.py` and verifies its frozen identity before and after use:

```python
from pathlib import Path

if Path(__file__).with_name("target.txt").read_bytes() != b"ready\n":
    print("invalid fixture data")
    raise SystemExit(1)
print("PASS fixture data")
```

The checker imports only the fixed standard library, reads bytes and compares
them with a literal. It never evaluates the file. A declared negative input
`print('EXECUTED-MUTABLE-FIXTURE')\n` must produce exit1 and only the invalid-data
message, not that execution marker. This is one check of the fixed fixture,
not an adversarial campaign or a general safety claim about arbitrary code.

The evaluator stages a synthetic imported-history fixture, one mutable file,
an immutable check script and its existing native state projection. It
validates literal grants, then resumes the same candidate through the SDK.
Native metadata must show the selected six tools. Before inference, the
existing helper observes instructions, state and prefix, and exercises real
permission decisions in the fixture.

The candidate loads the supplied unchanged skill, patches the approved file,
runs the fixed check, updates its native todo, and lists/stops/re-lists the
fixture's existing schedule. The evaluator observes the changed file and
native state independently, correlates the final root response and idle event,
and cleans up the fixture. The result is setup capability only.

Missing tools, an unexpected permission shape or denial of an approved action
stops before a model send where observable in preflight. A candidate error
after inference remains the first incomplete/negative setup outcome; it is
not evidence of a skill defect. Do not retry unchanged denial or substitute
CLI flags, a mocked tool result, a second coached send or wider grants.

Denied model calls can end a native turn. Therefore refusal checks belong to
owner preflight, not an intentionally failing call in the positive model task.
All owner calls remain recorded and cannot satisfy model-owned requirements.

## Check contract and acceptance

| ID | Property and setup | Expected success | Failure signal and meaning |
| --- | --- | --- | --- |
| A1 | Replay retained default read requests and current default configuration; omit permissions and also supply empty lists | Same four tools and prior approve/reject results; ordinary repository command unchanged | Changed default selection/decision or command is a compatibility regression |
| A2 | Submit invalid profiles, nonliteral paths/commands, unknown fields and permission-expansion flags through current validators; bind the exact data-only checker and isolated interpreter command | Rejection before SDK/model invocation; checker source matches the fixed fixture and interpreter comes from the existing runtime | Acceptance grants unsupported input; changed checker identity or an executing checker cannot qualify this fixture |
| A3 | Submit typed write/shell requests, including wrong session/call identity, sibling/alias/move path, wrong command, bypass and managed approval | Only exact supported effects receive approve-once; every forbidden effect remains absent | An accepted mismatch or forbidden mutation violates the authority boundary |
| A4 | Existing SDK preflight queries actual metadata and invokes approved patch/check plus refused sibling write/unapproved shell in a synthetic fixture, with no model sends; also test the declared executable-looking data input | Six real tools; correlated permission events/results; ready data passes; declared invalid data gives exactly exit1/invalid-data without execution marker; checker remains unchanged and isolated interpreter cannot import candidate files; forbidden effects absent; restore original mutable bytes; original prefix and state match before inference | Missing tool, denial, bypass, interpreted input, changed checker, unrestored fixture or changed prefix blocks inference, not the skill |
| A5 | One conditional synthetic candidate executes patch/check, SQL update and schedule stop under the same grants | Successful model-owned tool completions; changed file and check exit zero; todo done, schedule absent; matching final root response/non-aborted idle; goal/mode unchanged | Missing action/read-back, owner/model substitution or partial final response leaves combined capability unproved |
| A6 | Existing cold observer and cleanup inspect the same isolated fixture after candidate execution or error | Expected terminal file/native state; then no fixture reminders/todos; original namespaces unchanged; no native homes or credentials archived | Residual state or leakage leaves cleanup/containment incomplete |

Focused tests extend existing files. First capture the old input/decision
meanings on unchanged source, then replay those exact retained inputs after
editing. Add a few functional cases for new grants and their mismatches.
Use existing validation and live-proof receipts; do not create a replacement
proof framework. No executable pre-build guard is required.

A4 and A5 prove different boundaries. A4's trusted-owner operations prove
availability and mediation, not model execution. A5 cannot credit those owner
calls. Metadata alone cannot satisfy either effect check.
The negative data case is an intentional check outcome, not permission denial.
Accept only its declared exit and output; do not classify unrelated shell,
SDK or process failures as that expected result.

## Validation sequence and accounting

1. Complete current constraint reconciliation and paired design review.
2. Implement the smallest existing-owner change and focused diagnostics.
3. Freeze exact source, synthetic case, skill files, permissions, CLI/SDK,
   workflow and check identities. Register current-stage claims using the
   existing receipt validator.
4. Obtain both independent R1-R5 READY grades and present the complete frozen
   setup methodology before its paid phase. Do not call the fixture historical.
5. Use the existing private workflow for A4, with zero model sends. Only after
   A4 succeeds, permit one A5 candidate on the same inputs.
   Prefer the supported Haiku model with medium effort for this setup task;
   pin the exact identifier before dispatch. No paid behavioral judges or
   automatic retries are required for this mechanical capability question.
6. Retain every first outcome, then validate complete current-stage proof
   before implementation review, broad checks or owned source PR work.

Reuse existing CLI/SDK provisioning and artifact transport. Record preparation,
build, upload/download, runner, model, cleanup and review observations in the
existing report. Unknown prices and missing wall coverage remain unknown.
Do not upload a new image or duplicate input archive without a changed input
or named delivery need.

## Reframe gate

The gate is CLEAR because the CLI-owner premise was replaced by the existing
SDK owner and both design families accepted the narrowed fixed-check contract
after current challenge reconciliation. The proposed existing-owner route is
cleared for implementation, not established runtime capability. Actual typed
tool traversal, containment and prefix preservation remain A4 proof gates.

1. Blocked result: one candidate cannot combine editable work and native state.
2. Causing constraint: separate fixed CLI and SDK tool/permission configurations,
   an implementation choice, not an external policy.
3. Retained invariant: actual SDK mediation, isolated effects, unchanged defaults
   and an uncoached preserved prefix.
4. Simplest alternative: extend the existing SDK caller's literal grants and
   selected tool expectations; leave ordinary CLI work unchanged.
5. Fewer components: this keeps the existing runner/helper/state owner and adds
   no parallel execution or permission service.

Closure evidence is the current constraint reconciliation and both completed
finding-scoped design results on the exact contract identity above.
Reopen if an existing supported configuration supplies the caller unchanged,
required tools/mediation cannot be reached, preflight contaminates context,
an approved check would execute candidate-written content,
another subsystem is proposed, or a real task requires different state/profile,
controller, workspace or approval semantics. A new fixture does not erase that
real task's unresolved requirements.

## Migration and rollback

There is no state migration. Omit the new optional profile to select existing
read-only behavior. If default compatibility or preflight fails, remove the
extension or revert only this owned change; preserve input/result artifacts.
Do not change objectives, schedules, selected mode or other writers' work.

## Definition of Done: combined editable native capability

The exact candidate passes A1-A6, its proof receipts are accepted, both source
review families finish without an in-scope material defect, and proportional
source checks pass. Any owned source PR identifies these supported capabilities
and explicitly leaves historical admission, full repository/controller behavior,
skill qualification, merge, release and installation pending.
