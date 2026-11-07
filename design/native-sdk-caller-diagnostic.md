# Fixed native SDK caller diagnostic

Status: DESIGN_ACCEPTED; implement the accepted check contract and verify
frozen inputs before the conditional paid diagnostic.
Lane: critical, because the caller changes its permission mediation.
Reframe status: CLOSED. The former synthetic task required an intentionally rejected
read in the same query as permitted recovery. Actual rejection was followed
by idle before the required final response and recovery completed. The
corrected contract separates that negative control from the model's permitted
task. It does not change the permission boundary or completion requirements.

## Objective and non-goals

Use the existing public SDK model-send path to exercise the fixed synthetic
native scheduling journey on the existing private Actions evaluator.

No generic runner, new service, custom tool implementation, replacement state,
production native profile, historical baseline, skill treatment, CLI upgrade,
merge, product release or installation is in scope. Ordinary prose and
repository evaluators must remain unchanged. Do not repeat either direct CLI
configuration or add more flags to it.

## Authority and constraints

The user's objective requires:
> Use the existing private Actions evaluator. No new runner, service, dashboard,
> permission bypass, credential capture, live-agent manipulation or production
> mutation.

The user's outcome is reproduced recovery behavior, not preservation of a
particular command-line caller. The current private workflow, pinned version97
runtime and synthetic fixture are comparison controls, not permanent platform
requirements.

| Constraint | Source and protected result | Revisit condition |
| --- | --- | --- |
| Existing Actions evaluator | Direct user instruction; no second execution system | Explicit user change |
| Real native state and tools | User requires executed recovery, not promises | An actual native API cannot carry the operation |
| Bounded normal grants | User requires normal permissions; the model cannot expand its own authority | A required operation lacks a mediated path |
| One owned namespace and active client | Existing helper owns isolated fixture state | A second conflicting writer is evidenced |
| Fixed fixture, plugin, model and checks | Diagnostic comparison and first-outcome retention | A declared input must change to answer another question |
| One candidate, 300 seconds, no judges or retries | Coordinator's bounded infrastructure check, not a reliability threshold | This diagnostic ends; another question needs its own scope |

Deliberate owner grants are allowed. No separate external policy mandates CLI-p
or this runtime version. The permission boundary governs model-selected
requests, not trusted setup's approved creation and cleanup of its own fixture.
There is one active native owner and no concurrency mechanism.

## Existing parts and exact changes

`skill_eval.py:_run_native_workflow_diagnostic` already verifies and imports
the fixture, stages ordinary plan and personal instructions, pins the plugin,
prepares actual native state, invokes a candidate, observes cold state, retains
first errors and cleans up.

`native_workflow_probe.mjs` already owns the paired public SDK client,
version97 standalone connection, cold resume, native goal/mode/SQL/schedule
APIs and shutdown. Extend this fixed diagnostic helper with a candidate
operation. Do not add another generic receiver or intercept native responses.
The internal Python driver selects it instead of `run_copilot` only for this
fixed synthetic diagnostic. All other callers keep their command.

The SDK candidate operation resumes the imported UUID with fixed model
`gpt-5.6-sol-fast`, high reasoning, the same plugin and custom instructions,
four intended native tools, and `manageScheduleEnabled: true`. Disable
built-in MCPs. Continue-pending-work, resume-event and transcript-recovery
settings remain explicitly off. Register no custom tools, MCPs or callbacks
that return fabricated tool results.

Use client `mode: "copilot-cli"` and resume with
`skipCustomInstructions: false`, `instructionDirectories: []` and
`organizationCustomInstructions: ""`. The explicit directories list clears
only extra SDK discovery roots; the existing isolated home supplies the staged
personal file. A new cold runtime has no old instruction cache.
`refreshCustomInstructions` is a creation-only option and is not supplied on
resume. Do not replace or append a system message to simulate discovered files.

Forward the existing evaluator `COPILOT_GITHUB_TOKEN` only through the
documented candidate SDK `gitHubToken` option. Keep `useLoggedInUser: false`.
Do not copy the token into configuration files, receipts, arguments or logs.
Non-model setup, observation and cleanup need no authentication change.

Keep the fixed caller free of the experimental opt-in. Preserve prior
source/packages/outcomes when any diagnostic input changes.

## One concrete journey

The existing Actions job imports the frozen synthetic prior conversation.
The setup helper creates goal17/completed, autopilot mode, the pending native
row and the owned four-hour schedule. It verifies the state after cold resume
and closes. The SDK candidate owner then resumes the same UUID.

