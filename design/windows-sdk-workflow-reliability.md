# Windows SDK Workflow Reliability

## Objective

Make mailbox wakeups, unattended-run autopilot objective handoff, and
self-compact execute through the Copilot SDK reliably on standard Windows
hosts without Bash, WSL, terminal keystrokes, SSH, or Tailscale.

## User evidence

Evidence packet revision: `windows-sdk-reliability-r3`.

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
- On candidate `921a220`, native compaction completed successfully and advanced
  `summary_count` from 0 to 1, but the extension released the continuation
  after a fixed one-second delay. The SDK admitted that continuation to FIFO,
  reported that no live main turn existed for steering, and the fail-closed
  recovery removed it before natural idle delivery. The
  authoritative receipt is
  `completed\20260831T081603562Z-38648-260d0323.json`.
- A disposable Windows SDK trace then issued `session.send({mode:
  "immediate"})` directly from the matching successful
  `session.compaction_complete` handler. The send briefly changed the pending
  queue, returned one message ID, and emitted one matching `user.message` with
  delivery `idle` 867 milliseconds later. No post-compact `session.idle` event
  preceded the delivery; `session.idle` arrived only after that continuation
  turn finished. The trace is
  `files\windows-sdk-idle-probe\lifecycle.jsonl`.

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
| A compact continuation is sent after the matching successful `session.compaction_complete`; if its exact newly queued item cannot be promoted because `queue.sendNow` reports no live main turn, session-inbox waits for that message's natural `idle` delivery before considering removal. | Candidate `921a220` proved that immediate removal loses a valid continuation. The disposable Windows trace proved the same post-compact immediate send naturally delivered as `idle` after transient pending-queue activity. SDK 1.0.81 documents `sendNow.steered: false` as "no main turn was live." | Prevents a successful compact from losing its continuation while preserving immediate steering when a live turn exists and fail-closed removal at the final deadline. | Revisit if the SDK adds atomic compact-and-continue or exposes a direct readiness API that eliminates transient queue admission. |
| The native Copilot runtime and same-user extension processes are inside the trusted execution domain for faithful `session.send`, queue mutation, and session-event emission. | Existing self-compact state and locks use user-only local files and cannot defend against another process running as the same OS user; every accepted SDK receipt already relies on the joined runtime's events and RPC results. | Keeps the boundary focused on crashes, races, stale events, accidental concurrent work, and unsupported transports rather than claiming protection from a malicious local user or compromised native runtime. | Revisit if extensions become mutually untrusted, the runtime crosses a privilege boundary, or the product requires adversarial same-user tamper resistance. |
| Detached helpers must survive the initiating extension/tool process. | The authorizing turn ends before compact can safely start; unattended handoff may outlive the caller. | Avoids deadlock and half-started operations. | Revisit if extension background tasks gain documented lifetime guarantees. |
| Windows paths and process liveness use platform APIs rather than shell syntax. | Direct `EFTYPE` failure and absent POSIX commands on this host. | Standard Windows support without hidden dependencies. | Revisit only if the plugin formally requires a POSIX compatibility layer. |

Hard numeric timeouts remain configurable and preserve their current maximums;
this change does not invent new capacity limits.

## Reframe gate

**Status: CLEAR.** The first candidate fixed the helper runtime boundary, but
live proof exposed a second verified divergence in the existing generic
session-inbox compact path: `queue.sendNow({id}).steered === false` was treated
as proof that an exact newly queued immediate message could never deliver.
SDK documentation instead says it means no main turn was live, and the
disposable Windows trace shows that such a message naturally starts an `idle`
turn. A second challenge identified the remaining correlation gap: a
same-content foreign event cannot prove that the exact queued item delivered.
A third challenge correctly noted that the public SDK exposes no common
message/queue/event identifier. The architecture therefore states its existing
trust boundary explicitly instead of pretending to defend against a malicious
native runtime or another process with the same OS-user authority.

1. The blocked user-visible outcome is one token-bound compact followed by
   exactly one SDK continuation on standard Windows.
2. The blocking constraint is the inherited queue-recovery rule that removes
   the exact queued message immediately when `sendNow` reports no live main
   turn. It came from implementation history, not the SDK contract.
