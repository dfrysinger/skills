# Provider-Native Cross-Client Mailbox Constraint Challenge

## Status

**Evidence packet:** `provider-native-cross-client-mailbox-evidence-v1`
**Decision record:** `provider-native-cross-client-mailbox-decisions-v3`
**Pass 1 challenger:** fresh Claude Opus 5.5 context
**Pass 1 status:** complete
**Pass 2 challenger:** fresh Claude Opus 5.5 context, using this file as the
pass-1 continuity record
**Pass 2 subject:** `provider-native-cross-client-mailbox-design-v2-draft`
**Pass 2 status:** complete — initial `NARROW`; v3 recheck `CONTINUE`

## Pass 1: minimum design before proposal exposure

**Decision: `NARROW`.**

The required result is durable `provider:name[@machine]` mail, immediate native
wakeup for a supported exact live session, and truthful pending status with
upgrade guidance when that wakeup is unavailable.

The challenger classified the user's automatic upgrade and restart statements
as permission with safety conditions, not as a requirement for the first
working slice. The sentence "or if in autopilot maybe upgrade it automatically"
is a tactical suggestion. Recommending an upgrade already satisfies the
resolved unavailable-control decision.

### Minimum design

1. Parse provider-qualified identity while preserving bare Copilot aliases and
   the existing remote transport.
2. Keep Copilot session-control unchanged.
3. Use Claude's authenticated native session socket or named pipe.
4. Start Codex app-server as a child of each managed launch and attach the TUI
   and mailbox control client to that same server.
5. Keep only the minimum machine-local endpoint state needed to prove the exact
   live generation.

### Keep

- Provider-qualified logical identity.
- Existing immutable cross-computer transport.
- Durable envelope before wakeup.
- No terminal input injection.
- Distinct verified, deferred, held, refused, and ambiguous outcomes.
- Provider tokens excluded from arguments, logs, chat, and mailbox data.
- Agent Stack ownership as a condition of any future automatic restart.

### Remove or defer

- Automatic provider upgrade and restart from the first implementation.
- Portable idle and unsubmitted-input proof needed only by that repair flow.
- A resident Codex supervisor or machine-wide broker.
- New remote transport and new coordination locks.

### Unresolved facts entering proposal review

1. Whether Claude needs the sender to be its own child on native Windows. The
   minimum safe path is a SessionStart-hook child, which the proposal may use
   without persisting the token.
2. Whether the Codex TUI can receive its remote token without a command-line
   secret. Official documentation now answers yes through
   `--remote-auth-token-env`.
3. Native Windows Codex uses loopback WebSocket transport that OpenAI marks
   experimental and unsupported. A bounded live probe must prove the current
   installed release before this path can ship.

### Three highest-leverage assumptions

1. Automatic upgrade/restart was assumed required; it is only permitted.
2. Codex was assumed to need a resident supervisor; launch-scoped ownership is
   sufficient.
3. A general Claude sender was assumed safe; the documented own-child path is
   narrower.

### Reverse-trace gaps

- Define a Windows-safe storage mapping for logical addresses containing `:`.
- Confirm the exact Claude socket message framing and receipt.
- Generate the installed Codex schema for exact `turn/steer` fields.
- Prove the loopback Codex endpoint and attached TUI on native Windows.
- Define the accepted-versus-ambiguous receipt boundary for each provider.

### Authority and policy

The owner may deliberately grant local native control or accept an experimental
loopback Codex transport. No external policy forbidding those choices is in the
evidence. Claude inbound controls limit untrusted peer messages. The token,
identity, and no-injection boundaries apply to the owner-approved path itself.
Any future restart control limits autopilot from expanding its grant to an
unowned session.

## Codex merged-start reframe and focused reconciliation

**Initial decision: `REFRAME`.** The reviewed work order assumed the app-server
would reject one of two concurrent `turn/start` requests. The installed Codex
0.166.0 server instead returned the same successful active turn to both
callers. That load-bearing race premise failed, so adapter implementation
remained blocked while the design was corrected.

