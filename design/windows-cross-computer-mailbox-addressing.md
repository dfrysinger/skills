# Local-First Cross-Computer Mailbox

## Objective

Deliver messages between named agent sessions on one computer or across
computers without putting mutable mailbox state, locks, or acknowledgements in
a cloud-synced directory.

## Non-goals

- Do not infer a machine label from a hostname, operating-system account, or
  cloud-provider metadata.
- Do not move local mailbox, watcher, session-inbox, or acknowledgement state
  into OneDrive.
- Do not add broadcast, recipient discovery, reply threads, or a distributed
  lock service.
- Do not require every Copilot process restart to inherit shell environment
  variables after the machine has been configured once.

## Lane

**Systemic.** Machine identity and the remote transport root determine which
cross-computer route a watcher owns. Their persistent configuration is shared
by the portable CLI and watcher extension across process restarts.

## Constraint provenance and reframe gate

| Constraint | Provenance | Protects | Revisit condition |
| --- | --- | --- | --- |
| Machine identity is explicit and stable. | User-selected mailbox address contract. | Prevents one computer from importing another computer's route. | Revisit only if a repository-independent machine identity authority exists. |
| Mutable delivery state remains local. | Prior OneDrive lock and corruption experience plus the local-first product contract. | Prevents cloud-file conflicts from corrupting claims, acknowledgements, and retries. | Revisit only if the remote transport is replaced by a transactional service. |
| Process environment overrides persisted configuration. | Existing launch-time configuration and test isolation behavior. | Allows explicit per-process testing and emergency overrides without editing durable state. | Revisit if configuration gains profiles or a supported runtime settings API. |
| Persistent routing configuration is machine-local and independent of a Copilot session profile. | Machine qualification belongs to the physical computer, while session identity remains the agent name and exact Copilot session ID. | A direct restart resolves the same machine route even when its shell environment differs from the setup shell. | Revisit if one physical computer must participate under multiple mailbox machine identities. |
| Invalid persistent configuration fails closed. | Routing integrity requirement. | Prevents malformed or partial config from silently degrading a cross-computer watcher to local-only delivery. | Revisit only if the UI can surface and repair invalid configuration before watcher startup. |

**Reframe status: CLEAR.** The observed failure was a direct Copilot resume
whose process did not inherit the shell exports used during initial setup. A
small local configuration file reused by the existing mailbox state owner
survives that boundary without adding a daemon, remote registry, or mutable
cloud state.

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

## Configuration authority

The mailbox reads optional persistent configuration from
`~/.copilot/mailbox-config.json`. `MAILBOX_CONFIG_PATH` may select a different
local file. The file is versioned and contains only the physical machine's
cross-computer routing configuration:

```json
{
  "schemaVersion": 1,
  "machineName": "surface-pro",
  "remoteMailboxRoot": "C:\\Users\\me\\OneDrive\\copilot-mailbox"
}
```

`machineName` and `remoteMailboxRoot` are both required. Local mailbox and state
roots retain their existing environment/default resolution and are deliberately
not persisted here, so this file cannot redirect mutable state into OneDrive.
Explicit constructor options override environment variables; environment
variables override the persistent file; the persistent file overrides the
local-only default. A present file with an unsupported schema, unknown field,
malformed value, relative remote root, or incomplete pair is an error rather
than a local-only fallback. An explicitly set `MAILBOX_CONFIG_PATH` that is
missing, unreadable, or not a regular file is also an error; only absence of the
default path means the machine is intentionally local-only.

After environment/file precedence is resolved, the remote transport root must
be path-disjoint from the resolved local mailbox and state roots: none may be
equal to, contain, or be contained by another. Comparison follows the host
platform's path and case semantics. A collision is an invalid configuration and
is rejected before any directory, watcher route, or state file is created.

`mailbox.mjs configure` writes the file atomically with user-only permissions.
It prints the absolute path written. The file stays local and is never copied
into `MAILBOX_REMOTE_ROOT`.

The portable CLI and watcher extension call the same mailbox-core configuration
resolver. Configuration parse and validation failures have a distinct error
type. The watcher records `watcher.configuration_invalid` in the existing
default or environment-selected local state root, then its extension bootstrap
process exits non-zero without starting either local or qualified routes. The
hosting Copilot session remains running. It does not reuse the prior
machine-error fallback that silently reconstructed a local-only watcher. A
standalone `mailbox.mjs watch` process likewise exits non-zero.

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
delivery is needed. They may be supplied on every launch as before, or persisted
once:

```sh
node skills/mailbox/scripts/mailbox.mjs configure \
  --machine surface-pro \
  --remote-root "/path/to/OneDrive/copilot-mailbox"
```

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
9. After one persistent configuration write, a Copilot process started without
   mailbox environment variables watches both the local and qualified routes.
10. Environment variables override persistent configuration for an explicitly
    configured process.
11. Invalid or partial persistent configuration stops qualified watcher startup
    with a diagnostic instead of silently watching only the local route.

## Check contract

- A mailbox-core test writes a valid versioned config, clears mailbox
  environment variables, and asserts that the resulting watcher addresses
  include the qualified route. Failure proves process restart lost durable
  routing authority.
- A precedence test supplies conflicting file and environment values and
  asserts that the environment wins. Failure proves the documented emergency
  override no longer works.
- Schema tests reject unknown fields, unsupported versions, malformed names,
  relative roots, an incomplete machine/root pair, and an explicitly selected
  missing config path. They also reject equality and ancestor/descendant
  overlap between the resolved remote, local mailbox, and local state roots
  using the host platform's path semantics. Failure proves invalid routing or
  mutable-state placement can silently enter the watcher.
- A CLI test runs `configure`, verifies the exact persisted values and
  user-only file mode, then starts a fresh process without mailbox environment
  variables and observes the qualified route.
- A watcher-bootstrap test supplies invalid persistent configuration alongside
  otherwise valid environment values and asserts one
  `watcher.configuration_invalid` diagnostic, no `watcher.addresses_started`,
  and non-zero watcher-extension bootstrap exit while the Copilot host remains
  alive. Failure proves the old swallow-and-degrade path remains or the
  refusal's blast radius is too broad.
- The existing attached-envelope watcher test remains the import contract: the
  first stable observation waits, the second imports exactly once, and local
  acknowledgement leaves the remote bytes unchanged.

## Definition of Done: persistent cross-computer mailbox configuration

- The portable CLI and watcher extension use the same versioned local
  configuration authority.
- Direct Copilot restart without inherited mailbox exports retains the
  configured qualified watcher route.
- Invalid configuration fails closed with actionable diagnostics.
- Existing environment-only setups and local-only mailboxes remain compatible.
- A real qualified envelope with attachments imports, wakes, and is
  acknowledged after restarting the recipient without mailbox environment
  variables.

## Deliberate limits

This is one-shot durable delivery, not a chat or distributed queue service.
Remote transport files accumulate until a separate retention policy removes
old records. Fan-out, thread tracking, recipient discovery, and remote receipt
consumption are not part of this change. A future fan-out feature must create
one qualified immutable envelope per destination rather than restoring a
shared mutable broadcast mailbox.