Before sending the prompt, that owner records actual effective native tool
metadata, loaded instruction sources and the cold goal, mode, row and schedule.
Read `session.rpc.instructions.getSources()` on this actual resumed owner.
Its sources must contain the staged personal file exactly once, with identical
raw-content SHA256 and no extra or disabled source. Retain source paths, merge
order and content hashes. A separate CLI `instruction list` remains preparation
evidence only. Missing, mismatched or unobservable SDK instruction sources stop
before the model. The public session-scoped API and raw-content contract are
defined at `generated/rpc.d.ts:33162-33175,13337-13380`.
Required tool descriptors
must be present, with no extra names or MCP namespace. Requested configuration
alone does not pass.

Use the existing public `session.rpc.tools.execute` API with explicit
`toolCallId` values for owner-only plan, exact-goal and sibling read checks.
This API accepts the currently offered tool name and arguments
(`generated/rpc.d.ts:27867-27880`). The exact-goal read must reach the registered
path-bearing permission callback and receive `approve-once`. The sibling
must reach it and receive `reject`, with a documented `denied` or `rejected`
native result. Correlate
request, decision and execution by UUID and tool-call ID. A successful read
through an owner bypass is not this proof.

Capture native events before and after these checks. They must not introduce
user, assistant or tool-result conversation content into the imported prefix.
Keep permission and owner inspection receipts outside candidate-visible files.
If this route cannot traverse permission handling or keep the prefix intact,
stop before the model. Do not erase history or quietly use another API.

Only after those checks pass, send the frozen rendered prompt once through
public `session.send`. Install the completion listener before sending. Buffer
actual events that arrive before the send returns its message ID; do not lose
a fast response. Match root assistant messages by `originatingMessageId` to
that returned ID. A matching final response must precede a real, non-aborted
`session.idle` from the same resumed owner. `assistant.idle` alone does not
complete the session. Ignore child-agent events for completion matching, not
by deleting them from retained evidence.

This replaces only the convenience wait: the paired SDK `sendAndWait`
resolves `session.idle` only when its mode is not autopilot
(`index.js:10469-10504`). The native fixture requires autopilot mode. Do not
change that mode, patch the SDK, manufacture completion, or lengthen the
model deadline to accommodate this filter. The public send/message-ID contract
is at `session.d.ts:133-145`; native idle and aborted state are at
`generated/session-events.d.ts:1985-2021`.

Capture actual SDK events directly as newline-delimited JSON, preserving IDs
and contents. Retain the returned message ID, matching actual assistant event
and terminal idle event in the receipt. The diagnostic-only parser must bind
the completed receipt to those same actual events and model identity, while
ordinary CLI parsing still requires its real successful CLI result.
No fake CLI result record may be emitted.

An actual root session error, send/transport failure, aborted idle or the
300-second send/completion deadline fails the attempt. Abort and close using
the existing owner, retain the first error and every event, and continue only
the existing cold observation and fixture cleanup.

That deadline caps model work, not preparation and shutdown. The outer helper
watchdog is 360 seconds. At dispatch, the model window is the smaller of
300 seconds and the time remaining before the owner reaches 330 seconds,
reserving 30 seconds for abort and close. Exhausted owner time blocks before
send. Retain the actual window; prolonged preflight can reduce it. Actual
shutdown within the reserve remains a runtime acceptance condition.

The candidate must recall the prior-only marker, successfully load the skill,
read the ordinary plan and exact goal, update the native row and
list/stop/re-list the schedule. The prompt names the excluded sibling path
but must not require the model to attempt its read. The native preflight
already exercises rejection through this same owner and handler. A deliberate
negative control is not another permitted recovery operation.

Close the candidate and use the existing helper to verify the native row,
goal, mode and schedule after cold resume. Then clean only this fixture and
verify empty lists and all clients closed.

The fixed diagnostic parser must require successful target-skill completion,
not just invocation or a matching answer. Keep owner preflight denial
separate from model-owned tool counts. Require the actual preflight reject
receipt, successful permitted model actions and no successful outside read.
An unexpected model-side denial remains visible in raw evidence; it cannot
replace a required permitted action.

Publish corrected synthetic prompt and criteria bytes as a new frozen case
revision through the existing evaluator. Keep the previous revision and
outcomes intact. This changes the diagnostic fixture, not a historical
trigger or skill treatment, and is not an unchanged-case comparison.

## Permission handler

The complete handler contract is part of this work order:

- Bind one owner-created callback to the imported UUID, regular workdir,
  exact owned goal and pinned plugin. Reject another UUID.
- Reject managed-approval-required requests, sandbox bypasses and unknown
  permission kinds. Never change managed policy or sandbox rules.