**Corrected-action decision: `CONTINUE`.** The exact pending action is now:
for one Agent Stack-owned Codex launch, the child watcher validates exactly one
cwd-matching loaded thread, submits only the fixed mailbox prompt, reports a
successful idle `turn/start` as `submitted` even when it joins a concurrently
created turn, and uses `turn/steer` only with the exact active turn ID.

### User outcome and authority

The user requires immediate cross-client messaging for Agent Stack sessions,
said `"the sessions could be running but just need to be idle"`, and limited
the managed path with `"yes using agent stack, if its not an agent stack agent
session then no"`. The existing decision record also preserves the explicit
no-terminal-injection choice. The observable result is one durable envelope
and one exact native provider submission to the intended Codex thread, with no
claim stronger than the provider evidence.

### Keep

- **Per-launch app-server and child watcher.** Independent authority: immediate
  wakeup of the exact managed Codex session. Without it, durable `codex queue`
  does not wake the loaded TUI.
- **Exactly one cwd-matching loaded thread.** Independent authority: provider
  and workspace identity must not cross. Without it, the prompt can reach the
  wrong conversation.
- **Successful merged start reported as `submitted`.** Two conflicting writers
  are evidenced: the attached TUI and the mailbox watcher. The bounded probe
  showed two distinct concurrent inputs retained exactly once in one
  authoritative turn and acknowledged exactly once by the model.
- **Exact `expectedTurnId` steering and wrong-turn refusal.** This prevents an
  active-turn race from steering a different turn.
- **Job Object kill-on-close and in-memory token boundary.** These govern the
  owner-approved native path itself: launcher death must not leave controlled
  children running, and an untrusted mailbox sender must not gain the provider
  capability token.

### Remove

- The requirement for one `turn/start` caller to receive an explicit conflict.
- The conflict/re-read/steer transition after a successful concurrent start.
- Any claim that a successful start is `verified`; acknowledgement remains the
  only durable completion signal.

### Unresolved

None for the corrected Windows adapter action. macOS native Codex enablement
still requires its own platform proof and does not block Windows.

Deliberate owner grants are allowed. No external policy in the evidence
forbids authenticated local app-server control. The retained controls constrain
the selected owner-approved path and prevent authority expansion by untrusted
mailbox content; they are not categorical restrictions on the owner's ability
to launch Codex directly.

**Smallest next step:** implement the corrected child watcher and Job
Object-owned launch, then run `codex-native-contract` with the two-marker
merged-start fixture.

### Shared-state counts

- A session endpoint record has one writer: the owning launcher or Claude hook.
  It does not justify a new multi-writer lock.
- Existing mailbox claims already arbitrate multiple senders.
- A Codex TUI and mailbox client are two writers to one provider thread. Codex
  app-server must arbitrate their turn operations; Agent Stack must not add a
  second lock.

### Smallest next step

Revise the proposal to the narrowed first slice, then run pass 2. Implementation
starts with bounded Claude and Codex mechanism probes and the focused fixture:
three local `alpha` sessions, one unsupported pending target, and one
provider-qualified remote route.

## Pass 2: revised proposal

**Decision: `NARROW`.** The user outcome survives with less machinery. The
pending action, dual design review, stays blocked until the proposal applies
the narrowing below. No pass-2 finding needs a reframe. The remaining unknowns
are feasibility probes that are already behind the proposal's reframe gate.
None of them decides whether an addition is needed.

### User outcome and authority

The user outcome is unchanged from pass 1. Mail addressed to
`provider:name[@machine]` is stored durably, and a live Agent Stack session
for that exact provider and name wakes immediately without terminal input.
When that cannot be proved, the mail stays pending, the sender gets a truthful
status, and the guidance recommends an upgrade. The authority is
decisions-v2 events 1-4.

Events 5-6 grant permission for a later upgrade and restart flow. They do not
require it in this change. The user said cross-platform support "would be
excellent" if it can be done, and the question added "when proven." That
approves macOS as a goal for each platform after proof. It does not make
Windows shipment wait for macOS proof.