3. Removing continuation correlation, permitting an unconfirmed FIFO delivery,
   or accepting a nonce-bearing event while the exact queued item remains live
   would violate the exactly-once and draft non-interference invariants. A
   malicious same-user process can already rewrite the run metadata, lock, and
   event log and is not a separately defendable actor in this architecture.
4. Without that inherited rule, the simplest design binds the continuation to
   a fresh 128-bit nonce in the self-compact run metadata and exact prompt,
   sends after matching compact completion, attempts existing steering
   recovery, and when `sendNow` reports no live main turn waits through the
   existing confirmation deadline for the nonce-bearing prompt's natural
   `idle` delivery. Under the existing trusted-runtime boundary, the fresh
   nonce makes that event operation-unique. Success additionally requires that
   the exact queued item no longer be pending. A matching event while that item
   remains pending is ambiguous and the item is removed to prevent a later
   duplicate.
5. Correcting the existing queue state interpretation has fewer trusted
   components than lifecycle polling, pausing autopilot, adding a
   workflow-specific retry service, or moving SDK ownership into self-compact.

The working-r7 constraint challenge returned `CONTINUE` / `CLEAR`. Round-1
design review then required a final pre-publication root-activity check,
receipt authority precedence, unconditional post-`publishing` lock retention,
and explicit `queue.removeAt().removed` handling. Those changes form
working-r8. Its focused challenge returned `CONTINUE` / `CLEAR`; design review
round 2 closed three findings, required synchronization of the normative
receipt/removal text, and proved that a read immediately before `publishing`
still left an unenforceable interval. Working-r9 moves the marker before the
final scan, retains the exact authorization boundary, and makes all later root
activity disqualifying. Its focused challenge returned `CONTINUE` / `CLEAR`;
the resolution-only review may verify only the remaining publication-boundary
and normative-contract findings.

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

The event-triggered constraint recheck for working-r3 returned `CONTINUE` /
`CLEAR`. Focused round-2 reviews by Claude Opus 5 and GPT-5.6 Terra both
applied the architecture and scope lens, marked both prior findings resolved,
and reported no remaining findings.

Live proof later reopened the design. The working-r4 challenge rejected a
post-completion `session.idle` gate because the real Windows runtime emitted no
such event before readiness. A disposable trace established transient queued
admission followed by natural `idle` delivery. The working-r5 challenge then
identified that content-only matching could certify a foreign event while the
exact queued item remained live. Working-r6 adds a fresh continuation nonce and
requires both its exact event and disappearance of the exact queued item.
Working-r6's challenge found no public item-to-event identifier and required
the work order either to obtain one or define the exclusive trust boundary.
Working-r7 records the already-existing native-runtime/same-user trust domain;
its challenge returned `CONTINUE` / `CLEAR`. The design gate remains open only
for the required both-family design review of working-r7.

## Reuse contract and architecture

### Generic SDK transport

`extensions/session-inbox/request.mjs` remains the durable request publisher
and `extensions/session-inbox/extension.mjs` remains the only owner of SDK
send, native autopilot command invocation, compaction, and continuation
delivery. No workflow-specific branch is added there unless a live probe proves
an existing cross-platform defect.

The `921a220` live probe proved such a generic defect. The compact executor
sends the continuation after the matching successful completion; no
wall-clock stabilization delay or separate readiness event is authoritative.
`sendAndConfirm` continues to identify exactly one newly queued item and tries
`queue.sendNow`. If `steered` is true, it requires matching steering delivery.
If `steered` is false, the SDK says no main turn was live, so the executor must
leave that exact item in place and wait through the existing confirmation
deadline for matching natural `idle` delivery. It then re-reads the queue.
Success requires both the exact nonce-bearing event and absence of the exact
queued item. If a matching event appears while that item remains pending, the
executor removes only that item and reports ambiguity because the observed
event is not proven to be its delivery. If no matching event appears and the
item remains pending at the deadline, definitive no-continuation requires
`queue.removeAt({id}).removed === true` and a final event rescan with no
nonce-bearing delivery. `removed: false`, a removal error, an event observed
during or after removal, or disappearance without a matching delivery event is
ambiguous. The executor writes this classification into the authoritative
session-inbox receipt; the verifier may corroborate it but never upgrade it.
The fixed stabilization delay is removed rather than increased.

