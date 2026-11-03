# Provider-Native Cross-Client Mailbox

## Status

**Proposal revision:** `provider-native-cross-client-mailbox-design-v6-reviewed`
**Lane:** Critical
**Evidence packet:** [`provider-native-cross-client-mailbox-evidence-v1`](provider-native-cross-client-mailbox-evidence.md)
**Decision record:** [`provider-native-cross-client-mailbox-decisions-v2`](provider-native-cross-client-mailbox-decisions.json)
**Independent challenge:** [`provider-native-cross-client-mailbox-constraint-challenge.md`](provider-native-cross-client-mailbox-constraint-challenge.md)
**Dual design review:** [`provider-native-cross-client-mailbox-design-review.md`](provider-native-cross-client-mailbox-design-review.md)
**Design status:** Approved; implementation active under development-loop.

```yaml
design_incubation:
  status: approved
  cycle: 1
  objective_file: C:\Users\dfrysinger\code\skills-provider-mailbox\design\provider-native-cross-client-mailbox-design-objective.txt
  reminder:
    kind: design_progress
    id: 3
    interval: 30m
    status: stopped
```

## Objective

Let named Copilot, Claude, and Codex Agent Stack sessions exchange durable
provider-qualified mail and wake the exact live local session immediately
through authenticated provider-native control on Windows and macOS.

## Non-goals

- Do not send mailbox envelope contents through provider control channels. The
  channel carries only a fixed `check mailbox; skip if empty <marker>` prompt.
- Do not add broadcast, recipient discovery, group mail, shared conversation
  history, or provider-to-provider context transfer.
- Do not use tmux keystrokes, Windows console injection, focus changes, UI
  automation, or screen parsing as a fallback.
- Do not use Claude Remote Control or Anthropic servers for same-machine
  mailbox delivery.
- Do not expose a Codex app-server beyond the local machine.
- Do not manage or automate protected provider login, passwords, SSO, MFA, or
  device approval.
- Do not restart, upgrade, attach to, or claim ownership of a Claude or Codex
  process that Agent Stack did not launch.
- Do not add automatic provider upgrade or restart in this change. Return
  machine-readable upgrade or managed-relaunch guidance. The user's grant for
  a future autopilot repair flow remains recorded but is not required for the
  first working cross-client mailbox.
- Do not make the mailbox core a package manager or process supervisor.
- Do not redesign immutable OneDrive transport or move mutable state into it.
- Do not create a shared cross-provider conversation schema. Provider
  conversations remain provider-owned.

## User result

The user can address three local sessions with the same name:

```text
copilot:alpha
claude:alpha
codex:alpha
```

The user can add `@machine` only for cross-computer transport:

```text
codex:alpha@surface-pro
```

The sender first writes a durable envelope. A live supported local target then
receives a fixed mailbox prompt through its provider's native control channel.
The sender reports `verified`, `submitted`, `deferred`, `held`, `refused`, or
`ambiguous` according to what the provider can prove, instead of turning every
successful file write into a delivery claim.

Existing bare addresses such as `alpha` remain aliases for `copilot:alpha`.
They do not become broadcasts.

## Caller and authority

The trusted owners are deterministic mailbox code for envelope storage and
routing, and deterministic Agent Stack launcher code for provider process
ownership, provider version checks, and managed provider launch.

An agent in normal or autopilot mode may ask these owners to perform an
operation. The mailbox message text, receiving model, and provider process do
not gain authority to change identity, upgrade software, restart another
session, bypass inbound controls, or acknowledge mail.

The user permitted a future autopilot upgrade and restart flow, with idle and
Agent Stack ownership conditions. This work does not exercise that grant.
No incoming mailbox message can create or expand it.

## Lane and fail-closed boundary

**Critical.** This change handles per-session authentication tokens, local
control endpoints, and exact-session authorization.

The boundary fails closed when any of these facts cannot be proved:

