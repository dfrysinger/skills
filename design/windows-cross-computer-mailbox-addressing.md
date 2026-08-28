# Windows Cross-Computer Mailbox Addressing and Validation

## Objective

Validate the shipped Node mailbox on real Windows and add explicit `<agent>@<machine>` shared-mailbox addresses while preserving intentional unqualified broadcast behavior and the ordinary local Copilot session name.

## Non-goals

- Do not build a PowerShell mailbox engine or duplicate envelope parsing, publication, polling, target resolution, notification, or acknowledgement outside the existing Node implementation.
- Do not add shared machine discovery, hostname discovery, a shared liveness registry, distributed locks, recipient election, or per-machine broadcast acknowledgement state.
- Do not place `MAILBOX_STATE_ROOT` or `COPILOT_SESSION_INBOX_DIR` in OneDrive.
- Do not retune the 500 ms session-inbox request loop or two-second mailbox watcher loop.
- Do not rename a Copilot session to a qualified address; the local session remains `hotel`.
- Do not put machine identity into session-inbox instance records, request directories, or target resolution.
- Do not change macOS tmux identity preference or Claude/Codex fallback behavior.
- Do not promise durable delivery of one unqualified broadcast to computers that are offline or start after another recipient acknowledges it. Broadcast is for currently live matching watchers; qualified addressing is the durable one-computer path.
- Do not add a launcher, service, or Task Scheduler job unless installed-extension proof shows the packaged watcher cannot own startup, reload, shutdown, and single-owner behavior.

## Lane

**Critical.** The shared address and acknowledgement path can misroute, duplicate, or lose message and attachment delivery.

## Product contract

### Unqualified broadcast address

`hotel` uses the existing shared mailbox:

```text
$MAILBOX_ROOT/hotel/
```

Every currently live computer whose local Copilot session is named `hotel` watches this mailbox. Each may enqueue the envelope once on its own machine. The first acknowledgement still moves the single shared envelope to `delivered/`, so this is intentionally live broadcast-capable rather than durable per-machine fan-out.

### Qualified machine address

`hotel@thinkpad` uses a separate shared mailbox:

```text
$MAILBOX_ROOT/hotel@thinkpad/
```

Only the watcher whose configured machine name is `thinkpad` watches it. After accepting an envelope from that directory, the watcher publishes a machine-local session-inbox request targeting the ordinary session name `hotel`.

A qualified send performs an immediate sender-local wakeup only when the sender's configured `COPILOT_AGENT_MACHINE` exactly matches the qualified machine. Otherwise publication succeeds durably, the CLI reports that wakeup is deferred to the target machine's watcher, and it must not submit a request to a same-name session on the sending computer.

The configured machine name comes only from:

```text
COPILOT_AGENT_MACHINE=thinkpad
```

There is no automatic hostname fallback. Machine names must be stable and unique within one shared `MAILBOX_ROOT`.

### Address grammar

An address is either:

```text
<agent>
<agent>@<machine>
```

Allow exactly zero or one `@`. Validate each component independently with the existing safe-name rule. Reject empty components, additional `@` characters, whitespace, path separators, and any other character the existing rule rejects. The full address remains the envelope recipient string and shared directory key.

## Rollback

Rollback by reverting the addressing commit and reinstalling the last known-good plugin release.

- Existing unqualified `hotel` mail remains compatible.
- Old watchers do not watch `hotel@thinkpad`, so qualified envelopes remain safely pending rather than being consumed by the wrong machine.
- Before rollback, pause qualified sends. After rollback, retain qualified pending directories untouched until the addressing release is restored, or manually re-send their envelopes to a supported unqualified address after confirming that broadcast behavior is acceptable.
- No envelope schema or directory migration is required.

## Fail-closed evidence