Completed compact receipts additively carry `continuationAccepted`,
`continuationMessageId`, `continuationDelivery`, and, on a definitive
continuation failure, `continuationError`. Ambiguous receipts set top-level
`ambiguousSideEffect: true` and preserve the observed continuation fields in
`result`. Missing continuation-classification fields are non-success, never an
implicit compatibility success.

Within the supported trust model, a fresh private 128-bit nonce makes the
continuation prompt unique to one run. The joined native runtime's exact
nonce-bearing `user.message` event is authoritative evidence that the prompt
entered the agentic loop. This does not claim protection against another
same-user process that reads private run state or forges runtime events; such a
process can already alter the lock, receipts, checkpoint files, and event log
used by every other self-compact proof.

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
2. `verifier-starting`: create a fresh 128-bit continuation nonce; write the
   exact brief plus run token, the fixed continuation prefix plus that nonce,
   candidate metadata, and run log paths with user-only permissions; spawn the
   detached verifier with inherited operation metadata.
3. `verifier-owned`: the verifier validates the lock token, writes
   `watcher.pid`, atomically changes the lock state, opens its log, then creates
   a readiness artifact containing the same lock token. Only after reading
   that exact readiness token does the foreground write the two-line atomic
   handoff containing lock token and `toolCallId` and return its receipt.
4. `authorized`: the verifier observes exactly one matching tool completion,
   no conflicting root activity, and the end of the authorizing turn. The
   successful authorization tail read supplies an exact byte boundary; the
   verifier must not replace it with a later file-size snapshot. It then
   resolves the target generation.
5. `publishing`: atomically persist that authorization byte boundary, target session ID,
   target generation, tool call ID, run token, lock token, deterministic dedupe
   key, and expected request receipt directory before spawning the request
   publisher. Entering this state means a side effect may occur and the lock is
   no longer automatically reclaimable. Only after the marker is durable does
   the verifier perform its final event-tail classification from the recorded
   authorization boundary. If any unrelated root activity arrived during
   target resolution or this check, it publishes no request and retains the
   lock. Because the public SDK exposes no transaction shared with the root
   event writer, every later root event remains in the same recorded range and
   is disqualifying during receipt/completion verification. It may coexist with
   a native compact, but can never authorize success, release, or retry.
6. `request-published`: after the publisher returns a request ID, atomically
   persist that ID and its pending/processing/completed/failed receipt paths.
7. `compact-observed`: require one successful completion whose
   `customInstructions` exactly equal the brief plus this run token and whose
   checkpoint number exceeds the baseline.
8. `checkpoint-observed`: require `workspace.yaml` to reach that checkpoint
   and exactly one numbered checkpoint file.
9. `continuation-observed`: require both the authoritative session-inbox
   receipt for this request ID to report non-ambiguous continuation success
   with `idle` or `steering` delivery and exactly one corroborating root user
   message whose content equals the fixed continuation prefix plus this run's
   nonce after the completion boundary. A nonce-bearing event cannot override
   an ambiguous or failed receipt.
10. `completed`: write terminal state and release only this run's artifacts and
   lock.

A definitive failure before the `publishing` transition removes the current
run's artifacts and lock. Every failure at or after `publishing` retains the
lock and run metadata, whether its continuation outcome is definitive or
ambiguous, because the compact side effect may already have occurred. Such a
lock is never automatically reclaimed or retried.

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
  continuation nonce, exact prompt, `continuationAccepted`,
  `continuationMessageId`, `continuationDelivery`, ambiguity/error
  classification, and corroborating event delivery/count.

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
- An exact queued continuation for which `queue.sendNow` reports no live main
  turn is allowed to drain naturally only until the existing confirmation
  deadline. Matching nonce-bearing `idle` delivery plus disappearance of the
  exact queued item is success. A same-content event while the item remains is
  ambiguous and the item is removed to prevent duplication. A still-pending
  item with no matching event is removed and reported as definitive
  continuation failure. Disappearance without matching delivery is ambiguous.
- A queue removal proves definitive no-continuation only when
  `queue.removeAt({id}).removed` is true and a final event rescan still finds no
  nonce-bearing delivery. `removed: false`, a removal error, or a matching
  event observed during or after removal is ambiguous.
- The authoritative session-inbox receipt owns continuation classification.
  The verifier's event-log check corroborates identity, delivery, and count;
  it cannot upgrade a failed or ambiguous receipt to success.
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
   continuation carrying the run's fresh 128-bit continuation nonce.