### Whether pass-1 narrowing was applied

| Pass-1 item | Applied? | Note |
| --- | --- | --- |
| Defer automatic upgrade and restart | Yes | Non-goal, invariant 11, and AC-9/AC-10 cover it. The added `no-implicit-repair` live check is a campaign to prove an absent feature. See addition 3. |
| No resident supervisor or broker | Yes | Codex uses one app-server per launch. |
| No new remote transport or locks | Partly | It adds no new lock. It does add an endpoint registry, a heartbeat writer, receipt storage, and a bearer-token secret file. See addition 1. |
| Windows-safe storage mapping | Yes | The `_providers/<provider>/<name>` layout cannot collide with bare names because `validateName` requires an alphanumeric first character. |
| Claude own-child sender | Yes | The design uses a SessionStart-hook watcher. Its lifecycle across hook re-fires is not specified. See addition 2. |
| Codex token without a command-line secret | Partly | The TUI uses `--remote-auth-token-env`. The app-server still reads a persistent secret file, which a simpler documented flag avoids. |
| Accepted versus ambiguous boundary for each provider | Copilot and Codex: yes. Claude: no | The public Claude docs define the auth line, a 30-second line timeout, and inbound `hold`/`refuse` handling. They do not define a socket acknowledgement. The proposal assumes a "provider result" that is not in the evidence. |

### Three highest-leverage remaining additions

**1. Sender-side Codex dispatch through a registry, a secret file, and
heartbeats. Remove and replace.**

The proposal adds a generation registry with these fields: launcher PID,
app-server PID, TUI PID, generation, version, capability, thread, endpoint,
runtime state, and update time. It also adds heartbeat expiry and a
user-only bearer-token file that any sender reads before calling app-server.

- Independent need: none. That machinery exists only because the sender
  process is the Codex control client. The user requires immediate wakeup of
  the exact session. The user did not require the sender to call app-server
  directly.
- Simpler existing capability: the launcher already stays alive while Codex
  runs. `agent-stack.ps1` holds a mutex for each name and waits on the child.
  The mailbox already has a portable `watch()` loop, a watcher lock, a
  notification claim, and `.notified` and `.unverified` markers. With the
  same pattern Claude needs, the launcher would:
  1. generate a token in memory;
  2. start `codex app-server` with `--ws-token-sha256 <hex>` on Windows
     loopback, or `unix://` where supported;
  3. pass the token to the TUI with `--remote-auth-token-env`;
  4. pass the token to a child mailbox watcher running
     `watch codex:<name>` with a Codex adapter.
- What this removes: the registry, the heartbeat loop, the PID tuple
  matching, the secret file, and any token reads by a sender. Generation
  identity follows from process lifetime plus a fresh token for each launch.
  A stale watcher cannot authenticate to a new app-server. Live thread and
  idle/active state are read from app-server through `thread/loaded/list`
  and `thread/read`, not from a stored copy.
- New requirement that is reachable: if the launcher is killed hard, an
  orphaned watcher keeps its address lock while its PID is alive. That would
  block the next launch's watcher. The watcher must therefore exit when its
  launcher parent is gone. That costs one check per poll loop and adds no new
  lock. Whether an orphaned app-server exits by itself is a probe fact.

**2. Claude SessionStart-hook watcher. Keep, but narrow and specify its
lifecycle.**

- Independent need: on native Windows, Claude closes any connection whose
  first line is not a valid auth line. The only token is the one exported to
  that session's children. The docs say the token is "the only way Claude
  Code verifies an own-child message" on native Windows. No outside sender
  can reach the session without persisting the token, so a child watcher is
  required.
- Narrowing:
  - Reuse `mailbox-core` `watch()`, its watcher lock, the notification claim,
    and the `.notified` and `.unverified` markers as the sender-visible
    receipt.
  - Add a Claude adapter only. Add no new receipt store.
  - The sender writes the envelope, then waits briefly for the existing
    marker or for an absent watcher, which means deferred plus guidance.
