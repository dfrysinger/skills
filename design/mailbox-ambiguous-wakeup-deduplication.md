# Mailbox Ambiguous Wakeup Deduplication

## Objective

Ensure one durable mailbox envelope can cause at most one native Copilot send
side effect when session-inbox accepted the send but could not confirm its
delivery before the active turn completed.

## Non-goals

- Do not make the mailbox envelope itself at-most-once; it remains pending until
  the recipient acknowledges it.
- Do not treat a returned SDK message ID as proof that the user turn was
  delivered.
- Do not add a timer, retry service, queue, daemon, remote lock, or OneDrive
  state.
- Do not automatically retry an ambiguous send with a new dedupe identity.
- Do not change session-inbox behavior for completed or definitive-no-side-
  effect requests.
- Do not repair Copilot's native queue or delayed `user.message` event timing.
- Do not hide an ambiguous wakeup as delivered; callers still receive
  `unverified`.

## Lane

**Systemic.** This changes the retry semantics shared by mailbox senders,
watchers, and session-inbox's persistent dedupe records. It affects concurrency
and durable local state but does not change authentication, authorization,
remote transport bytes, or mailbox envelope ownership.

## Observed failure

On Windows, deterministic session
`ab7c0c56-f5b8-5e16-9d9e-49808182c874` was in a 60-second tool turn. One local
envelope,
`20260829T095121604Z-10696-dca16af02107`, caused session-inbox to call
`session.send({ mode: "immediate" })`. Each call returned a message ID but no
matching `user.message` event inside the ten-second confirmation window.

Mailbox treated each ambiguous receipt as permission to rotate the envelope's
attempt ID. The watcher therefore generated a new dedupe key on every poll and
session-inbox performed another native send. When the active turn completed,
the session transcript contained six identical steering user-message events
for that one envelope. The agent read and acknowledged the envelope once, but
the duplicate native turns had already violated the exactly-once notification
boundary.

The first divergence is
`skills/mailbox/scripts/mailbox-core.mjs` rotating the notification attempt
after `ambiguousSideEffect` or `delivery:"unconfirmed"`. Session-inbox already
persists an `ambiguous` record for the original dedupe key and refuses to
execute that key again; rotation bypasses that protection.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit condition |
| --- | --- | --- | --- |
| The durable envelope remains pending until acknowledgement. | Existing mailbox ownership contract. | A lost or ambiguous nudge cannot lose mail. | Revisit only with a different durable delivery protocol. |
| A message ID without an `idle` or `steering` event remains unverified. | Live queue-desynchronization evidence and existing session-inbox contract. | Prevents success-shaped receipts for turns that may be stranded. | Revisit if the SDK exposes a durable accepted-and-deliverable acknowledgement. |
| One envelope retains one dedupe key after an ambiguous send. | Live six-turn reproduction plus existing session-inbox ambiguous-dedupe refusal. | Prevents a watcher poll from turning uncertainty into duplicate native sends. | Revisit if session-inbox can prove the original send had no side effect. |
| One local terminal marker suppresses further automatic attempts for that envelope. | Existing `notified/<address>/` state owner and the observed two-second watcher loop. | Prevents an ambiguous pending envelope from creating unbounded failed receipts and diagnostics. | Revisit if notification retries gain an authoritative no-side-effect event. |
| No time-based retry follows ambiguity. | No measured timeout can distinguish a delayed event from a lost send; the observed event arrived after one minute. | Avoids moving the duplicate boundary to a larger arbitrary delay. | Revisit only with a platform event that proves the prior send cannot still appear. |
| Local notification state remains machine-local. | Local-first mailbox design. | Keeps mutable retry and dedupe ownership out of OneDrive. | Revisit only through `windows-cross-computer-mailbox-addressing.md`. |

No new numeric limit is introduced. Existing watcher and confirmation intervals
remain implementation details; neither authorizes a new side effect after an
ambiguous result.

## Reframe gate

Implementation returns here before adding machinery if:

- reusing the same dedupe key still calls `session.send()` more than once;
- preventing rotation requires a new state owner or protocol;
- the durable envelope is removed or hidden after ambiguity;
- definitive no-side-effect failures stop being retryable; or
- Copilot exposes an authoritative event that distinguishes delayed delivery
  from no side effect.

**Status: CLEAR.** Existing session-inbox tests prove a second request with the
same key after an ambiguous send returns the prior ambiguity without another
`session.send()` call. The mailbox already owns per-envelope notification files
under `notified/<address>/`; one `.unverified` terminal marker in that directory
prevents both a new dedupe identity and unbounded same-key receipt churn.

## Reuse contract

- `notificationAttemptId()` remains the sole mailbox owner of the per-envelope
  attempt ID.
- `notified/<address>/<envelope>.unverified` records that the current attempt
  had an ambiguous side effect. It is owned and cleaned by the same code that
  owns `.attempt` and `.notified`.
- Session-inbox's existing dedupe record remains the sole owner of whether that
  key is completed, ambiguous, or unused.
- The pending envelope remains the durable user-visible fallback.
- Existing notification claims continue to serialize concurrent sender and
  watcher attempts.
- Existing `.notified` markers are still written only for confirmed `idle` or
  `steering` receipts.

No new service, lock, state root, registry, or public command is added.

## Data flow

1. Sender or watcher finds an unnotified pending envelope.
2. Mailbox obtains its existing attempt ID and sends one request with the
   envelope-derived dedupe key.