6. Definitive failure before the durable `publishing` transition releases or
   permits safe stale recovery of the lock; every failure at or after
   `publishing`, definitive or ambiguous, retains it.
7. Workflow policy remains in its owning skill/extension, not in the generic
   session-inbox transport.

## Acceptance criteria and check contract

| Criterion | Check | Failure signal |
| --- | --- | --- |
| Portable autopilot helper | Node tests cover validation, exact objective bytes, request arguments, confirmed receipt, failure receipt, and Windows-style paths. | Any invalid input publishes a request, or a non-confirming SDK result returns success. |
| Native autopilot on Windows | A live exact-session request sets a disposable objective and the receipt proves native objective state plus `idle`/`steering`. | Missing/mismatched objective, queued activation, timeout, or success without native state. |
| Portable self-compact orchestration | Node tests cover tool binding, every named lock-state transition, token-matched readiness and handoff, foreground death after handoff, verifier startup failure, verifier death after handoff but before `publishing`, safe reclaim of that pre-attempt state, crash at/after `publishing` with retained lock, request classification, replay/duplicate request, stale/manual-equivalent completion events, token matching, checkpoint proof, continuation count, and Windows paths. | A malformed/current-conflicting invocation starts compact, detached creation is mistaken for ownership, a pre-attempt dead verifier permanently wedges the session, or incomplete proof returns success. |
| Publication-boundary root-activity check | A deterministic fixture captures the successful authorization tail boundary, pauses target-generation resolution, appends a new supported root-activity event, then releases resolution. The verifier must write `publishing` with the original boundary, classify the appended event before spawning the request, publish no request, and retain the post-marker lock. Companion fixtures append activity after the final scan but before request execution and between request execution and compact completion; both must remain visible from the recorded boundary and prevent success/release/retry. | A later file-size snapshot hides intervening activity, an event occupies an undefined read-before-marker interval, any root activity after authorization can still reach `completed`, or a post-marker failure releases/retries. |
| Post-compact transient queue drain | The session-inbox harness makes the nonce-bearing continuation appear as the exact new queued item, makes `queue.sendNow` return `steered: false`, removes that item when emitting the matching `idle` event, and requires one successful message ID/delivery without `queue.removeAt`. Companion fixtures cover: the same nonce-bearing event while the exact item remains pending, which requires `removed: true` plus ambiguity; no event with the item still pending, which requires `removed: true`, a final no-event rescan, and definitive continuation failure; `removed: false` followed by a matching event, which requires ambiguity; a removal error, which requires ambiguity; and disappearance without an event, which requires ambiguity. | A valid transient item is removed before natural idle delivery, queued admission or content alone is reported as success, a foreign/pre-existing item is removed, a false/failed removal is reported as definitive, a late event is ignored, the same-content/pending-item case can later duplicate, or disappearance without delivery is reported as definitive. |
| Continuation operation identity | Self-compact tests require a fresh 128-bit continuation nonce in run metadata and the exact continuation prompt, reject missing/reused/mismatched nonces, and prove the verifier accepts only one exact nonce-bearing root event after the token-bound compact boundary. | A fixed same-content prompt can certify a foreign event, a nonce is absent or reused, or a mismatched event releases the lock. |
| Authoritative continuation outcome | A verifier fixture supplies one exact nonce-bearing event while the correlated session-inbox receipt reports failed or ambiguous continuation, and requires a terminal retained-lock failure. Only a correlated completed receipt with `continuationAccepted: true`, `delivery: idle|steering`, and the exact corroborating event may reach `completed`. | The event log upgrades a failed/ambiguous receipt, the wrong request receipt authorizes success, or a definitive post-publication continuation failure releases the lock. |
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
extensions. Existing envelopes, requests, checkpoints, and lock formats remain
compatible. Compact receipts gain additive continuation-classification fields;
an older or version-skewed receipt without those fields is treated as
non-success and retains the lock. A lock from an ambiguous run is never removed
by rollback without inspecting its run log and receipt.

The `921a220` proof lock is retained because the compact side effect occurred.
Before a successor live attempt, an operator may remove only that exact lock
after recording the completed receipt, checkpoint 1, absent continuation, dead
verifier PID, and the fact that the SDK removed the queued message. This is
manual adjudication of a known terminal outcome, not automatic stale recovery.

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