- provider and agent name;
- local versus remote route;
- provider endpoint authentication;
- provider conversation or thread identity;
- idle or active-turn state for provider delivery;
- exact active turn for steering;
- supported provider capability;
- supported launch mode.

Fail-closed evidence is a pending envelope plus a structured outcome that
names the unproved fact. No control request or acknowledgement occurs
after that failure.

## Constraint provenance

| Constraint | Provenance | Protects | Revisit condition |
| --- | --- | --- | --- |
| Local identity is `provider:name`; `@machine` selects remote transport. | Exact top-level user decision and existing local-first transport contract. | Prevents provider identity from forcing unnecessary OneDrive routing. | Revisit only through a new address-contract decision and migration. |
| Live supported targets wake immediately. | Exact top-level user decision. | Preserves the practical cross-client behavior the user asked for. | Revisit only if a provider removes all supported live-control paths. |
| Unsupported native control stays queued and recommends upgrade. | Exact top-level user decision. | Prevents unverified terminal input from masquerading as delivery. | Revisit only through an explicit fallback decision. |
| Existing bare names mean Copilot. | Existing mailbox and Copilot watcher compatibility. | Avoids breaking current senders and mailbox directories. | Revisit after measured usage and an explicit migration plan. |
| The envelope remains the durable source of truth. | Existing mailbox architecture. | Wakeup loss cannot lose the message. | Revisit only if mailbox persistence is replaced as a separate project. |
| Mutable state stays local; remote files remain immutable. | Existing reviewed OneDrive transport design. | Prevents shared-filesystem locking and acknowledgement corruption. | Revisit only if remote transport becomes transactional. |
| Provider control carries only a fixed wakeup prompt. | Least privilege and existing Copilot mailbox behavior. | Provider channels never become a second mailbox or leak attachments. | Revisit only if a provider requires a structured opaque notification. |
| Claude control uses its documented per-session socket or named pipe and inbound controls. | Official Claude Code behavior. | Uses the provider's authentication, ownership, and permission boundary. | Revisit if the provider removes hook access or own-session posting. |
| Codex TUI and control use one Agent Stack-managed app-server. | Official Codex remote TUI and turn APIs; queue alone is not immediate. | Gives the sender a reachable exact live thread without terminal injection. | Revisit if Codex exposes a simpler supported exact-session control API. |
| Automatic upgrade/restart is deferred; this change returns upgrade or managed-relaunch guidance. | Constraint challenge found the user statement tactical and permissive, while upgrade guidance already satisfies the required unavailable-control outcome. | Keeps package management, idle-input proof, and restart supervision off the critical delivery path. | Revisit in a separate work order using the recorded idle and Agent Stack ownership grant. |
| Protected login remains manual. | Existing user autonomy boundary and credential policy. | Keeps secrets and protected identity actions outside agent control. | Revisit only for provider-supported non-secret synthetic test accounts. |

Claude's minimum documented versions are 2.1.224 on macOS/Linux and 2.1.234
on native Windows. Other capability checks use feature detection and the
installed provider's generated schema rather than a hard-coded Codex version.

## Reframe gate

Implementation stops before adding another component when:

- Claude cannot run an authenticated own-session mailbox watcher from a
  supported hook without persisting its token.
- Codex cannot attach its normal TUI and a control client to one local managed
  app-server while preserving exact resume.
- Codex immediate control requires an unauthenticated non-loopback listener.
- exact provider thread identity cannot be proved without parsing conversation
  content;
- a provider-native accepted response cannot be distinguished from held,
  refused, deferred, or ambiguous delivery;
- provider version drift requires a second protocol implementation rather than
  using documented or generated schemas.

For any trigger, record:

1. the blocked user-visible outcome;
2. the originating constraint;
3. the invariant that would fail if changed;
4. the simplest design without that constraint; and
5. the option with fewer trusted components and maintenance surfaces.

