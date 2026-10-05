# Self-Compact Interruption Reliability

## Objective

Make one self-compaction request remain understandable and recoverable across
stale session readiness and one pre-publication user interruption without
losing, replaying, or delaying the user's message and without weakening the
existing exactly-once compaction boundary.

## User decisions

The durable decision record is
`design/self-compact-session-control-decisions.json`.

- A user interruption must not cause the requested compaction to disappear
  forever. The user message remains native session input and is answered
  normally; it is never captured or replayed by self-compact.

The approved `session-control` rename is a separate systemic work order at
`design/session-control-rename.md`. It is not a prerequisite, acceptance check,
or rollback dependency of this critical reliability change.

Evidence packet revision: `evidence-v2` in
`design/self-compact-session-control-evidence.json`.

## Lane

**Critical.**

This change alters the fail-closed authorization boundary between a private
compaction brief, root conversation activity, a detached verifier, and native
session compaction.

### Protected assets and actors

- **Protected assets:** the private brief, user-message integrity, one-shot
  compact identity, checkpoint identity, continuation identity, and the exact
  active autopilot objective.
- **Owner-controlled code:** the installed `self-compact` extension, the shared
  session request extension, and their deterministic helpers.
- **Untrusted choice:** model-authored visible prose and tool selection in the
  user-interruption turn.
- **Forbidden operations:** copying the private brief into visible prose,
  synthesizing or replaying user text, publishing a second compact request for
  one operation, or retrying an ambiguous/post-publication result.
- **Owner-approved operations:** temporarily pausing autopilot, sending a fixed
  brief-free control prompt, answering the user's message, and resuming or
  canceling the pending compact through an explicit tool action.

No external policy is evidenced. Deliberate owner grants remain allowed.

## Non-goals

- Do not queue, copy, summarize, rewrite, or replay the user's message.
- Do not compact while the interrupting user turn is still unresolved.
- Do not add FIFO/enqueue delivery; the repository intentionally permits only
  native immediate delivery.
- Do not add a scheduler, background retry daemon, generic workflow engine, or
  cross-session pending-compaction service.
- Do not retry an ambiguous or post-publication compact outcome.
- Do not relax token-bound completion, exact checkpoint advancement,
  exactly-once continuation, or retained-lock behavior.
- Do not rename historical receipt contents or require migration of existing
  completed evidence.
- Do not redesign mailbox envelopes, unattended-run objectives, or session
  rotation.
- Do not rename the shared request extension or migrate its storage in this
  change.

## Current failure

The foreground `self_compact` tool returns after arming a detached verifier.
The authorizing assistant turn then ends. If a user message arrives before the
verifier publishes the compact request, the verifier correctly cancels, but
that cancellation exists only in its log. The new user turn receives neither
the status nor the private brief, so an interactive session has no
deterministic way to resume the requested compact. Active autopilot happened to
create another attempt in the observed successful demonstration, but that is
not a general recovery mechanism.

A separate failure occurs when the request extension's generation heartbeat is
stale. The verifier discovers that only after the foreground tool reported
that it was armed.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit condition |
|---|---|---|---|
| User input is never captured or replayed | Direct user outcome plus existing draft non-interference boundary | User-message integrity | Revisit only if the user explicitly grants a new message-replay capability |
| Private brief remains only in structured state | Existing self-compact contract and observed successful proof | Confidential steering state and exact authorization | Revisit only if the CLI supplies a native opaque continuation token |
| New user activity prevents immediate publication | Existing fail-closed authorization boundary | Changed user intent and current-turn authority | Revisit only if the SDK supplies an atomic user-intent/quiescence lease |
| One interrupted compaction remains recoverable | Direct user decision | The requested operation is not silently lost | Revisit if observed use requires more than one recovery cycle or the CLI natively resumes interrupted tools |
| No ambiguous/post-publication retry | Existing one-shot boundary | Duplicate compaction and continuation prevention | Revisit only with a native idempotent compact operation identity |
| Immediate delivery only | Repository guard and current shared request-extension contract | No hidden FIFO message accumulation | Revisit only through a separate reviewed delivery design |
| One live operation per session | Two evidenced conflicting actors: foreground submitter and detached verifier | Single writer at publication and cleanup | Revisit if native SDK compaction becomes atomic and self-identifying |
| One recovery cycle per operation | The user authorized recovery from an interruption; no evidence supports an unbounded prompt loop | The request survives the observed failure without repeated automated turns | Revisit after an observed second interruption that should remain automatic |
| Native compaction retains conversation turns through its trigger while custom instructions steer rather than replace the generated summary | Copilot CLI native compaction contract assumed by the existing self-compact skill; not yet proven for a post-brief interrupted exchange | The user question and answer survive without copying them into the private brief | If the live proof cannot find both unique exchange markers after compaction, mark the reframe status OPEN and return to design; do not amend the brief or add message capture |