- For `kind: "read"`, resolve the request path against the fixed workdir.
  Require an existing unaliased canonical target and check any native
  `resolvedPath` against the same identity. Return `approve-once` only for
  the exact owned goal or evidence-tree target. Reject the sibling, plugin
  tree and all other targets.
- For `kind: "custom-tool"`, return `approve-once` only for the intended
  native names `skill`, `sql`, `manage_schedule`. Register no custom tools
  or MCPs. Never approve `view` through a path-free custom-tool request.
- Return `reject` for every other request. Never use `approveAll`,
  session-wide or permanent grants, assisted approval or interactive flags.
- Record native requests and once-only decisions by UUID and tool-call ID.
  Preserve handler errors as denial, not success.

The paired SDK source defines read requests at
`generated/session-events.d.ts:9436-9478`, custom-tool requests at9719-9744,
the UUID-bearing callback at `types.d.ts:1039-1042`, and single-request decisions
at `generated/rpc.d.ts:18304-18312,18763-18771`. Native callback delivery and
error-to-denial behavior are at `index.js:14015,14110,10908-10947`.

The source contract provides native callback delivery and once-only decisions;
actual runtime mediation remains unproved until the checks above pass.

## Checks, failure and rollback

Focused tests cover accepted owned reads, rejected sibling/alias/wrong-UUID/
unknown/managed-required/bypass requests, callback errors, no-model exit on
missing metadata or mediation, missing/mismatched/duplicate/disabled instruction
sources, event-prefix preservation and unchanged normal commands. They must
fail if the corresponding boundary is removed.
Completion tests cover events arriving before send returns, wrong or missing
message correlation, child events, assistant-only idle, aborted idle, root
errors and deadline closure. Only a matching root response followed by actual
session idle passes. Native runtime correspondence still requires Actions.

Actual Actions acceptance requires every retained caller checkpoint: imported
context, successful skill load, native goal/mode, row update, scheduling,
actual SDK instruction correspondence, native preflight sibling rejection,
no successful outside reads, first-error retention, no extra tools and
verified cleanup. Owner calls cannot satisfy model-owned action checks.
Focused checker tests must reject a missing successful skill load, missing
preflight rejection, missing model-owned SQL/schedule action or successful
outside read. A denied model-side request is not required for success.
Observe model settings and owned invocation usage, plus available preparation
and runner accounting; keep unknown costs unknown. Exclude both native homes
from retained archives.

On timeout, abort the SDK candidate, close it, observe and clean through the
existing owner. Keep the first error even if cleanup also fails. Rollback is
to leave this experimental path unused; ordinary routes remain unchanged.
No original or live namespace is touched.

## Reframe gate and Definition of Done: SDK native caller correspondence

The blocked outcome is completed permitted native recovery in one SDK query.
The conflicting intentional-rejection requirement came from the synthetic
fixture, not independent user authority. Its removal changes no grant: the
same handler still rejects that path, and the same owner proves rejection
before the send. All model-owned permitted operations and final/cold-state
checks remain. One existing public send and native-event listener use the
same client; no component, second prompt or wider permission is introduced.

The review packet must include the observed sequence, the independent minimum
design and the exact correction's scope verdict. One sequence does not prove
that every rejected read always interrupts a query. Removing an unsupported
requirement does not depend on proving that causal generalization. Both
independent method reviewers must accept the corrected full work order before
this reframe gate can close. Actual final-message, idle and recovery effects
remain runtime conditions.

Implementation remains stopped while reframe status is OPEN. Scope closure
must address the full work order and the permission-traversing preflight route,
not only the typed callback. Both independent design reviewers must accept it.

Then implement the accepted checker correction and run its focused checks.
Freeze source, complete inputs and runtime identities, present the method,
and run one cheap Actions diagnostic. Done means the effective metadata,
normal permissions and all original caller checkpoints are observed, retention
is verified and the same implementation passes its applicable review gate.
No historical or skill qualification follows from this synthetic result.
Each attempt uses one complete current candidate fingerprint and one
conditional candidate. It reruns all five premodel gates before its send and
verifies its own cold terminal state, cleanup and archive exclusions; old
per-attempt state is never pooled.

If effective tooling, loaded instructions, permission mediation or history
preservation cannot be proved, record the exact boundary without a model call.
If the candidate does
not perform scheduling, retain the negative result and return to scope before
another change. Do not relax required permitted-action, final-response,
permission or cold-state checks to preserve this receiver. Do not add a
coached follow-up or accept tool-bearing partial output as completion.