**Reframe status: `CLEAR`.** Official Claude documentation supplies an
authenticated own-session socket path to hooks and starts a turn when an idle
session accepts a message. Official Codex documentation supplies local remote
TUI attachment, authenticated loopback transport, generated version-matched
schemas, runtime thread state, `turn/start`, and `turn/steer`. The remaining
wire and lifecycle details are bounded pre-implementation mechanism probes,
not reasons to add terminal injection.

## Reuse contract

The change extends existing owners instead of creating a second messaging
system:

- `mailbox-core.mjs` remains the only owner of address parsing, envelope
  persistence, remote publication/import, read, and acknowledgement.
- session-inbox remains the Copilot live-control adapter.
- the mailbox state root remains the owner of watcher locks, notification
  attempts, existing `.notified` and `.unverified` markers, and diagnostics.
- Agent Stack remains the owner of provider process launch, isolated
  workspaces, one-live-session protection, provider version checks, and exact
  resume.
- Claude remains the owner of socket authentication, inbound controls,
  permissions, and conversation state.
- Codex app-server remains the owner of thread and turn state.

New provider adapters are required because Copilot's SDK cannot control Claude
or Codex, Claude's token exists only inside its session environment, and an
embedded Codex TUI has no reachable supported control endpoint.

## Address and envelope contract

The canonical grammar is:

```text
[PROVIDER:]NAME[@MACHINE]
```

`PROVIDER` is exactly `copilot`, `claude`, or `codex`. `NAME` and `MACHINE`
retain the existing safe-name grammar. A missing provider means `copilot`.
Logical addresses are not used directly as Windows path segments. One shared
path-key helper maps mailbox directories and every address-keyed state path,
including watcher locks, notification claims, notified markers, unverified
markers, watermarks, and remote import markers:

```text
copilot:alpha           -> alpha
copilot:alpha@surface   -> alpha@surface
claude:alpha            -> _providers/claude/alpha
claude:alpha@surface    -> _providers/claude/alpha@surface
codex:alpha             -> _providers/codex/alpha
codex:alpha@surface     -> _providers/codex/alpha@surface
```

This preserves existing Copilot directories and uses only the existing safe
name grammar in each path segment. Envelope identity remains the logical
provider-qualified address.

New envelopes store:

```json
{
  "to": {
    "address": "codex:alpha",
    "provider": "codex",
    "name": "alpha"
  }
}
```

Remote envelopes also include `machine`. Readers accept existing bare
Copilot envelopes and normalize them in memory. They do not rewrite old
delivered records.

## Receiver self-identity

Every Agent Stack-owned provider process receives one canonical
`MAILBOX_SELF_ADDRESS`:

```text
copilot:alpha
claude:alpha
codex:alpha
```

Mailbox self-resolution prefers this value for check, read, acknowledge, send,
reply, watch, and sender identity. It validates and canonicalizes the value
through the same address parser. A non-Copilot Agent Stack session without a
valid provider-qualified self address fails closed; it never falls back to a
bare name. Existing Copilot callers without the variable retain their current
bare-name resolution.

The fixed wakeup prompt does not need to carry the address because the
receiving provider process already has its exact self identity. This also makes
replies from `claude:alpha` and `codex:alpha` provider-qualified instead of
silently becoming mail from Copilot Alpha.

## Session-bound watchers

Copilot continues to use session-inbox's existing instance and notification
state.

Claude and Codex each run one mailbox watcher as a child of the exact owning
session. The child owns the native provider credential in memory and reuses
`mailbox-core`'s existing `watch()` loop, watcher lock, notification claim,
`.notified` markers, and `.unverified` markers. The sender never connects to
Claude or Codex directly. It writes the envelope, waits briefly for the
existing marker state, and otherwise reports deferred.

The child exits when its owning launcher or provider process is gone. No
endpoint registry, heartbeat store, PID tuple, new receipt store, or durable
provider token is added.