- A malformed address is rejected before publication.
- A Windows watcher without `COPILOT_AGENT_MACHINE` watches only the unqualified mailbox.
- A watcher configured as `thinkpad` never scans or acknowledges `hotel@macbook-pro`.
- An unknown qualified address remains pending until a matching configured machine appears.
- Zero or multiple fresh local `hotel` sessions produce no session-inbox request.
- Incomplete or changing attachments produce no request, acknowledgement, move, or poison state.
- A locked attachment remains pending until bounded retry succeeds or reports a terminal error without loss.
- Diagnostics omit summaries, message bodies, prompt content, and attachment contents.

## Constraint provenance

| Constraint | Provenance and binding evidence | Protected outcome | Revisit condition |
| --- | --- | --- | --- |
| Full qualified address is the shared directory and envelope recipient string. | Explicit updated handoff decision; preserves the existing string and directory layout. | Old watchers ignore qualified mail safely and no envelope schema migration is needed. | A supported transport cannot sync directories containing `@`. |
| Machine identity is configured through `COPILOT_AGENT_MACHINE`; no hostname discovery. | Explicit updated handoff decision and user-selected `hotel@surface-pro` product syntax. | Stable human-selected routing that does not silently change after OS rename or imaging. | The Windows launcher cannot supply stable environment configuration, or an existing authoritative machine identity becomes available. |
| Watcher observes both `<agent>` and `<agent>@<machine>`. | Explicit updated handoff architecture. | Preserve broadcast and add deterministic one-computer routing. | Two concurrent watcher loops cannot share lifecycle safely or create excessive duplicate work. |
| Qualified mail maps to local target `<agent>`. | Session-inbox resolves only local live Copilot session names; the handoff forbids qualified local identity. | Machine qualification stays in shared storage and local ambiguity remains fail closed. | Session-inbox gains a supported first-class routing identity separate from session name. |
| Notification markers and locks use the full mailbox address. | Existing local dedupe/lock owners plus updated handoff requirement. | Broadcast and qualified envelopes cannot suppress or lock each other. | Measured evidence shows one process must own both addresses atomically. |
| Unqualified broadcast is limited to currently live watchers. | Existing single shared acknowledgement move and explicit decision to preserve broadcast without adding per-recipient state. | Avoid claiming durable fan-out the architecture cannot provide. | A supported caller requires guaranteed delivery to offline or late-starting broadcast recipients. |
| Fresh instance age remains 15 seconds; watcher loop two seconds; request loop 500 ms; attachment gate two stable scans; rename retry ten times at 200 ms. | Shipped compatibility defaults, with existing tests and macOS receipts; no Windows evidence currently implicates them. | Preserve proven behavior while measuring Windows. | Windows traces show a limit directly violates an acceptance criterion. |

No new hard numeric limit is introduced.

## Reframe gate

Return to this design before adding a shared registry, service, scheduled task, schema migration, third storage plane, automatic hostname identity, or per-machine broadcast acknowledgement.

Reframe also fires when repeated fixes merely move failure between the two shared mailboxes, local watcher ownership, local name resolution, and SDK queue delivery without completing the user-visible route.

### Closed reframe record: envelope field versus mailbox address

1. **Blocked outcome:** deterministic one-computer delivery when the same agent name exists on multiple computers.
2. **Constraint and provenance:** the updated handoff explicitly requires `hotel@thinkpad` to remain the shared recipient string and directory and requires configured `COPILOT_AGENT_MACHINE`.
3. **Invariant at risk:** putting machine identity inside the envelope while storing it under `hotel/` lets old watchers consume qualified mail and does not preserve the requested shared-address contract.
4. **Simplest design without the rejected mechanism:** validate the full address, store it under the full address directory, and have the configured watcher map it back to local target `hotel`.
5. **Fewer trusted components:** the address-directory design reuses the envelope schema, mailbox functions, watcher, local session resolver, and acknowledgement path; the prior field design added mixed-version interpretation and filter logic inside every read.

**Durable reframe status: CLEAR.** The updated handoff is authoritative, the simpler address-directory design satisfies it using existing owners, and no revisit condition is currently met. Implementation begins only after this replacement work order passes design review.