- Reachable failure the proposal does not address: SessionStart re-fires
  inside one Claude session on `resume`, `clear`, and `compact`. A second
  watcher would hit the existing lock while the first watcher may hold a
  token or socket that is no longer valid. The design must state whether the
  hook matcher is `startup|resume` only, or whether a newer watcher replaces
  an older one.

**3. Proof and release scope that goes past the user grant. Narrow it.**

- Make enablement per provider and per platform:
  - Windows ships on Windows proof.
  - The macOS tmux wakeup for Claude or Codex is removed only after native
    macOS proof passes for that provider.
  - Until then, unsupported native control on macOS follows decision 4: the
    mail stays queued and no new tmux fallback is added.
- Replace the separate `no-implicit-repair` live check with these two
  checks:
  - a `wakeup-state-machine` assertion that adapters expose no upgrade,
    restart, or stop operation;
  - review that no such call site exists.

  The byte-identical-binary live check protects a feature that no longer
  exists.
- The property to keep is that delivery never changes a provider binary or
  process. Its minimum direct check is the adapter interface assertion.
- Treat the outcome vocabulary as one rule: mail stays pending and the
  receipt names the unproved fact, passing the provider's reason through
  unchanged. Keep `held` distinct only because Claude `hold` needs user
  action in the target session.

### Keep

- Provider-qualified address grammar, the `_providers` storage mapping, and
  bare names as Copilot aliases. Authority: events 1-2 and the existing
  compatibility promise.
- The durable envelope is written before wakeup, and wakeup never
  acknowledges it. Authority: the existing architecture. Without it, a lost
  wakeup loses mail.
- Session-control stays unchanged for Copilot.
- The Claude own-child watcher, under addition 2.
- The Codex app-server per launch, with the TUI attached through `--remote`.
  Authority: event 2 requires immediate wakeup, and the docs say `codex queue`
  persistence alone does not reach the loaded TUI.
- The fixed `check mailbox; skip if empty <marker>` prompt only. Security
  reasoning:
  - Protected asset: user-turn authority in the target session. That
    includes approvals and sessions launched with bypass flags.
  - Uncontrolled actor: the peer or remote sender whose envelope text the
    owner does not control.
  - Forbidden operation: placing that text in Codex `turn/start` or
    `turn/steer`. App-server treats that input as user input.
  - Evidence: Codex docs describe turn input as user input. The binding
    boundary says "a provider control prompt is not user permission."

  This governs owner-approved mailbox code so that untrusted peer text cannot
  gain user-turn authority. It is not a defense against same-user processes.
- `turn/steer` with `expectedTurnId`. The parameter is documented, so the
  "if the schema supports it" condition can be dropped.
- Token exclusion from envelopes, remote transport, logs, diagnostics,
  arguments, and chat. Authority: the evidence binding boundary and
  secret-hygiene rules.
- No terminal injection. Authority: event 4.
- Agent Stack ownership as a precondition of any later restart. Authority:
  event 6.

### Remove

- The Codex endpoint registry, its heartbeat writer, PID/generation tuple
  matching, and the bearer-token secret file. Replace them with the
  launcher-child watcher and `--ws-token-sha256`.
- Wakeups dispatched by the sender to Claude or Codex. The sender writes the
  envelope and reads existing markers.
- A new receipt or endpoint-metadata store under the state root.
- "Agent Stack ownership" as a separately proved fact for delivery. A
  managed adapter exists only for sessions Agent Stack launched, and the user
  tied ownership to restart, not to delivery.
- The `no-implicit-repair` live campaign. It becomes an interface assertion.
- Any wording that makes macOS proof a gate on the Windows slice.
- The "least privilege" justification for a token file readable by the user.
  Any same-user process can read the file or the process environment. The
  design must not claim that token custody isolates same-user agents.

### Unresolved: one deciding fact each

Each fact decides feasibility or a lifecycle rule, not whether a component is
needed.