Existing `.notified` marker content stays compatible and continues to mean
verified delivery. Existing `.unverified` markers evolve from a legacy
attempt-ID string to a versioned payload containing `attemptId`, `outcome`,
provider detail, and update time. `submitted`, `held`, `refused`, and
`ambiguous` use that marker and suppress automatic replay. `deferred` writes no
marker because it proves no provider side effect and may retry on a later
watcher poll. The sender reads and reports the recorded outcome without
converting `submitted` into `verified`.

## Provider adapters

### Copilot

The mailbox dispatcher calls the existing session-inbox request client with
the fixed prompt, envelope-specific deduplication key, and timeout. Only its
existing `idle` or `steering` receipt is `verified`.

### Claude

Agent Stack starts Claude with a SessionStart hook that launches one
session-bound mailbox watcher as Claude's own child. The watcher inherits
`CLAUDE_CODE_MESSAGING_SOCKET` and
`CLAUDE_CODE_MESSAGING_TOKEN` in memory. It never writes the token.

The hook may run again on resume, clear, or compact. Its watcher identity uses
only a non-secret hash of the socket address. If that identity matches the live
lock owner, the new hook child exits and the existing watcher continues.

If the socket identity differs, the new watcher waits for the existing watcher
lock while its Claude parent remains alive. The old watcher keeps working when
its endpoint and credential remain valid. If a terminal endpoint error occurs
before any message byte is written—socket or pipe missing, connection refused,
or authentication rejected—the poll returns `deferred` without a marker,
releases the lock, and exits; the waiting watcher then acquires the same lock
and retries. The mechanism probe identifies any platform-specific transient
busy error that must remain deferred without exiting. This uses the existing
lock and adds no takeover file, second lock, or stored credential. A hook
re-fire therefore leaves one acting watcher and may leave one non-acting
waiter.

The watcher's parent-liveness check targets the long-lived Claude process, not
the short-lived hook process. After a hook re-fire, any terminal pre-write
endpoint loss or authentication rejection returns `deferred` without a marker
and exits. The waiting new watcher then acquires the existing lock.

The watcher claims `claude:<name>`, waits for a pending envelope, opens the
session's own socket or named pipe only when the fixed prompt is ready,
authenticates where required, and posts one complete message line. Claude
applies `crossSessionInbound` and its normal permission rules. An accepted idle
message starts a turn; an active session receives it between tool calls.

The Claude mechanism probe decides the runtime outcome vocabulary. If the
socket returns an authoritative accepted, held, or refused result, the watcher
passes it through. If a clean write has no authoritative reply, the watcher
records `submitted`, not `verified`. A failed write is `deferred`. A connection
failure after a partial or completed write is `ambiguous`, and the same attempt
identity is not replayed automatically.

### Codex

For each Agent Stack-owned Codex launch, Agent Stack creates one random token
in memory, starts one local app-server child, starts one mailbox watcher child,
and attaches the TUI to that app-server with `codex --remote`.
Per-session ownership is preferred over one machine-wide daemon because it
keeps lifecycle, workspace, and thread identity within one launcher.

On macOS, use the provider's local Unix-socket transport when supported. On
native Windows, use an authenticated loopback listener. The launcher passes
only the token hash to app-server with `--ws-token-sha256` and passes the raw
token to the TUI and watcher through private child environments. The token is
never written to disk or placed on a command line.

Agent Stack, as the sole TUI launch owner, starts the TUI with the
version-matched equivalent of:

```text
codex resume --last --cd <workspace> --remote <endpoint>
```

The bounded native probe must establish the exact supported argument order and
authentication form before Codex adapter code is written. The child watcher
only connects to the already-running app-server; it never launches the TUI.
Codex remains the owner of selecting the last durable thread for that
workspace. After the TUI loads it, every wakeup attempt requires exactly one
loaded thread, reads it back, and verifies its working directory is the
expected Agent Stack workspace.
Zero, multiple, or mismatched loaded threads fail closed. Checking on each
attempt also refuses delivery if the TUI leaves more than one thread loaded
after an interactive switch. The watcher never starts or loads a thread
itself. It then:

