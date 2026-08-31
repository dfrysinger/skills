# Windows SDK Workflow Reliability

## Objective

Make mailbox wakeups, unattended-run autopilot objective handoff, and
self-compact execute through the Copilot SDK reliably on standard Windows
hosts without Bash, WSL, terminal keystrokes, SSH, or Tailscale.

## User evidence

Evidence packet revision: `windows-sdk-reliability-r1`.

- User request, 2026-08-31: "hi can you see i fyou an get the sdk version of
  mailbox and /dfrysinger-skills:unattended-run autopilot objective setting,
  and /dfrysinger-skills:self-compact working reliably on this machine and
  windows in general?"
- The host has Node and PowerShell but no `bash`, `awk`, `nohup`, `mktemp`, or
  `seq` on `PATH`.
- Directly spawning `submit-compact.sh` with Node `execFile` on this host fails
  with `spawn EFTYPE`.
- The mailbox watcher and session-inbox extensions already run as Node
  processes and use SDK session APIs without a terminal transport.

The `grill-me` skill required by the design workflow is not present in plugin
0.108.22. The request already defines the end-user job, supported platform,
and prohibited transports, so there is no unresolved product decision to ask
the user before proposing the work.

## Lane

**Critical.** This replaces reusable orchestration at the boundary between
three skills, two extensions, durable request/receipt state, and native Copilot
SDK commands on multiple operating systems. Critical wins because the
self-compact port reimplements a fail-closed authorization and draft
non-interference boundary: an incorrect transition could consume unsubmitted
user input, duplicate a compact, or certify an uncorrelated checkpoint.

## Non-goals

- Do not change Copilot CLI, `@github/copilot-sdk`, native queue semantics, or
  session event schemas.
- Do not add SSH, Tailscale, WSL, Git Bash, terminal input injection, or a
  Windows-only service.
- Do not change mailbox envelope formats, OneDrive transport ownership, or
  deterministic `name@machine` identity.
- Do not move self-compact policy into generic session-inbox code.
- Do not weaken self-compact authorization, run exclusion, ambiguity handling,
  checkpoint proof, or exactly-once continuation checks.
- Do not require the SDK features to work when the installed Copilot CLI does
  not expose their native RPCs.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit condition |
| --- | --- | --- | --- |
| Node is the portable orchestration runtime. | Node is already required by the plugin, mailbox core, and session-inbox extension; standard Windows lacks the current POSIX toolchain. | One implementation and one receipt format across Windows and macOS. | Revisit if Copilot extensions gain a durable post-turn task API that removes helper processes. |
| Mailbox mutable state remains local and OneDrive remains immutable transport only. | Existing mailbox product contract and prior cloud-lock failures. | Delivery integrity and deterministic retry ownership. | Revisit only for a transactional remote transport. |
| Autopilot objectives are established by native `commands.invoke` and verified through native objective state. | Existing session-inbox SDK path and user requirement for SDK operation. | Prevents a success-shaped receipt when only a prompt was queued. | Revisit if the SDK adds an atomic set-objective API. |
| Self-compact remains a private structured tool with one detached verifier. | Existing structured-tool design and draft non-interference contract. | Current-turn authorization, crash survival, and one continuation. | Revisit if the SDK adds an atomic run-after-turn compaction primitive. |
| Detached helpers must survive the initiating extension/tool process. | The authorizing turn ends before compact can safely start; unattended handoff may outlive the caller. | Avoids deadlock and half-started operations. | Revisit if extension background tasks gain documented lifetime guarantees. |
| Windows paths and process liveness use platform APIs rather than shell syntax. | Direct `EFTYPE` failure and absent POSIX commands on this host. | Standard Windows support without hidden dependencies. | Revisit only if the plugin formally requires a POSIX compatibility layer. |

Hard numeric timeouts remain configurable and preserve their current maximums;
this change does not invent new capacity limits.

## Reframe gate

**Status: CLEAR.** The current failure is at the helper runtime boundary:
portable SDK logic is already in Node, while unattended-run and self-compact
reach it through POSIX-only launch and verification scripts. Porting that
orchestration to the already-required Node runtime removes dependencies rather
than adding a subsystem.