## Reframe gate

**Status: CLEAR.**

The current design adds no new service or transport. It extends the existing
self-compact verifier and the existing shared session request extension. It
must return to design before implementation adds a second process, a queue, a
message-replay path, a new persistence owner, or a new delivery mode.

The simpler future design is a native SDK operation that atomically pauses
autopilot, establishes a user-activity lease, compacts at the next safe idle
boundary, and restores the objective. If that capability appears, the
extension-level resume protocol should be retired rather than expanded.

## Reuse contract

The change reuses:

- the existing session-scoped self-compact lock as the single operation owner;
- the existing private candidate, instructions, continuation, and run files;
- the existing detached verifier as the only state-machine writer;
- the existing shared request extension's
  `session.send({ mode: "immediate" })` path for a fixed
  agent-control prompt;
- the existing generation heartbeat for a foreground readiness probe;
- the existing tool-call event parser for resume/cancel authorization;
- the existing deduplicated compact request and continuation verifier.

One new status artifact is required because the detached verifier reaches an
outcome after the foreground tool turn has ended. No existing tool result or
session event carries that outcome into the interrupting turn.

## Data flow

### Normal compact

1. Every synchronous `self_compact` entry path reads the existing
   generation-heartbeat artifacts before pausing autopilot, acquiring the
   operation lock, or launching a verifier.
2. Preparation pauses and privately stages the exact objective.
3. The final brief-bearing `self_compact` call creates one operation ID,
   acquires the session lock, and launches one verifier.
4. The verifier binds the tool call, publishes one generation-bound compact
   request, verifies the token-bound completion, checkpoint, continuation, and
   objective restoration, writes terminal success, and releases the lock.

### Interrupted compact

1. Before entering `publishing`, the verifier observes one new root
   `user.message`.
2. It does not publish and does not discard the operation. It writes status
   `interrupted`, including the root event ID and a brief-free reason.
3. Through the existing shared request extension, it sends one fixed immediate
   control prompt with only the operation ID. The prompt begins with
   `[self-compact-control:<operationId>]` and states that it is generated
   control input, not user-authored text. The verifier records the accepted
   SDK message identity and exact prompt. Delivery may be steering into the
   active user turn or idle if that turn has already ended.
4. The prompt instructs the agent to answer the user normally. After the
   answer, the agent must make exactly one final tool request:
   - `self_compact { action: "resume", operationId }` if the latest instruction
     still permits compaction; or
   - `self_compact { action: "cancel", operationId }` if it cancels or
     supersedes compaction.
5. A resume call contains no brief. Its handler verifies the live lock,
   operation ID, interrupted status, and root event identity, then writes one
   resume handoff for the same verifier.
6. Resume authorization permits visible assistant prose before the tool call
   because that prose answers the interrupting user. It still requires exactly
   one final self-compact tool request and no later root activity.
7. The same verifier either loops back to authorization or releases on cancel.
   The operation retains one compact dedupe key and can publish at most once.

The one generated control event is excluded from interruption counting and
resume-authorization root activity only when its accepted SDK message identity,
exact fixed prompt, operation ID, and `steering` or `idle` delivery all match.
A user message that quotes or reproduces the marker has another event identity
and remains an interruption.

### Second interruption

One operation supports one automatic interrupted/resume cycle. A second user
interruption records terminal failure, restores the staged objective, releases
the pre-publication lock, and sends one fixed terminal control notice. The user
may request a new compact after that turn. This is the smallest bounded policy
supported by the observed single-interruption failure.

### Stale readiness

Every `prepare`, initial brief-bearing compact, resume, and cancel entry reads
the existing heartbeat artifacts for the exact session through a shared pure
helper. It succeeds only when exactly one fresh generation matches. The
generation lookup is session-scoped, so another live session does not conflict.
For initial preparation or compact, failure is returned synchronously before
autopilot is paused, a lock is acquired, or a verifier is launched. Resume and
cancel may still operate on a live local lock when transport readiness is
unavailable, but cannot send another control prompt.
The detached verifier still rechecks generation immediately before publication
because readiness can change after preparation.