- calls `turn/start` with the fixed prompt when the thread is idle;
- calls `turn/steer` only with the exact active `expectedTurnId`;
- returns `deferred` when the endpoint is unavailable or state is not safe;
- returns `ambiguous` when the connection fails after a request might have
  been accepted.

If the TUI starts a turn between the idle read and `turn/start`, the watcher
must use the provider's explicit conflict response. It may re-read and steer
only the exact new active turn; an unclassified response is ambiguous.

The app-server response and subsequent state notification update the existing
notification markers. The TUI and mailbox watcher cannot operate on different
app-server processes because the same launcher created both children with one
in-memory endpoint and token.

## Pre-adapter mechanism gates

Provider-aware parsing, storage, receiver identity, marker state, and Copilot
reuse may be implemented first. Provider adapter code is blocked until its
platform probe settles these facts:

- Claude: exact post-auth message framing; whether the socket replies with
  accepted, held, or refused; whether socket or token changes across resume,
  clear, and compact; and successful old-to-new watcher handover after a
  changing generation.
- Codex: the installed version's exact remote resume invocation; exactly one
  loaded cwd-matching thread; token handling without command-line exposure;
  `turn/start` behavior during a concurrent TUI turn; exact
  `expectedTurnId` steering; and app-server/watcher cleanup after launcher
  death.

If a probe cannot preserve exact identity, authenticated local control, or
truthful outcomes, that provider-platform pair remains disabled and the
reframe gate opens before another mechanism is added.

## Upgrade and relaunch guidance

A mailbox wakeup never upgrades software or restarts a process. A deferred
outcome includes the required capability, observed version or launch mode, and
the exact supported upgrade or Agent Stack relaunch guidance when known.

Automatic repair is a separate future work order. Its recorded authority
allows it only when the session is idle and Agent Stack-owned. This design adds
no restart channel, package-manager integration, idle-input detector, or
supervision loop.

## End-to-end journey

Alpha in Copilot sends mail to `codex:alpha`.

1. The mailbox parser canonicalizes the target as local Codex Alpha.
2. The mailbox writes the envelope under the local provider-qualified mailbox.
3. The Agent Stack-owned Codex watcher observes the envelope while holding the
   exact launch's in-memory endpoint and token.
4. The watcher authenticates to its app-server and verifies the loaded thread
   and workspace.
5. If idle, it starts a turn containing only
   `check mailbox; skip if empty <marker>`.
6. Codex reads the durable envelope with the mailbox skill and acknowledges it.
7. The watcher records the existing notification marker, and the sender sees a
   verified wakeup result. The envelope moves to delivered only when Codex
   acknowledges it, not when step 5 succeeds.

If Codex is too old or was not launched through Agent Stack, step 3 or 4
returns deferred. The envelope remains pending and the sender receives upgrade
or Agent Stack relaunch guidance. The process is not touched.

## Failure model

- **Address collision:** canonical provider-qualified storage prevents
  same-name Copilot, Claude, and Codex mailboxes from sharing a directory.
- **Receiver identity loss:** a non-Copilot provider without a valid
  `MAILBOX_SELF_ADDRESS` refuses mailbox operations instead of reading the
  bare Copilot alias.
- **Stale child:** the watcher exits when its provider or launcher parent is
  gone; a changed Claude socket leaves a new watcher waiting on the existing
  lock until the old watcher either proves it can still deliver or exits after
  terminal pre-write endpoint loss or authentication rejection.
- **Token leak:** token values never enter mailbox data, durable state,
  diagnostics, process arguments, or notification markers.
- **Provider hold/refusal:** when the provider exposes that outcome, the
  envelope remains pending and the marker names it. A provider with no
  authoritative reply reports only `submitted`.