1. **Codex on native Windows.** Can a launcher-owned app-server
   (`unix://` if it works on Windows, otherwise loopback `ws://` with
   `--ws-token-sha256`) serve `codex resume --last --remote ...` for the same
   thread? Codex is not installed in this environment, so this cannot be
   probed here.
2. **Claude receipt.** Does the socket return any acceptance, hold, or refuse
   response after the auth line and message line? If it does not, a clean
   write is "submitted," not "verified." The proposal must then define
   verification without parsing conversation content, or define its receipt
   as submitted. This decides whether AC-3's "verified" can be claimed for
   Claude.
3. **Claude hook re-fire.** Do the socket and token stay stable across
   SessionStart `resume`, `clear`, and `compact`? This decides between
   restricting the hook matcher and adding a watcher takeover rule.
4. **Codex `turn/start` during a race.** When the TUI starts a turn between
   the watcher's idle read and its `turn/start`, does app-server reject the
   call or start a second turn? This decides whether "idle" can map to
   `turn/start`, or whether the adapter must re-read and use `turn/steer`.

### Owner grants and external policy

- Deliberate owner grants are allowed. Examples: an experimental loopback
  WebSocket transport, Claude or Codex permission-bypass launch flags, and a
  later autopilot restart under events 5-6.
- External policy forbidding these choices is absent from the evidence.
- The fixed-prompt rule and token exclusion govern owner-approved code paths
  themselves. They stop untrusted peer text from gaining user-turn authority
  and stop secrets from leaving the machine. They do not restrict what the
  owner may grant.
- Claude `crossSessionInbound` governs untrusted peers. Own-child messages
  bypass it only when no inbound value applies. The watcher sends only the
  fixed prompt, so peer text never inherits own-child status.
- The restart ownership rule limits an autopilot actor from expanding its
  grant to unowned sessions.

### Writer counts for retained shared state

| State | Evidenced writers | Mechanism |
| --- | --- | --- |
| Mailbox envelope directory | Many senders plus remote import | Existing atomic writes. Nothing new. |
| Notification claim (`notifying/<addr>.lock`) | Copilot: sender poke plus watcher, at least 2. Claude/Codex: the session watcher only, 1. | Existing claim reused. No new lock. |
| Watcher lock (`watchers/<addr>.lock`) | Claude: re-fired hook watchers, at least 2. Codex: orphaned watcher plus new launch, at least 2. | Existing lock reused, plus a liveness or takeover rule. No new lock. |
| `.notified` / `.unverified` markers | The claim holder, 1 | Existing. |
| Codex thread | TUI plus watcher, 2 | App-server arbitrates through `expectedTurnId` and the unresolved `turn/start` race. Agent Stack adds no lock. |
| Claude session input | User plus watcher, 2 | Claude arbitrates through its queue between tool calls. |
| Codex endpoint registry | Launcher, 1 | Removed. |

### Denied capabilities

Terminal input injection is denied by event 4. Codex `turn/start` and
`turn/steer`, and Claude socket posting, are the provider-native paths the
user explicitly approved in events 2-3. They are not an indirect re-grant of
injection. No other path in the proposal recreates keystroke injection.

### Smallest next step

Revise only these parts of the proposal: the Codex adapter, "Local session
registration," receipts, the macOS release gate, and the check contract. Make
them match the narrowing above, and record the four unresolved facts as
pre-adapter probes. Then run the dual design review.

Implementation may start with the `address-schema`,
`wakeup-state-machine`, and `generation-ownership` guards and with the Claude
probe. Claude probes need Claude Code 2.1.234 or later on native Windows.
Neither `claude` nor `codex` resolved on this challenger's PATH. Codex
adapter code stays blocked until unresolved fact 1 is proved on an installed
build.

## Pass 2 recheck: design v3

**Decision: `CONTINUE`.** Design v3 applied every material pass-2 narrowing.
It removed the Codex registry, heartbeat, PID tuple, durable token, sender-side
native dispatch, new receipt store, automatic repair campaign, and
cross-platform release coupling.