3. Session-inbox performs the native send and either:
   - confirms `idle` or `steering`, allowing mailbox to write `.notified`; or
   - records the dedupe key as `ambiguous` and returns an unverified receipt.
4. On ambiguity, mailbox preserves the same attempt ID, writes one
   `<envelope>.unverified` marker containing that attempt ID, and returns
   `unverified`.
5. Later watcher polls treat `.unverified` like `.notified` for request
   suppression, but never report the ambiguous wakeup as delivered.
6. When the envelope leaves `pending/`, normal notification cleanup removes its
   `.attempt` and `.unverified` files.
7. The envelope stays in local `pending/` until the agent or user reads and
   acknowledges it.

## Failure model

- If the original ambiguous send later appears, it appears once because no new
  dedupe identity was issued.
- If the original send never appears, automatic wakeup remains unverified and
  the durable envelope remains visible in `pending/`. Manual mailbox checks and
  existing resume hints remain recovery paths.
- Repeated watcher polls do not create another request, failed receipt,
  diagnostic failure, or native send for that envelope.
- A later unnotified envelope for the same mailbox may produce one new wakeup.
  If that wakeup is confirmed, the existing ready-envelope sweep marks every
  pending ready envelope notified, including the older ambiguous envelope.
- A definitive no-side-effect failure has no ambiguous dedupe record and
  remains retryable with the same attempt ID.
- Confirmed delivery still writes `.notified` and prevents further requests.

## Hard invariants

1. One envelope has one notification attempt ID until confirmed or
   acknowledged.
2. Ambiguity never rotates the attempt ID.
3. Ambiguity writes one local `.unverified` marker for the current attempt.
4. Repeated watcher polls create no further request for that envelope.
5. Session-inbox executes `session.send()` at most once for that key.
6. Ambiguity remains visible as `unverified`; it is not promoted to success.
7. The envelope remains pending and readable after ambiguity.
8. Confirmed and definitive-no-side-effect behavior remains unchanged.
9. Notification attempts, dedupe records, claims, and markers remain local.

## Acceptance criteria

1. One ambiguous mailbox attempt preserves its dedupe key and writes one
   `.unverified` marker.
2. Later watcher polls create no additional session-inbox request, failed
   receipt, or native `session.send()` call for that envelope.
3. One envelope sent during a live long-running turn produces exactly one
   matching `user.message` event after the turn settles.
4. The caller receives `unverified` before confirmation and the envelope
   remains pending.
5. The recipient can read and acknowledge that envelope normally.
6. A confirmed wakeup still writes notification markers and returns
   `delivered`.
7. A definitive no-side-effect failure remains retryable.
8. A later new envelope remains eligible for one wakeup and a confirmed wakeup
   marks all ready pending envelopes notified.

## Check contract

| Check | Protects | Setup and transition | Pass signal | Failure meaning |
| --- | --- | --- | --- | --- |
| Mailbox ambiguous terminal-state test | Stable per-envelope attempt identity and bounded local state. | Return an ambiguous receipt, poll the same pending envelope again, and inspect notification state and request files. | Attempt ID is unchanged; one `.unverified` marker exists; the second poll creates no request or failed receipt; no `.notified` marker exists. | Mailbox can bypass dedupe, duplicate a native turn, or churn local receipts forever. |
| Session-inbox ambiguous dedupe test | One native side effect per key. | Submit the same prompt and dedupe key after an unconfirmed native send. | Second receipt remains ambiguous and native send call count stays one. | Reused mailbox keys can still execute twice. |
| Confirmed and definitive-failure regressions | Existing retry boundary. | Exercise confirmed delivery and a failure before side effects. | Confirmed writes `.notified`; definitive failure can retry. | The fix hides pending mail or blocks safe retries. |
| New-envelope recovery test | Mailbox-level liveness after one ambiguous envelope. | Leave one envelope `.unverified`, add another envelope, and confirm its wakeup. | The new envelope gets one request and confirmed delivery marks both ready envelopes `.notified`. | One ambiguity disables the entire mailbox or leaves stale terminal state. |
| Slow-turn live proof | Actual delayed event boundary. | Keep `hotel` in a tool turn longer than the confirmation timeout and send one marked envelope. | One matching steering/idle user-message event, one read, and one acknowledgement; no duplicate prompt. | Poll retries still create duplicate native turns. |
| Existing focused suite | Adjacent mailbox/session-inbox behavior. | Run the current Node tests. | Expected pass/skip baseline plus the new regression passes. | Shared request or mailbox behavior regressed. |

## Migration and rollback

Existing `.attempt`, `.notified`, and session-inbox dedupe files require no
migration. New `.unverified` markers are local, per-envelope state and are
removed by the same pending-envelope cleanup as the existing files.

Rollback restores attempt rotation, which restores repeated automatic wakeup
attempts but also restores the reproduced duplicate-turn failure. Pending
envelopes and remote transport records remain compatible in either direction.

## Definition of Done: ambiguous mailbox wakeup deduplication

- The ambiguous retry regression proves one stable dedupe key and one terminal
  `.unverified` marker without repeat request or receipt churn.
- Existing session-inbox coverage proves one native send for repeated ambiguous
  requests.
- Confirmed and definitive-no-side-effect paths remain covered.
- The focused mailbox/session-inbox suite passes.
- A real long-turn Windows proof produces one marked native user-message event,
  one read, and one acknowledgement for one envelope.
- Dual implementation review has no material finding.
- The fix lands with the deterministic Windows naming change in plugin
  0.108.18.
