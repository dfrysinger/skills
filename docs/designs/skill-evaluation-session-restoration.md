# Restore historical sessions in skill evaluations

Status: reviewed work order.

## Objective and lane

Continue a frozen historical task with its prior conversation and required
working state, so the evaluator measures new agent actions instead of a proposed
response to a transcript summary.

Lane: critical, because the optional case field changes a frozen contract and
the executable branch narrows candidate permission configuration.
The existing evaluator, case manifests, candidate process, result accounting and
Actions hosting remain the owners of their respective operations.

The trusted operator selects source evidence, the cutoff and permitted fixture
operations. The candidate must not choose a later cutoff, see hidden evidence,
rewrite the frozen inputs or expand those permissions.

## Non-goals

- No second evaluator, session service, approval broker or new scheduler.
- No automatic recovery of unavailable historical external services or accounts.
- No reconstruction that quietly changes the original task or inserts the fix.
- No claim that refreshing skill discovery erases instructions already in history.
- No full-corpus campaign, skill optimization, merge or installed-plugin rollout.
- No promise of identical model inputs across different CLI or model versions.

## Existing capabilities

The prose runner already resumes the same native session between phases.
Repository tasks already restore source, run an agent and independently grade
its captured changes. Frozen evidence and hidden judge packets already have
separate manifests and staging boundaries.

The native `sessions import` command accepts semantic JSONL and produces a
resumable native session. An isolated probe preserved user and assistant roles,
tool requests and completed results without running historical tools.
It regenerates native identifiers and timestamps; original provenance must
remain in the frozen source records.

Native skill reload refreshed a fixture's catalog while retaining its old skill
text in conversation history. It is not a treatment-isolation mechanism.
Native fork also supports a history cutoff and copies a plan file, but that
does not prove its copied files reflect the earlier cutoff. Do not depend on
fork for the initial execution path.

## Case contract and data flow

Add an optional `session_restore` object to the first candidate phase:

```json
{
  "history_file": "history.jsonl",
  "source_session_id": "original-session-identifier",
  "cutoff_event_id": "first-excluded-source-event",
  "skill_context": "before-target-load",
  "limitations": [
    "List any missing instructions, tools, services or path adaptations."
  ]
}
```

`history_file` names a regular file beneath that phase's existing evidence
directory, not a second archive. Existing freezing includes it in the phase
manifest, but it is an evaluator-only member: candidate staging must skip it.
Import reads the frozen source outside the candidate workspace. Do not copy the
transcript into the workspace or advertise its source path to the candidate.
Validate containment and required fields during freeze and verification. Only
the initial phase can import; later phases use the existing resume behavior.

The source capture identifies the original trigger request and first wrong
decision. The history ends before that trigger request; the candidate prompt is
the exact original request. The original wrong response, correction and later
recovery stay in the judge packet. No evaluation announcement, forced skill
invocation or proposed next action is prepended for this mode.

The restored workspace is the existing frozen phase packet or repository
snapshot. A case must account for every relevant instruction and working-state
dependency at the same cutoff. Missing state is an explicit limitation, not
proof that a conversation import is a complete restoration. Do not dispatch a
case whose missing state prevents its required actions or observable criteria.

Use `before-target-load` for clean skill comparisons: capture before
the target skill's first activation and let the candidate use the pinned skill
normally. Reject recorded target-skill invocations or target skill-context
messages in that prefix. Authoring still audits other ways its text could have
been exposed. Do not silently strip or replace instructions from old history.
An earlier cutoff may require replaying more of the task; do not force the old
future tool responses after the candidate takes a different action.

For historical behavior validation, the operator may explicitly select
`recorded-target-context`. Preserve old invocations and delivered target text
unchanged. All other validation and execution boundaries remain the same.
The restoration receipt records the selected policy. Both host and repository
reports must state that this is historical behavior/mechanism validation, not
isolated skill-change or current-skill-improvement evidence.
Record historical body hashes and differences from the current pinned catalog
in case provenance and limitations; existing skill/plugin identity artifacts
identify the available catalog. Do not imply those are the old loaded bytes.
Source qualification still establishes the actual message order and required
state. The policy does not itself establish fidelity. Disclose image, path,
tool, instruction and runtime adaptations; do not call an adapted case exact.

In an isolated candidate home, invoke native import with the actual staged
working directory. Validate its structured result and returned session ID.
Retain the import output, history digest, CLI identity and provenance in a
restoration receipt. Resume that ID through the existing candidate launch seam.
Unsupported import, invalid input or incomplete restoration fails before model
execution; no transcript-as-a-file fallback is permitted.

Use one shared Python restoration helper for native command construction,
structured-result checking and receipt content. Host subprocesses and the
existing container executor carry that same command; do not create another
model client or require an SDK dependency in the shipped evaluator.

## Executable repository tasks and permissions

Repository restoration adds an import-before-resume branch in the existing
container, not another runtime kind. Bind import and continuation to the same
isolated container home. Do not prepend the ordinary forced-skill prompt.
Keep existing patch capture, offline grading and independent behavioral judging.