## Reuse contract

Reuse:

- `mailbox-core.mjs` for publication, attachment readiness, per-address notification markers, per-address locks, acknowledgement, retries, and diagnostics;
- `mailbox.mjs` as the portable Windows CLI;
- `mailbox-watcher/extension.mjs` for joined-session identity and lifecycle;
- `session-identity.mjs` for tmux-first/macOS and `/rename` fallback identity;
- `request.mjs` for exactly-one fresh local session selection;
- `session-inbox/extension.mjs` for native SDK `enqueue`;
- the existing diagnostic logger and error shape.

New code is required only to validate/split a mailbox address, map a qualified address to its base local agent target, let one extension own two existing watcher loops, and let recipient CLI actions inspect both of its own addresses.

When the joined Copilot session identity changes, the extension stops both old watcher loops and releases both old full-address locks before deriving the new pair. For example, renaming `hotel` to `india` changes ownership from `hotel` plus `hotel@thinkpad` to `india` plus `india@thinkpad`. A qualified watcher always targets the base component of the full address it watches. Pending mail for the old qualified address remains safely pending; it is never redirected into the renamed session.

## Data flow

1. Sender runs `mailbox.mjs send hotel@thinkpad`.
2. The CLI validates `hotel` and `thinkpad` independently and preserves `hotel@thinkpad` as the recipient.
3. `mailbox-core.mjs` publishes attachments and JSON under `$MAILBOX_ROOT/hotel@thinkpad/pending/`.
4. If the sender is not configured as `thinkpad`, the CLI suppresses sender-local wakeup and reports that the target machine's watcher owns delivery. If it is configured as `thinkpad`, the immediate local wakeup targets the base session name `hotel`.
5. The ThinkPad extension obtains local session name `hotel` and configured machine `thinkpad`.
6. The extension owns watcher loops for `hotel` and `hotel@thinkpad`; another machine such as `macbook-pro` owns `hotel` and `hotel@macbook-pro`.
7. The qualified watcher calls the existing mailbox polling path with shared address `hotel@thinkpad` and local target `hotel`.
8. Attachment stability and the full-address local `.notified` marker gate notification.
9. `request.mjs --target-name hotel` resolves exactly one fresh local session generation.
10. Session-inbox submits SDK mode `enqueue`; the native event is `idle` or `queued`, never `steering`.
11. Recipient CLI `check`, `read`, and `ack` inspect `hotel` and, when configured, `hotel@thinkpad`.
12. Acknowledgement moves the selected address's JSON and attachment directory to that address's `delivered/`.

## Realistic failure model

- `COPILOT_AGENT_MACHINE` is absent, malformed, duplicated on two computers, or changes between runs.
- The extension starts one watcher but not the other, or leaves one lock after reload.
- The joined session is renamed while both watcher loops are active; stale loops or locks must not survive, and pending mail under the old address must not be redirected to the new session.
- Qualified polling accidentally targets local session `hotel@thinkpad` instead of `hotel`.
- A qualified send to another machine accidentally wakes a same-name session on the sender's computer.
- Marker or lock paths use only the base agent and cause broadcast/qualified interference.
- Recipient CLI sees the wakeup but checks only `hotel/`, leaving qualified mail unread.
- The same envelope ID exists in both addresses and `read` or `ack` chooses arbitrarily.
- One broadcast recipient acknowledges before another live recipient scans; the later recipient misses that broadcast under the documented live-only semantics.
- OneDrive delays or rewrites attachment metadata, resyncs an envelope, or holds a file during rename.
- Node is unavailable in the extension environment.
- Diagnostics serialize content or an error embeds it.

## Hard invariants