## Status model

The verifier owns one `self-compact-<operationId>.status.json` artifact:

```json
{
  "version": 1,
  "operationId": "eight-lowercase-hex",
  "runId": "timestamp-pid",
  "state": "armed",
  "reason": "brief-free status",
  "observedRootEventId": null,
  "attempt": 0,
  "updatedAt": "ISO-8601 timestamp"
}
```

Allowed states:

- `armed`
- `interrupted`
- `resuming`
- `publishing`
- `terminal-success`
- `terminal-cancelled`
- `terminal-failure`

Only the verifier writes state transitions after initial creation. The
foreground resume/cancel helper writes a separate exclusive handoff artifact;
it never edits verifier state.

Terminal artifacts remain as authoritative receipts. Success cleanup removes
private brief-bearing artifacts and the live lock. A terminal pre-publication
cancel removes the lock and private artifacts after recording the brief-free
terminal status. Ambiguous/post-publication failures retain the lock and full
evidence as today.

## Failure model

- **Readiness probe fails:** synchronous failure, no pause, no verifier, no
  pending operation.
- **Readiness changes after probe:** final verifier recheck fails closed and
  records terminal failure.
- **Control prompt is not accepted:** operation records terminal failure and
  releases only when publication never began.
- **Control prompt is delivered as steering:** the current answer may include
  prose before the final resume/cancel tool call.
- **Resume tool uses the wrong operation ID:** synchronous refusal; verifier
  remains pending until its existing deadline.
- **Another user message arrives before resume authorization completes:** the
  operation reaches terminal failure; no compact request exists.
- **User cancels:** explicit cancel tool call records terminal cancellation,
  restores autopilot if staged, and releases.
- **Deadline expires while interrupted:** terminal failure, objective restore,
  release because publication never began, and one fixed terminal control
  notice.
- **Any failure after publication starts:** retain the lock and do not retry.
- **Root activity discovered after `publishing` is durably recorded but before
  the request side effect:** record a visible terminal non-resumable outcome
  and retain the lock. Recoverable interruption applies only before
  `publishing`; the design does not move the fence later.
- **A prior terminal operation exists when any later self-compact tool action
  starts:** synchronously report its brief-free terminal state and reason
  before processing the new action. This is the fallback read path when the
  control transport could not deliver a terminal notice.

## Invariants

1. One operation owns at most one verifier, one live lock, one compact request,
   one successful compact event, one checkpoint, and one continuation.
2. User-authored text is read only from the native event log and is never
   copied into an artifact or control prompt.
3. The private brief appears only in the original structured tool request and
   private files.
4. Resume/cancel control prompts contain only fixed text and the opaque
   operation ID.
5. A resume tool call carries no brief and cannot select another operation.
6. No publication occurs while an unresolved root user turn follows the latest
   authorization.
7. A changed user instruction can cancel through an explicit final tool call.
8. Preparation never pauses autopilot unless readiness already passed.
9. The exact staged objective is restored after success or any definitive
   pre-publication terminal outcome.
10. The generated control prompt is visibly marked and its root event retains
    native `steering` or `idle` delivery metadata; it never suppresses,
    reorders, or alters the interrupting user message.
    Exactly one event matching the accepted SDK message identity, fixed prompt,
    operation ID, and delivery is exempt from interruption counting. Marker
    text alone never grants the exemption.
11. Native compaction summarizes the complete conversation through the compact
    trigger. The private brief is a steering delta, not replacement content,
    so the interrupting question and answer survive without changing the brief.
12. `publishing` is durably recorded before the first request-publication side
    effect. Every `publishing`-or-later failure is non-resumable.

## Acceptance criteria

1. A stale heartbeat causes both autopilot preparation and a direct interactive
   brief-bearing compact to fail synchronously with a clear readiness error;
   autopilot remains unchanged and no verifier, lock, or pending status exists.
2. A healthy preparation followed by no interruption completes one compact,
   one checkpoint, one continuation, and exact objective restoration.
3. A user message observed after handoff but before the durable `publishing`
   fence produces status `interrupted`; the message appears once as native user
   input and is answered before the resume tool call. Activity first observed
   after that fence follows criterion 8's visible terminal non-resumable path.
4. The fixed control prompt contains no user text and no private brief.
   Its marker and delivery metadata distinguish it from the interrupting user
   message, which remains ordered before the answer.
   The exemption also requires the exact accepted SDK message identity; a user
   message quoting the marker is not exempt.