- **Repeated submission:** terminal attempt outcomes suppress automatic replay;
  only `deferred` retries automatically. A later new envelope triggers a new
  wakeup attempt and lets the provider process all still-pending mail.
- **Lost wakeup:** Claude/Codex watcher polling retries a deferred envelope.
  Copilot may also use its existing explicit poke path. Acknowledgement remains
  separate.
- **Ambiguous send:** the attempt is marked ambiguous and the same attempt
  identity is never replayed automatically.
- **Codex active-turn race:** steering requires the exact current turn identity;
  a changed turn rejects the request.
- **Launcher death:** `codex-native-contract` must prove that its app-server
  and watcher children exit or are terminated by the launcher's cleanup path.
  Provider durable conversation state remains provider-owned; a normal Agent
  Stack launch resumes it. Mail remains pending.
- **Remote outage:** existing local outbox and immutable retry behavior remain
  unchanged.

## Migration

1. Add provider-aware parsing and compatibility tests before changing any
   watcher.
2. Introduce canonical provider-qualified directories and
   `MAILBOX_SELF_ADDRESS` while retaining bare Copilot reads and sends.
3. Add versioned outcome payloads to the existing notification markers and
   provider adapter interfaces.
4. Reuse session-inbox for Copilot with no behavior change.
5. Add the Claude hook watcher and prove its native submission or receipt path,
   including hook re-fire behavior.
6. Add managed Codex app-server launch and prove exact thread control.
7. Enable each provider separately on each proven platform. Windows proof can
   ship the Windows path without waiting for macOS proof.
8. Remove a provider's macOS tmux wakeup fallback only after that provider's
   native macOS live proof passes. Keep tmux for terminal persistence, not
   mailbox input.
9. Leave automatic autopilot repair for a separate work order using the
   recorded ownership and idle constraints.

Existing bare Copilot mailbox data is not bulk-renamed. Compatibility
normalization reads it in place.

## Rollback

- Disable provider-native wakeup per provider and leave envelopes queued.
- Restore bare Copilot-only dispatch through session-inbox.
- Stop and remove only Agent Stack-owned Claude/Codex watcher children and
  Codex app-server children.
- Launch Codex with its prior embedded mode and Claude with its prior direct
  mode.
- Do not restore terminal injection. Manual mailbox pickup is the safe
  rollback for Claude and Codex.
- Do not rewrite or delete pending, delivered, remote, or provider conversation
  data.

Rollback is complete when provider processes run normally, no Agent Stack
native-control child remains, Copilot mailbox delivery still works, and every
Claude/Codex envelope remains readable for manual pickup.

## Hard invariants

1. `provider:name` selects one provider and one local session.
2. `@machine` alone selects remote transport.
3. Bare names remain Copilot aliases and never broadcast.
4. The durable envelope is written before any wakeup attempt.
5. Wakeup success never acknowledges an envelope.
6. Provider control carries only the fixed mailbox prompt and marker.
7. No provider token enters durable mailbox or diagnostic content.
8. Provider-native delivery never uses terminal injection. An existing macOS
   tmux compatibility path is removed separately for each provider only after
   that provider's native macOS proof passes.
9. The provider watcher is a child of the owning launch and checks exact
   workspace and conversation identity before provider control.
10. Codex TUI and control client use the same managed app-server.
11. This change never upgrades or restarts a provider process.
12. Any unknown identity, ownership, state, or side effect leaves mail pending.
13. A non-Copilot receiver never derives its mailbox or sender identity from a
    bare name.
14. One envelope attempt can produce at most one provider submission.

## Acceptance criteria

`AC-1` Address parsing distinguishes all three provider-qualified local
addresses, preserves bare Copilot compatibility, and makes receiver
self-identity exact for check, acknowledge, send, and reply.

`AC-2` Provider-qualified remote mail publishes and imports through the
existing immutable transport without mixing provider identity with machine
identity.

`AC-3` A live idle Copilot and Codex Agent Stack session each returns a verified
native wakeup for one fixed prompt. Claude returns verified only if its socket
provides an authoritative reply; otherwise it returns submitted and live proof
shows the turn started.