1. Shared mailbox addresses and envelope recipients use the same validated full string.
2. Machine qualification never enters session-inbox identity or target resolution.
3. One configured extension owns at most one watcher for each of its unqualified and qualified addresses.
4. Locks and notification markers are keyed by full mailbox address.
5. A qualified watcher targets the unqualified local Copilot session name.
6. A machine never scans, reads, acknowledges, or marks another machine's qualified address.
7. Recipient CLI actions cover both local addresses and fail on an envelope ID ambiguous across them.
8. A joined-session rename replaces both watcher loops and their locks as one lifecycle transition; an old qualified address is never mapped to the new local identity.
9. A qualified remote send never submits a sender-local SDK request to a same-name session on a nonmatching or unconfigured machine.
10. Ordinary wakeups enter SDK mode `enqueue` and are observed only as `idle` or `queued`.
11. Failed wakeup never removes or acknowledges an envelope.
12. Attachment publication, stability gating, acknowledgement pairing, retries, and diagnostics privacy retain their existing contracts.

## Acceptance criteria

1. The exact worktree plugin loads both extensions on Windows and records one fresh `/rename hotel` instance.
2. A configured `thinkpad` extension owns `hotel` and `hotel@thinkpad` watcher locks, and no other qualified watcher; renaming the joined session replaces both locks with the new unqualified and qualified pair.
3. Local unqualified mail produces one idle/queued native turn, is read, and moves to `delivered/`.
4. `hotel@thinkpad` wakes only the Windows `hotel`; `hotel@macbook-pro` wakes only the MacBook Pro `hotel`; an unknown qualified address remains pending.
5. One unqualified `hotel` envelope is observed to wake both concurrently live test computers once each while acknowledgement is withheld until both notification markers and native turns are recorded. A trial in which either recipient acknowledges before both observations is invalid and must be repeated; it is not a contract failure.
6. Two fresh local `hotel` sessions fail closed rather than selecting one.
7. Recipient check/read/ack finds mail in both local addresses and rejects an ID present in both.
8. OneDrive offline recovery, watcher restart before acknowledgement, and resync/touch produce one SDK turn on the intended machine.
9. JSON-before-attachment and a changed attachment produce no request until two stable scans.
10. A Windows-held attachment recovers through bounded rename retry without loss.
11. Diagnostics contain operational metadata and no content canaries.
12. No PowerShell mailbox logic, second service, or Task Scheduler architecture is introduced.

## Deterministic check contract

| Check | Setup and transition | Pass signal | Failure meaning |
| --- | --- | --- | --- |
| Address parser tests | Valid unqualified/qualified and malformed addresses | Exact preserved address; components validate independently; malformed input rejects before write | Shared path or local target can be ambiguous or unsafe. |
| Qualified publication test | Send `hotel@thinkpad` with attachment | JSON and attachment exist only under `hotel@thinkpad/pending/` and envelope recipient is unchanged | Schema/layout contract was replaced rather than extended. |
| Dual watcher lifecycle test | Session `hotel`, machine `thinkpad`, start/reload, rename to `india`, then stop extension | Exactly `hotel.lock` and `hotel@thinkpad.lock` before rename; exactly `india.lock` and `india@thinkpad.lock` after rename; old locks are released; both stop and restart cleanly | Packaged extension cannot own both routes or can redirect old qualified mail after an identity change. |
| Target mapping test | Qualified watcher sees complete mail | Session-inbox request uses `--target-name hotel` and dedupe key includes full address | Qualification leaked into local identity or routes collide. |
| Qualified sender wakeup test | A computer with local session `hotel` sends `hotel@thinkpad` while its machine is different or unconfigured, then while configured as `thinkpad` | Remote case publishes with no local request and reports deferred wakeup; matching-local case targets only local `hotel` | A same-name session can be woken on the wrong computer. |
| Recipient aggregate test | Place unique and duplicate IDs across both local addresses | check lists both; read/ack selects unique address; duplicate ID refuses | Agent can miss or arbitrarily consume mail. |
| Broadcast/qualified marker test | Same envelope IDs across address directories | Independent markers under full addresses | One route suppresses another. |
| Existing mailbox/session-inbox suites | Run Node tests on Windows | All portable tests pass; tmux-only tests skip explicitly | Existing behavior regressed. |
| Windows lock probe | Hold attachment during acknowledgement, release it | Both JSON and attachment move once | Retry or pair integrity failed. |
| Attachment live receipt | JSON first, missing/changed attachment, then stable | No request until second identical scan; one later turn | Partial attachment can reach the agent. |
| OneDrive restart receipt | Publish offline, sync, restart watcher before ack, touch/resync | One intended-machine turn and delivered envelope | Offline durability or dedupe failed. |
| Two-computer receipt | Windows thinkpad and Mac machine share `hotel`; for broadcast, withhold acknowledgement until both notification markers and native turns are recorded | Qualified routes isolate; controlled unqualified test wakes both once; unknown target remains pending. An early acknowledgement invalidates the broadcast trial rather than failing it. | Cross-computer contract failed under the controlled live-watcher setup. |
| Diagnostics scan | Unique summary/body/attachment canaries across success/failure | Operational events exist; no canary match | Diagnostics retain mailbox content. |