Return to design before implementation if:

- a supported guarantee requires undocumented Windows process behavior that a
  direct probe cannot observe;
- Node cannot reproduce the current event-bound authorization without
  weakening it;
- mailbox delivery requires a second state owner or remote mutable lock; or
- a fix starts embedding workflow policy in session-inbox.

The current plugin contains `constraint-challenge`, although this long-lived
session began before that skill was registered. The required challenge is
therefore executed by a fresh read-only agent using the installed skill
contract and persisted beside the unattended charter.

## Design review

Round 1 identified two acceptance-level defects: the lane understated the
fail-closed authorization boundary, and verifier death after handoff but before
publication could permanently wedge a session. Revision `working-r3` corrected
both by classifying the work Critical and introducing the durable `publishing`
boundary with evidence-based recovery only before it.

The event-triggered constraint recheck returned `CONTINUE` / `CLEAR`. Focused
round-2 reviews by Claude Opus 5 and GPT-5.6 Terra both applied the architecture
and scope lens, marked both prior findings resolved, and reported no remaining
findings. The design gate is closed for implementation.

## Reuse contract and architecture

### Generic SDK transport

`extensions/session-inbox/request.mjs` remains the durable request publisher
and `extensions/session-inbox/extension.mjs` remains the only owner of SDK
send, native autopilot command invocation, compaction, and continuation
delivery. No workflow-specific branch is added there unless a live probe proves
an existing cross-platform defect.

### Mailbox

`mailbox-core.mjs` and `mailbox-watcher/extension.mjs` already provide the
portable implementation. Work here is proof-first: exercise a real Windows
named session, inspect the durable session-inbox receipt, and change code only
for a reproduced defect.

### Unattended-run

Add `enqueue-autopilot.mjs` as the portable owner of objective validation,
temporary private files, request execution, receipt persistence, and result
classification. Keep `enqueue-autopilot.sh` as a thin compatibility wrapper
that executes Node. Windows callers invoke the `.mjs` file directly with a
detached Node process.

The generic session-inbox completed or failed receipt remains authoritative.
The unattended-run audit receipt is only an indexed view and records:

- objective SHA-256 digest;
- request ID;
- target session ID and resolved target generation;
- authoritative completed or failed receipt path;
- exact objective bytes expected;
- native objective ID and `active|completed` status;
- activation delivery, which must be `idle` or `steering`; and
- the helper outcome and timestamp.

Retry uses the existing objective-derived dedupe key. Before publishing a new
attempt, the helper reconciles any authoritative receipt for the same request
identity. It never treats its timestamp/PID filename as operation identity.

### Self-compact

Replace the extension's direct `.sh` spawn with `submit-compact.mjs`. Port the
foreground authorization, session lock, detached verifier, request execution,
event parsing, checkpoint proof, and continuation proof into Node. Keep the
existing shell entry points as compatibility wrappers during migration so
current macOS callers and tests fail visibly rather than silently changing
semantics.

The Node submitter launches the verifier with the same executable and a
private internal mode. It uses `detached: true`, ignored standard streams to a
run log, and `unref()`. Lock files retain token and state ownership. Process
liveness uses `process.kill(pid, 0)` and filesystem errors are handled
explicitly.

#### Self-compact handoff state machine

The portable implementation preserves the current trusted transfer protocol:

1. `foreground`: bind exactly one running root `self_compact` tool call by
   `toolCallId`; create a unique eight-hex run token and owner lock with
   `submitter.pid`, token, and state through create-exclusive writes.
2. `verifier-starting`: write the exact brief plus run token, fixed
   continuation, candidate metadata, and run log paths with user-only
   permissions; spawn the detached verifier with inherited operation metadata.
3. `verifier-owned`: the verifier validates the lock token, writes
   `watcher.pid`, atomically changes the lock state, opens its log, then creates
   a readiness artifact containing the same lock token. Only after reading
   that exact readiness token does the foreground write the two-line atomic
   handoff containing lock token and `toolCallId` and return its receipt.
4. `authorized`: the verifier observes exactly one matching tool completion,
   no conflicting root activity, and the end of the authorizing turn.