The design may proceed to dual design review. The permitted scope is the
provider-aware schema and storage guards, existing Copilot adapter, bounded
Claude and Codex mechanism probes, child watchers, one Codex app-server per
launch, and platform-specific enablement after that platform's proof.

Blocked scope remains:

- Codex adapter code before native Windows `resume --last --remote` is proved
  against a launcher-owned app-server;
- adapter enablement before its reply, hook-re-fire, and race probes pass;
- macOS tmux removal before native macOS proof for that provider;
- automatic upgrade or restart;
- any registry, heartbeat, durable token, sender-side provider dispatch,
  broker, supervisor, new lock, or terminal injection.

The owner may deliberately accept the experimental loopback Codex transport.
No external policy forbidding it is evidenced. Existing watcher locks have two
reachable contenders after hook re-fire or orphan cleanup. Codex thread state
has two writers, the TUI and watcher, and remains arbitrated by app-server with
`expectedTurnId`; no Agent Stack lock is added.

## Focused reconciliation after dual-review round 1

The round-one findings added provider self identity, provider-qualified remote
transport proof, outcome detail, Claude hook re-fire handling, and exact Codex
remote resume. The first focused reconciliation returned `NARROW`:

- keep `MAILBOX_SELF_ADDRESS` and map every address-keyed mailbox and state
  path through one Windows-safe helper;
- keep the remote transport integration check;
- keep `.notified` compatible and add outcome detail only to existing
  `.unverified` markers;
- write no marker for deferred attempts and add no explicit retry operation;
- remove the Claude takeover file and use one acting watcher plus a waiter on
  the existing lock, keyed only by non-secret socket hash;
- check exactly one cwd-matching loaded Codex thread on every attempt, without
  a registry or stored thread binding.

Design v5 applied that narrowing. A final focused recheck required removal of
two unsupported phrases: an app-server-empty precondition and a generic
Claude/Codex explicit-poke fallback. Those phrases were removed.

**Current gate: `CONTINUE`.** Dual-review round 2 may verify the round-one
findings and v5 delta. Codex adapter code remains blocked until the native
Windows remote-resume probe passes. Provider enablement remains blocked until
that provider-platform pair's native contract probe passes.

## macOS Codex authenticated-transport reframe

**Decision: `REFRAME`.** Codex 0.166.0 rejects
`--remote-auth-token-env` for a `unix://PATH` remote. The reviewed macOS action
requires the TUI and watcher to authenticate to one launcher-owned Unix
app-server with the same in-memory token. That action cannot launch, so macOS
Codex implementation and the dependent identity, delivery, steering, and
cleanup proofs remain blocked.

### User outcome and authority

The retained outcome is immediate native wakeup of the exact Agent Stack-owned
Codex thread, with durable mail left pending when exact local control cannot be
proved. The user authorized the Codex upgrade and proof. That authorization
does not select a different local transport or weaken the authenticated-control
boundary after the reviewed Unix contract fails.

### Keep

- One app-server and one mailbox watcher owned by each Agent Stack launch.
- Exactly one loaded thread whose working directory matches the launch.
- No token in arguments, files, logs, mailbox data, or diagnostics.
- No terminal input injection.
- Fail-closed pending mail when endpoint, thread, or turn identity is not exact.

The app-server remains the shared state owner for two evidenced writers, the
TUI and watcher. No additional coordination lock is justified.

### Remove

- The assumption that `--remote-auth-token-env` works with `unix://PATH` on
  macOS Codex 0.166.0.
- Any implementation or proof claim that depends on that rejected launch.

### Unresolved

The deciding fact is which corrected owner-approved boundary should replace
the failed contract:

1. a private Unix socket with operating-system file permissions and no Codex
   bearer token; or
2. an authenticated loopback WebSocket, which the installed TUI explicitly
   permits with `--remote-auth-token-env`.

The second option reuses the already proved Windows topology and preserves the
provider bearer-token check. The first option keeps the smaller macOS-local
transport but changes what authenticates the client. No external policy in the
evidence forbids either deliberate owner grant. Both govern owner-approved
local control; the token and exact-thread checks prevent untrusted mailbox
content from expanding that grant.