The current repository command's blanket tool/path approvals cannot be used for
this proof. A restored repository case must declare its permitted operations
through `repository_task.candidate_permissions`, containing only `write_paths`
and `shell_commands` string arrays: exact writable repository-relative files
and literal shell commands required by the task. Compile those into native
`write(absolute-path)` and `shell(command)` rules, retaining normal path, URL and
denial checks. No unqualified shell/write grant, wildcard command, redirection,
permission-changing flag or all-paths grant is allowed.

The operator approves fixture operations; the model cannot edit that frozen
profile. This narrows the existing command rather than bypassing an approval
failure. If the task needs an operation outside the declared profile, preserve
the outcome and diagnose the route; do not widen it merely to obtain a pass.
Use normal native read and skill loading controls. Unrestored cases retain
their existing behavior; do not dispatch the old blanket-approval path here.

## Constraints and revisit conditions

| Constraint | Source and protected outcome | Revisit when |
| --- | --- | --- |
| Prior roles and observations remain history | User's historical-continuation goal; prevents coaching by a summary | Native interchange cannot represent a required record |
| Working state matches the conversation cutoff | User's executed-behavior goal; prevents impossible or misleading tasks | A selected case lacks necessary state or relies on a live dependency |
| Later correction is hidden | Existing case contract and blind-testing goal | The staged candidate can read later source or grader bytes |
| Old target instructions do not contaminate clean-comparison arms | Reload probe and treatment identity | A prefix includes target guidance or an earlier cutoff changes the task |
| Normal permissions remain enforced | Existing execution boundary; candidate receives only operator-approved operations | A required action cannot use native scoped permissions |
| Existing pipeline owns execution | Supported evaluator and Actions workflow | A measured required operation cannot pass through its existing seam |

Reframe status: CLEAR for the proposed architecture, based on the completed
two-pass independent constraint challenge. Design review remains a separate
implementation gate. Return to this decision before adding an API,
runner, dependency, grant or state-reconstruction mechanism to accommodate a
failed assumption. Removing an unsupported implementation preference must not
remove the user's required behavior.

## Check contract

| Check | Setup and signal | What a failure proves |
| --- | --- | --- |
| Frozen restoration inputs | Valid first-phase history; missing, escaping or later-phase history rejected; tampering changes verification | Restoration is not bound to the selected case |
| Candidate staging | Native import can read frozen history; candidate workspace contains ordinary phase files but no history file | The replay introduced an extra conversation file |
| Skill-context boundary | Target exposure rejected in before-target-load; retained unchanged in explicit recorded-target-context; invalid policies rejected | A comparison could retain old instructions or a historical run could silently replace them |
| Claim boundary | Both report paths label recorded-context behavior as non-comparative and identify current catalog separately from old text | A historical pass could be mistaken for an isolated skill improvement |
| Import and resume | Native structured success yields the resumed ID; unsupported, malformed and failed results do not launch a candidate | A failed import could masquerade as restored execution |
| Scoped permissions | Exact permitted file/command works; outside-file, other-command and URL requests remain denied | Restoration broadened the declared authority |
| Real continuation | New actions inspect or change the restored fixture; old tool calls are not re-executed | The test only described or replayed work |
| Original request and hidden future | Rendered prompt equals original request; staged packet excludes correction and grading evidence | The candidate was coached or could see the answer |
| One historical incident | Frozen original capture, cutoff, working state and actual trajectory with declared fidelity limits | Synthetic route proof was mistaken for a historical task result |
| Compatibility | Existing targeted prose, phase-resume and repository tests retain their meanings | Optional restoration changed old cases |

Use focused behavioral tests in the existing evaluator test modules. Use tiny
native fixtures for mechanism diagnosis. Native import/resume and scoped
permission checks must pass without a model call before the first paid
candidate/judge attempt. Preparation may be local; real attempts use the
existing private Actions pipeline and retain first results, model/CLI identities
and accounting. No additional generic guard framework is required.

## Migration and rollback

The field is optional. Old frozen cases and receipts keep their identities.
New cases require a CLI that actually supports native import; test the command,
not a guessed version threshold. Unsupported environments fail before a model
call. Removing restoration from an authoring case creates a new frozen revision,
not a rewrite of historical results.

If a restoration regression appears, stop new affected dispatches and retain
their receipts. Ordinary cases can continue through their existing path. Revert
the optional feature in source without deleting imported-session evidence.
An invalid permission profile must stop before candidate execution. Negative
native checks must show that another file, another command and an unapproved URL
do not gain access; an emitted rule alone does not establish that boundary.

## Definition of Done: restored-session task support

The optional contract, native import/resume seam and scoped executable path pass
their focused tests and current runtime proof. One real historical case retains
its original trigger, required state, actual new actions, honest fidelity limits
and immutable outcome. Required design and implementation reviews have no
material unresolved findings. Reviewed source and proof are persistent.