5. `publishing`: atomically persist the event byte offset, target session ID,
   target generation, tool call ID, run token, lock token, deterministic dedupe
   key, and expected request receipt directory before spawning the request
   publisher. Entering this state means a side effect may occur and the lock is
   no longer automatically reclaimable.
6. `request-published`: after the publisher returns a request ID, atomically
   persist that ID and its pending/processing/completed/failed receipt paths.
7. `compact-observed`: require one successful completion whose
   `customInstructions` exactly equal the brief plus this run token and whose
   checkpoint number exceeds the baseline.
8. `checkpoint-observed`: require `workspace.yaml` to reach that checkpoint
   and exactly one numbered checkpoint file.
9. `continuation-observed`: require exactly one matching root user message
   after the completion boundary with `idle` or `steering` delivery.
10. `completed`: write terminal state and release only this run's artifacts and
   lock.

A definitive failure before the `publishing` transition removes the current
run's artifacts and lock. Any timeout, crash, unknown request outcome,
matching compact without proven continuation, or other ambiguity after
`publishing` retains the lock and run metadata.

Automatic stale recovery is allowed only when all relevant process owners are
dead and the durable state proves no publication attempt began:

- a `foreground` lock with no watcher PID or handoff may be reclaimed when its
  submitter PID is dead; or
- a `verifier-starting`, `verifier-owned`, or `authorized` lock may be
  reclaimed when both recorded PIDs are dead, its readiness/handoff artifacts
  are internally consistent, and no `publishing` state or request metadata was
  ever persisted.

`publishing` and every later state are never automatically reclaimed. This
conservative boundary treats a crash after the durable publication-attempt
marker as ambiguous even if no pending request is later found.

Detached process creation is not accepted as ownership transfer. Tests require
the token-matched readiness and handoff sequence, then kill the foreground
process and prove the verifier continues from durable state.

### Correlation tuples

Every operation has one explicit correlation tuple:

- Mailbox: envelope ID, notification-attempt dedupe key, target session ID,
  target generation, session-inbox request ID, authoritative request receipt
  path, and envelope acknowledgement state.
- Autopilot: objective digest, target session ID, target generation, request
  ID, authoritative request receipt path, native objective ID/status, and
  accepted activation delivery.
- Self-compact: tool call ID, run token, lock token, target session ID, target
  generation, compact request ID and receipt path, exact custom instructions,
  baseline/completed checkpoint numbers, completion event boundary, and
  continuation message ID/delivery.

Wrapper or audit receipts reference these tuples. They never become a second
authority for delivery or native state.

## Failure model

- Missing Node or request CLI fails before request publication.
- Unsupported or malformed objective/brief fails before creating a durable
  SDK request.
- Failure before request publication removes foreground artifacts and lock.
- Ambiguity after request publication retains the self-compact lock.
- A process crash after handoff leaves a run log and durable request receipt.
- An SDK return without matching native objective state, compaction event,
  checkpoint, or immediate continuation is not success.
- Duplicate, queued, or conflicting delivery remains a failure.
- A mailbox wakeup receipt that does not prove `idle` or `steering` leaves the
  envelope pending and unacknowledged.

## Hard invariants

1. No Windows acceptance path depends on Bash, WSL, terminal keystrokes, SSH,
   or Tailscale.
2. Mailbox wakeup is one SDK user turn with one durable receipt; the envelope
   remains pending until recipient acknowledgement.
3. Autopilot success requires exact objective text in native objective state
   and `idle` or `steering` activation.
4. Self-compact is authorized by exactly one current root tool call and starts
   only after that tool call and turn finish.
5. Self-compact success requires one matching token-bound completion, a higher
   checkpoint number, exactly one checkpoint file, and exactly one immediate
   continuation.
6. Definitive failure before the durable `publishing` transition releases or
   permits safe stale recovery of the lock; `publishing` or any later
   ambiguity retains it.
7. Workflow policy remains in its owning skill/extension, not in the generic
   session-inbox transport.

## Acceptance criteria and check contract