No pre-implementation architecture grep guard is required.

## Migration

No envelope schema migration exists. Qualified addresses create new sibling mailbox directories. Existing `hotel/` directories and envelopes remain unchanged.

Set `COPILOT_AGENT_MACHINE` on each computer before sending qualified mail. Rollout may occur one computer at a time because old watchers ignore qualified directories safely. An unknown or not-yet-upgraded target leaves its qualified mail pending.

## Current baton

- **Phase:** frozen-candidate cross-computer proof.
- **Branch:** `dfrysinger/windows-mailbox-validation`.
- **Critical path:** review this replacement design; remove the superseded `to.machine` implementation; implement address validation, dual watchers, target mapping, aggregate recipient actions, and full-address local state; run deterministic Windows tests; rerun all affected live claims; dual-review implementation; final two-computer campaign; land.
- **Current candidate evidence:** Windows exact-worktree proof observed both `hotel` and `hotel@surface-pro` watcher ownership, one qualified native `queued` turn mapped to local `hotel`, acknowledgement, unknown-qualified persistence, OneDrive-backed offline start and restart/resync dedupe, attachment stability gating, held-file rename recovery, and diagnostics exclusion. A controlled two-process Windows campaign observed one unqualified envelope once in each independent native session while acknowledgement was withheld. These runs are diagnostic until repeated on the final clean reviewed commit; the required physical Mac/Windows campaign remains open.
- **Open proof claims:** `windows-extension-load`, `windows-local-delivery`, `qualified-machine-routing`, `broadcast-two-computer-delivery`, `onedrive-offline-dedupe`, `windows-attachment-gating`, `windows-file-lock-recovery`, and `diagnostics-content-exclusion`.
- **Reframe status:** `CLEAR`; replacement design passed bounded Claude Opus and GPT review with no material finding.

## Definition of Done — Windows Addressed Mailbox

- This replacement design passes bounded dual review with no material finding.
- The installed/worktree Windows plugin owns the unqualified and configured qualified watchers for one ordinary `/rename` identity.
- All changed deterministic mailbox and session-inbox tests pass on Windows.
- Final validated receipts on one frozen reviewed fingerprint cover extension lifecycle, unqualified delivery, qualified isolation and unknown-target persistence, live broadcast on two computers, local ambiguity refusal, OneDrive offline/restart dedupe, attachment gating, lock recovery, acknowledgement, and diagnostics privacy.
- Mac and Windows sessions both named `hotel` prove `hotel@thinkpad`, the configured Mac qualified address, and unqualified `hotel` end to end.
- No PowerShell mailbox engine, shared registry, hostname discovery, second service, or speculative polling architecture is introduced.
- Implementation dual review has no verified in-scope must-fix finding.
- The final diff is committed, pushed to the owned branch, and opened as a pull request with proof evidence.