`AC-4` Active Claude delivery occurs only through its documented between-tool
queue, and active Codex delivery steers only the exact active turn.

`AC-5` Held and refused outcomes are reported when the provider exposes them.
Unavailable, stale, unsupported, submitted-only, and ambiguous targets remain
pending and return distinct structured outcomes.

`AC-6` Claude and Codex native delivery works without terminal input on each
provider-platform pair that is enabled. Windows enablement requires Windows
proof; macOS tmux removal requires separate native macOS proof.

`AC-7` Provider tokens and bearer secrets are absent from mailbox envelopes,
durable state, diagnostics, markers, process command lines, and captured test
output.

`AC-8` Hook re-fire, process death, stale watcher locks, and duplicate launch do
not redirect mail to another generation or conversation.

`AC-9` An unsupported version or unmanaged launch returns actionable upgrade or
Agent Stack relaunch guidance without changing the installed binary or process.

`AC-10` Mail to an active, ambiguous, stale, unsupported, or unowned target
cannot stop, restart, upgrade, or claim that target.

`AC-11` Existing Copilot mailbox, local-first remote transport, and provider
resume tests continue to pass.

`AC-12` Rollback leaves provider conversations and every envelope intact and
returns Claude/Codex to manual mailbox pickup.

## Check contract

| Check | Protects | Setup and transition | Pass signal | Failure proves |
| --- | --- | --- | --- | --- |
| `address-schema` | AC-1, AC-2 | Table-test valid and invalid bare, provider, and machine forms; round-trip canonical envelope fields; set each provider self address and run check, acknowledge, send, and reply resolution. | Exact canonical structures; Claude/Codex never touch bare Copilot paths; invalid non-Copilot self identity refuses. | Provider or machine identity can collide, route incorrectly, or consume another provider's mail. |
| `provider-remote-transport` | AC-2 | Publish `claude:alpha@surface-pro` and `codex:alpha@surface-pro` through a temporary immutable remote root while bare Copilot `alpha` exists; import each twice and acknowledge locally. | Each imports exactly once into its provider-qualified local mailbox; bare Copilot is untouched; remote bytes are unchanged; no mutable marker enters remote storage. | Provider identity is lost or the existing immutable transport contract regresses. |
| `legacy-copilot-compat` | AC-1, AC-11 | Read and send against an existing bare Copilot fixture without `MAILBOX_SELF_ADDRESS`. | Same mailbox files and session-inbox target as before. | Migration breaks current callers. |
| `wakeup-state-machine` | AC-3, AC-4, AC-5 | Fake each adapter outcome and generation race around a pending envelope, then run another watch tick. | Existing notified marker remains compatible; unverified payload distinguishes submitted/held/refused/ambiguous and suppresses replay; deferred writes no marker and may retry; envelope stays pending. | Persistence and live delivery claims are coupled incorrectly or prompts can repeat. |
| `claude-native-contract` | AC-3 through AC-8 | Launch a temporary supported Claude session with the Agent Stack hook; probe socket reply semantics, idle and active sends, inbound hold/refuse, hook re-fire, socket change, parent death, and waiter acquisition after auth rejection, missing endpoint, and refused connection while preserving the watcher on transient busy. | Exact submitted/verified/held/refused/ambiguous outcome marker plus transcript marker; one acting watcher; no secret in captured files or process args. | Claude delivery or watcher lifecycle is not authenticated, immediate, truthful, single-owner, or secret-safe. |
| `codex-native-contract` | AC-3 through AC-8 | Launch a temporary app-server, child watcher, and attached TUI; probe `resume --last --remote`, idle start, concurrent TUI start, exact-turn steer, wrong-turn race, parent death, and app-server exit. | Matching thread/turn notifications and transcript marker; no orphaned watcher or server. | Control can reach the wrong thread, race user input, or claim an unproved side effect. |
| `cross-provider-live-windows` | AC-3, AC-6, AC-11 | Send Copilot to Claude and Codex, then reply to provider-qualified Copilot in isolated Windows workspaces. | All envelopes read and acknowledged by exact targets without terminal input. | The composed Windows journey fails despite adapter tests. |
| `cross-provider-live-macos` | AC-3, AC-6, AC-11 | Repeat the provider journey on macOS before removing that provider's tmux fallback. | Exact native targets acknowledge and no tmux input occurs. | Native macOS control is not ready to replace the old path. |
| `secret-hygiene` | AC-7 | Scan deterministic fixtures, logs, markers, durable state, command lines, and test captures using unique canary secrets. | Canary absent everywhere outside child process environments and provider memory. | A provider credential escaped its allowed boundary. |
| `generation-ownership` | AC-8, AC-10 | Re-fire hooks with stable and changed socket identities; keep the old endpoint valid in one case; reject auth, remove the socket/pipe, refuse connection, and return a transient busy error in separate cases; kill parents, leave stale locks, and start duplicate launches around pending mail. | Matching identity reuses one watcher; changed identity leaves one actor plus one waiter; terminal pre-write failures release the lock and the waiter wakes mail; transient busy retains the old watcher; stale generations cannot record success. | Re-fire can leave zero or multiple acting watchers, transient errors can kill the only watcher, or stale state can control another process. |
| `no-implicit-repair` | AC-9, AC-10 | Assert provider adapters expose only wakeup/status operations and inspect call sites during review. | No upgrade, restart, stop, package-manager, or process-control operation exists. | Delivery code silently expanded into package or process control. |
| `rollback-preservation` | AC-12 | Populate pending/delivered/remote/provider fixtures, enable native control, then roll back. | Byte-identical durable data and normal provider resume. | Rollback can lose mail or conversation state. |
| Existing mailbox and Agent Stack suites | AC-11 | Run the repositories' targeted existing suites. | All prior tests pass. | The change regressed an established contract. |