**Smallest next step:** write one corrected bounded macOS Codex action that
selects a transport and names its trust boundary, then reconcile and probe that
exact action before writing adapter or launcher code.

## Authenticated-loopback reconciliation for macOS Codex

**Decision: `CONTINUE`.** The corrected action uses one authenticated
`127.0.0.1` WebSocket app-server per Agent Stack-owned Codex launch on both
macOS and Windows. The launcher gives app-server only the token hash and gives
the raw token to the TUI and watcher through private child environments.

The user's cross-client, cross-platform outcome remains unchanged. This
topology reuses the admitted Windows contract and the installed macOS TUI's
supported authentication form. It adds no broker, registry, durable token,
new lock, or terminal input path.

### Keep

- One launcher-owned app-server, watcher, and TUI per Codex session.
- Bearer-token authentication, exact loaded-thread and working-directory
  checks, exact active-turn steering, and fail-closed pending mail.
- Existing app-server arbitration for the two evidenced thread writers, the
  TUI and watcher.

### Remove

- The macOS Unix transport choice.
- Any platform-specific Codex authentication downgrade.

### Unresolved

The corrected macOS mechanism still needs a bounded live proof for loopback
binding, missing and wrong token refusal, exact TUI resume, idle start, active
steering, concurrent start retention, launcher-child cleanup, endpoint
closure, and token secrecy. These are proof gates, not new architecture.

Deliberate owner grants are allowed. No external policy in the evidence
forbids an authenticated local listener. The bearer token governs the
owner-approved control path and prevents other local clients without the token
from exercising Codex control. Exact thread checks prevent mailbox content
from redirecting that authority.

**Smallest next step:** run the corrected macOS native contract probe. Write no
adapter or launcher code until every listed mechanism gate passes.

## Fresh two-pass macOS loopback challenge

**Evidence packet:** `provider-native-cross-client-mailbox-evidence-v1`
**Decision record:** `provider-native-cross-client-mailbox-decisions-v3`
**Challenger:** fresh read-only context
`98df4602-ac7d-4a1d-8312-5bde65090aa4`
**Pass 2 subject:** `provider-native-cross-client-mailbox-design-v7-loopback-review`
**Decision: `CONTINUE`, narrowly gated**

Pass 1 received the evidence and decision records without the proposal. It
independently derived the minimum macOS Codex design:

- one authenticated loopback app-server shared by the Agent Stack-owned TUI
  and watcher;
- one launch-scoped raw token in private child environments, with only its hash
  passed to app-server;
- exact loaded-thread, workspace, and active-turn checks;
- launcher-owned cleanup; and
- truthful `submitted`, `deferred`, and `ambiguous` outcomes while the envelope
  remains pending until acknowledgement.

Pass 2 found that the revised proposal matches that minimum and closes the
foreign-listener risk. App-server binds port zero, and the launcher must prove
exactly one `127.0.0.1` listener belongs to the live app-server child before it
gives either client the endpoint or raw token.

Keep the per-launch app-server, TUI, and watcher; token/hash separation; exact
listener, thread, workspace, and turn checks; truthful pending outcomes; and
the ban on terminal injection. Remove the Unix-authentication assumption and
block all adapter or launcher code until the native-contract probe passes.

The remaining unknowns are probe facts: whether the installed macOS app-server
supports an authoritative port-zero ownership chain, the exact remote resume
form, missing and wrong token refusal, thread identity, idle and active
delivery, concurrent-start retention, cleanup, endpoint closure, and secret
hygiene.

Agent Stack owns launch, lifecycle, and workspace authority. App-server owns
thread and turn arbitration. The bearer token grants local client authority
but does not claim same-user process isolation. Operating-system listener
ownership prevents endpoint substitution before token disclosure. Mailbox
content cannot alter identity, permissions, or control policy.

**Smallest next step:** run one bounded macOS native-contract probe against the
exact port-zero, child-owned authenticated-loopback design. Write no adapter or
launcher code until every gate passes.