| Criterion | Check | Failure signal |
| --- | --- | --- |
| Portable autopilot helper | Node tests cover validation, exact objective bytes, request arguments, confirmed receipt, failure receipt, and Windows-style paths. | Any invalid input publishes a request, or a non-confirming SDK result returns success. |
| Native autopilot on Windows | A live exact-session request sets a disposable objective and the receipt proves native objective state plus `idle`/`steering`. | Missing/mismatched objective, queued activation, timeout, or success without native state. |
| Portable self-compact orchestration | Node tests cover tool binding, every named lock-state transition, token-matched readiness and handoff, foreground death after handoff, verifier startup failure, verifier death after handoff but before `publishing`, safe reclaim of that pre-attempt state, crash at/after `publishing` with retained lock, request classification, replay/duplicate request, stale/manual-equivalent completion events, token matching, checkpoint proof, continuation count, and Windows paths. | A malformed/current-conflicting invocation starts compact, detached creation is mistaken for ownership, a pre-attempt dead verifier permanently wedges the session, or incomplete proof returns success. |
| Native self-compact on Windows | The private tool produces one token-bound compact, advances `summary_count`, creates one numbered checkpoint, and sends one immediate continuation. | Missing/duplicate compaction or continuation, stale checkpoint, retained unknown outcome reported as success, or draft/other activity consumed. |
| SDK mailbox on Windows | A real local envelope to a live deterministic Windows agent imports once, proves `terminalPokeCli` is absent, yields one completed session-inbox send receipt with `idle|steering`, and remains pending until explicit ack. | Terminal injection or fallback selection, duplicate user turns, remote mutation, missing receipt, or premature ack. |
| Publication during rotation | A deterministic fixture pauses between barrier check and publish, establishes the rotation barrier, and requires publication to fail or serialize without a pending request crossing the barrier. | A request becomes pending after rotation starts without participating in one exclusion protocol. |
| Cross-platform compatibility | Existing mailbox/session-inbox tests and shell compatibility tests pass; wrapper parity tests prove each shell wrapper only locates Node and forwards all arguments/exit status. | macOS behavior changes, wrapper-owned workflow logic remains, or shell and Node behavior diverge. |

The native autopilot live proof predicate is exact: the authoritative receipt
must record the requested objective text/digest, `objectiveSet: true`, native
objective ID, native status `active|completed`, target generation, and
activation delivery `idle|steering`. Any queued, absent, mismatched, or
unreadable state is failure or ambiguity, never success.

The non-macOS rotation publication branch is tested as a generic
session-inbox property. If the deterministic race fixture reproduces a request
crossing the barrier, fix it in session-inbox with one cross-platform
exclusion owner; do not compensate in unattended-run or self-compact.

## Migration and rollback

Ship the Node entry points in one plugin release. The self-compact extension
switches atomically to the Node submitter; shell wrappers delegate to the same
Node implementation. Roll back by reverting the release and reloading
extensions. Existing envelopes, requests, receipts, checkpoints, and lock
formats remain compatible. A lock from an ambiguous run is never removed by
rollback without inspecting its run log and receipt.

The boundary fails closed when deterministic tests and live proof show:

- malformed briefs, duplicate tool requests, conflicting root activity, and
  stale tool calls create no pending compact request, no compaction event, no
  checkpoint advance, and no terminal-input mutation;
- verifier death before `publishing` is recoverable only under the explicit
  dead-owner/no-attempt predicates above;
- verifier death at or after `publishing` retains the lock and cannot cause an
  automatic retry;
- only the exact token-bound successful completion can authorize checkpoint
  and continuation success; and
- draft or unrelated root activity cancels before publication rather than
  being consumed.

## Definition of Done: Windows SDK Workflow Reliability

- The design is reviewed by both required model families with no material open
  finding.
- Standard Windows runs mailbox wakeup, autopilot objective handoff, and
  self-compact without a POSIX compatibility layer or terminal input.
- All deterministic tests and existing related suites pass on the final tree.
- Three current live-proof receipts validate `PASS` for mailbox, autopilot,
  and self-compact against the same final candidate.
- The reviewed change is merged to `dfrysinger/skills`, the supported plugin
  update is installed, extensions are reloaded, and one post-install Windows
  canary passes for each boundary.