5. Resume uses the same operation, verifier, lock, compact dedupe key, and
   private brief, then completes exactly once.
6. An explicit cancel after interruption publishes no compact request,
   restores the objective, records terminal cancellation, and releases.
7. A second interruption creates no compact request, records terminal failure,
   restores the objective, releases the pre-publication lock, and emits one
   fixed terminal notice.
8. A post-publication ambiguous result is never resumed and retains its lock.
   Root activity found after the `publishing` marker is classified here even
   when the request side effect has not yet been observed.
9. A terminal timeout or refusal is surfaced through one fixed control notice
   when transport works. If transport does not work, the next self-compact tool
   entry synchronously reports the durable terminal state; the outcome is not
   recoverable from log prose alone.
10. The installed candidate passes a real interactive scenario in which a user
    interruption is answered and the same operation subsequently compacts and
    resumes once.

## Check contract

| Check | Setup and transition | Passing signal | Failure proves |
|---|---|---|---|
| Readiness-before-entry test | Active and inactive autopilot plus zero, one, and multiple fresh generations | Only one generation permits preparation or initial compact; failure leaves objective active and creates no lock/verifier | Any supported entry path can appear armed before transport readiness |
| Resume parser tests | Interrupted operation plus matching, wrong, duplicate, and prose-bearing resume/cancel turns | Matching sole final call accepted; wrong/duplicate/later activity refused | Resume authorization can bind the wrong turn or operation |
| Interruption state-machine test | Authorize, append root user event before `publishing`, deliver control prompt, then resume; repeat with a user message that quotes the control marker | One verifier and one compact publication; the fixed marker and generated-control label are present; delivery metadata and accepted SDK message identity match; the native user message remains ordered before its assistant answer and is unchanged; the quoted marker is not exempt | Interruption can lose or duplicate the operation, or control input can become indistinguishable from user input |
| Cancel state-machine test | Interrupt then explicit cancel | Zero compact publication, terminal cancellation, released lock | Changed user intent cannot stop pending compaction |
| Second-interrupt test | Interrupt during initial and resumed authorization | Terminal failure, objective restore, released pre-publication lock, zero publication | Retry creates a loop or second request |
| Ambiguous-outcome test | Mark publication before inducing failure | Retained lock and no resume prompt | Post-publication ambiguity can be retried |
| Publication-fence race test | Durably enter `publishing`, append root user activity before the request side effect | Terminal non-resumable status and retained lock; no resume prompt | Moving the fence or over-broad recovery can duplicate compaction |
| Terminal-status fallback test | Make terminal control delivery unavailable, then invoke any self-compact action | The action synchronously reports the prior terminal operation and reason | Detached failures can remain visible only in log prose |
| Real live proof | Installed exact candidate, active autopilot, interrupting question containing a unique marker, answer containing a second unique marker, resume | One terminal receipt, checkpoint advance, continuation, restored objective, and both unique exchange markers remain available to the post-compaction continuation exactly once | Scripted state machine does not work in the real CLI, or native compaction loses the interrupting exchange because the brief predates it |

No pre-implementation structural guard is required. Behavioral tests and the
existing no-enqueue check carry the contract.

## Rollback

Rollback to commit `49d3b7833be9f1774bd926c9366e16c2f599dc68`
and reinstall the plugin. Existing legacy storage remains untouched. Any
pre-publication operation from the new protocol must be terminally canceled and
its lock released before rollback. Any operation at or after publication keeps
its lock and is diagnosed from its receipt before rollback.

Fail-closed rollback evidence:

- no pending or processing shared session request;
- no live verifier from the candidate;
- no lock in a publication-or-later state;
- installed extension inventory matches the rollback commit;
- the existing active-autopilot compact proof remains reproducible.

## Definition of Done: Reliable Interrupted Self-Compaction

- Preparation proves one fresh target before pausing autopilot.
- Every operation has one brief-free, machine-readable status.
- A pre-publication user interruption is answered normally and resumes or
  cancels the same operation through an explicit final tool action when the
  interruption is observed before the durable `publishing` fence.
- One operation cannot create duplicate verifier, compact, checkpoint, or
  continuation effects.
- Ambiguous/post-publication outcomes remain fail-closed and non-retryable.
- Targeted tests and the real installed interactive proof pass on the exact
  reviewed candidate.
- The final diff is reviewed, committed locally, installed, and not pushed
  unless the user separately requests publication.