The `address-schema`, `wakeup-state-machine`, and `generation-ownership` guards
must exist before provider integration. Before adapter code is written, its
native contract probe must settle the unresolved wire and race behavior for
that provider-platform pair.

## Where this design is weak

- Claude documents socket authentication and own-child posting but not the full
  message object or reply in the public page. A bounded live probe must settle
  the exact framing and whether runtime status is verified or only submitted.
- Native Windows Codex currently depends on loopback WebSocket transport that
  its documentation calls experimental and unsupported. The design contains
  that risk to one local per-session endpoint, requires authentication, and
  keeps manual pickup as rollback. A supported Windows local transport would
  remove the largest provider risk.
- Claude and Codex tokens authenticate provider protocols but do not isolate
  one process from another process running as the same operating-system user.
  The design does not claim that boundary. It keeps secrets out of durable and
  user-visible surfaces and limits token lifetime to the owning launch.
- A watcher and, for Codex, app-server per live provider session use more
  processes than a machine-wide broker. They reuse the launcher's lifetime and
  existing watcher locks, and avoid a registry, durable secret, or shared
  multi-tenant identity.
- The design touches active dirty work in the main Skills checkout. Delivery
  must integrate through isolated worktrees and reconcile rather than overwrite
  that work.

## Definition of Done: Provider-Native Cross-Client Mailbox

The change is done when canonical provider-qualified mail works end to end on
supported Windows and macOS Agent Stack sessions; Copilot uses session-inbox,
Claude uses its authenticated own-session socket, and Codex uses the same
managed app-server as its TUI; unsupported or uncertain delivery remains
pending with truthful upgrade or relaunch guidance and never changes a provider
binary or process; terminal injection is absent; secrets stay inside their
local provider boundary; rollback preserves every envelope and conversation;
all checks above pass; implementation review is complete; and reviewed commits
are pushed to owned feature branches without merging to main.
