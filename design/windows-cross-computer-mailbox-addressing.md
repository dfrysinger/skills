# Local-First Cross-Computer Mailbox

## Objective

Deliver messages between named agent sessions on one computer or across
computers without putting mutable mailbox state, locks, or acknowledgements in
a cloud-synced directory.

## Product contract

An unqualified address is local:

```text
hotel
```

It means the `hotel` session on the current computer. It is stored under
`MAILBOX_LOCAL_ROOT`, which defaults to `~/.copilot/mailbox`. It is not a
broadcast and never touches the remote transport.

A qualified address is cross-computer:

```text
hotel@surface-pro
```

It means the `hotel` session on the computer whose configured
`COPILOT_AGENT_MACHINE` is `surface-pro`. Qualified messages use
`MAILBOX_REMOTE_ROOT` only as an immutable transport. There is no automatic
hostname fallback and no implicit fan-out.

## Storage ownership

### Local mailbox root

`MAILBOX_LOCAL_ROOT` owns the mutable delivery lifecycle:

- `pending/` and `delivered/` envelopes;
- local attachment copies;
- reads and acknowledgements.

Legacy `MAILBOX_ROOT` remains a compatibility fallback for the local root.

### Local state root

`MAILBOX_STATE_ROOT` owns process and retry state:

- watcher locks;
- notification claims and markers;
- remote publication outboxes;
- remote import markers;
- diagnostics.

Session-inbox requests, receipts, heartbeats, claims, and logs are also local.

### Remote transport root

`MAILBOX_REMOTE_ROOT` may be a OneDrive directory. It contains only immutable,
single-writer transport records:

- `<name@machine>/pending/<id>.json`;
- `<name@machine>/pending/<id>/<attachment>`;
- `receipts/<name@machine>/<id>.json`.

The delivery path never renames, edits, or deletes a published remote file.
Retention cleanup is a separate concern.

## Delivery flow

### Same-computer message

1. The sender addresses `hotel`.
2. The mailbox writes the attachments and envelope into the local `hotel`
   mailbox.
3. It asks session-inbox to deliver `check mailbox; skip if empty` immediately.
4. Hotel reads the local envelope and acknowledges it by moving it from local
   `pending/` to local `delivered/`.

No remote directory is consulted.

### Cross-computer message

1. The sender addresses `hotel@surface-pro`.
2. The mailbox writes a complete envelope and attachments into a local
   `remote-outbox`.
3. The bridge copies attachments first and the envelope last into
   `MAILBOX_REMOTE_ROOT`.
4. If OneDrive is unavailable, the local outbox remains intact. Every watcher
   retries publication on later polls.
5. The Surface watcher observes only `hotel@surface-pro`. It waits for the
   remote files to be complete and stable.
6. It copies the envelope and attachments into the ordinary local `hotel`
   mailbox and records a local import marker.
7. It asks session-inbox to wake the local `hotel` session.
8. Hotel reads and acknowledges the local copy.
9. A separate immutable receipt is staged locally and published under the
   remote `receipts/` directory.

Acknowledgement does not modify the original remote envelope or attachments.

## Address and watcher rules

- Addresses contain either zero or one `@`.
- Agent and machine components use the existing safe-name validation.
- A session always reads and acknowledges its unqualified local mailbox.
- A configured watcher owns one local delivery loop and, when both
  `COPILOT_AGENT_MACHINE` and `MAILBOX_REMOTE_ROOT` exist, one qualified import
  loop.
- A machine cannot import another machine's qualified address.
- Renaming a session stops both old loops before starting the new local and
  qualified routes.

## Failure behavior

- Missing `MAILBOX_REMOTE_ROOT` rejects a qualified send before publication.
- Remote publication failure leaves the local outbox retryable.
- Existing remote destinations are accepted only when their bytes match the
  local immutable source; a conflicting file is reported and retained for
  investigation.
- Missing or changing attachments are not imported.
- A failed wakeup never removes or acknowledges local or remote mail.
- Duplicate import attempts are suppressed by local import markers and by
  checking both local `pending/` and `delivered/`.
- Two fresh local sessions with the same name still fail closed in
  session-inbox target resolution.

## Hard invariants

1. Unqualified mail never reads or writes `MAILBOX_REMOTE_ROOT`.
2. Qualified mail is staged locally before remote publication.
3. Shared transport files are immutable after publication.
4. Remote import creates an ordinary unqualified local envelope.
5. Local read and acknowledgement APIs reject qualified addresses.
6. Acknowledgement never moves or deletes remote transport files.
7. Remote publication and receipt failures preserve a local retry item.
8. Locks, claims, notification markers, import markers, and session-inbox state
   never live in OneDrive.
9. Machine qualification never enters local session identity.
10. There is no implicit broadcast.

## Configuration

```sh
MAILBOX_LOCAL_ROOT="$HOME/.copilot/mailbox"
MAILBOX_REMOTE_ROOT="/path/to/OneDrive/copilot-mailbox"
MAILBOX_STATE_ROOT="$HOME/.copilot/mailbox-state"
COPILOT_AGENT_MACHINE="surface-pro"
```

`MAILBOX_REMOTE_ROOT` and `COPILOT_AGENT_MACHINE` are optional when only local
delivery is needed.

## Acceptance criteria

1. An unqualified send, read, wakeup, and acknowledgement complete with the
   remote root absent or unavailable.
2. A qualified send publishes attachments and one envelope under the full
   qualified address and does not wake a same-name session on another machine.
3. A matching watcher imports the qualified envelope exactly once into the
   unqualified local mailbox.
4. Local acknowledgement leaves the remote envelope and attachments
   byte-for-byte unchanged and publishes a separate receipt.
5. Taking the remote root offline leaves the staged envelope usable and a later
   flush publishes it without creating a second envelope.
6. A watcher configured for one machine never imports another machine's route.
7. Extension reload and session rename leave one lock per active local or
   qualified route.
8. Existing session-inbox immediate-delivery, retry, ownership, and privacy
   tests continue to pass.

## Deliberate limits

This is one-shot durable delivery, not a chat or distributed queue service.
Remote transport files accumulate until a separate retention policy removes
old records. Fan-out, thread tracking, recipient discovery, and remote receipt
consumption are not part of this change. A future fan-out feature must create
one qualified immutable envelope per destination rather than restoring a
shared mutable broadcast mailbox.
