# Provider-Native Cross-Client Mailbox Probe Record

This record preserves the pre-adapter mechanism gates required by
`provider-native-cross-client-mailbox.md`. No credential values, provider
tokens, or protected account data are recorded here.

## Claude Code 2.1.302 on native Windows

**Gate: ADMITTED**

The installed native Windows CLI was exercised first through its documented
non-interactive stream protocol and then through a real interactive TUI under
ConPTY. ConPTY input was used only to drive the bounded probe; mailbox delivery
used the authenticated Claude messaging pipe.

Observed contract:

- A `SessionStart` hook receives
  `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`,
  `CLAUDE_CODE_SESSION_ID`, and `CLAUDE_PID`.
- `CLAUDE_PID`, not the hook process parent, identifies the long-lived Claude
  process.
- The native Windows endpoint is a named pipe.
- A watcher authenticates by writing one JSON line:
  `{"type":"auth","token":"..."}`.
- After waiting about 250 ms to detect an authentication close, it writes:
  `{"type":"user","message":{"role":"user","content":"<fixed prompt>"}}`.
- The pipe sends no acknowledgement bytes. A clean message write is therefore
  `submitted`, never `verified`.
- A close after the authentication line is `deferred` and releases the watcher
  lock. `ENOENT` before a write is also `deferred` and releases the lock.
- An error after message bytes may have been written is `ambiguous`.
- Idle delivery started and completed a model turn.
- Delivery during an active multi-tool turn arrived between tool calls.
- Startup, `/clear`, `/compact`, and in-process `/resume` re-fired
  `SessionStart`. The process ID and socket hash remained stable in the
  exercised in-process cases; matching generations must reuse the existing
  watcher.
- Watchers exited after `/exit` by polling `CLAUDE_PID`.
- The token was absent from process arguments and from the bounded probe's
  files, logs, transcripts, and command output.

The pipe cannot distinguish Claude's accept, hold, refuse, or ignore policies.
The adapter must not claim those outcomes.

## Codex CLI 0.166.0 on native Windows

**Gate: ADMITTED**

The installed CLI proved the following app-server contract:

- `app-server --listen ws://127.0.0.1:<port> --ws-auth capability-token
  --ws-token-sha256 <hash>` accepts an authenticated loopback WebSocket.
- The raw launch-scoped token can remain in private child environments and
  outside arguments and durable files.
- The real remote TUI invocation is the installed-version equivalent of
  `resume --last --cd <workspace> --remote <endpoint>
  --remote-auth-token-env <environment-name>`.
- `thread/loaded/list` and `thread/read` can prove exactly one loaded thread
  with the expected workspace.
- `turn/start` works while idle.
- `turn/steer` works with the exact active `expectedTurnId`.
- A nonmatching turn ID is refused.

The first probe also found two unresolved gates:

- app-server and watcher children survived launcher death;
- the concurrent TUI-start race was not observed under a true console-backed
  launch.

The second probe closed the lifecycle gate:

- app-server, watcher, primary TUI, and race-TUI children were assigned to one
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` Job Object;
- killing the launcher terminated every owned child;
- raw-token scans of process arguments and temporary files remained clean.

The second probe kept a real native TUI attached to the exact synthetic thread,
but an unsupported positional prompt on a second `codex resume` did not create
a turn. A direct protocol race then showed that two separately authenticated
clients can both receive successful `turn/start` responses containing the same
active turn ID. The server does not return the conflict assumed by the reviewed
work order. Exact-turn steering still succeeds and wrong-turn steering is
refused.

The final probe inspected authoritative `thread/items/list` history for two
distinct marker inputs. Both `turn/start` responses returned the same turn ID;
each marker appeared exactly once as a `userMessage` in that turn, and the
completed turn's `agentMessage` acknowledged each marker exactly once. The
responses were not duplicate views of one input: both inputs were attached to
the shared turn.

The corrected contract is admitted:

- a successful idle `turn/start` is `submitted` whether it creates a turn or
  joins a concurrently created turn;
- it is never `verified`;
- exact active-turn steering remains required;
- a wrong-turn error proves pre-acceptance refusal and permits one exact
  re-read/re-steer;
- unclassified post-request failures are `ambiguous`.

## Claude Code 2.1.222 on macOS

**Gate: SUPERSEDED BY THE 2.1.318 PROOF BELOW**

The installed arm64 macOS client was checked against the reviewed native
messaging requirement before any launcher change:

- installed version: `2.1.222`;
- documented macOS minimum: `2.1.224`;
- the installed binary contains `CLAUDE_PID`, but does not contain
  `CLAUDE_CODE_MESSAGING_SOCKET` or `CLAUDE_CODE_MESSAGING_TOKEN`.

This version cannot establish the authenticated own-session socket contract.
The macOS Claude adapter remains disabled and the guarded tmux compatibility
path remains in place. The next supported probe requires an attended upgrade
to Claude Code 2.1.224 or later. No provider token was read, printed, written,
or placed in process arguments.

## Claude Code 2.1.318 on macOS

**Gate: PASS**

After an attended upgrade, the installed arm64 macOS client exposed
`CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`, and
`CLAUDE_PID` to a SessionStart-hook child. The reviewed watcher and adapter
then passed the real provider journey:

- a private authenticated socket write started an idle Claude turn;
- a second native message arrived while Claude owned a foreground tool call
  and was processed after that tool checkpoint;
- both turns resolved the exact `claude:<name>` mailbox rather than a bare
  Copilot mailbox;
- the receiver read and acknowledged the durable envelopes;
- an Agent Stack-launched candidate sent a fixture-free reply back to the
  requesting Copilot session;
- stopping the owning Claude tmux session stopped the detached watcher;
- the token appeared in neither process arguments nor captured terminal,
  mailbox, test, or diagnostic output.

The first live run correctly exposed a stale installed Claude plugin: native
delivery started the turn, but the old mailbox CLI ignored
`MAILBOX_SELF_ADDRESS` and reported the provider mailbox empty. Loading the
exact provider-mailbox candidate fixed that consumer mismatch. The final
acceptance used the reviewed Skills candidate and the macOS Agent Stack
candidate together.

The committed-candidate acceptance on 2026-11-04 used Skills commit
`6b90342b816a47352505787894b5485aa361ffb3` and Agent Stack commit
`410367ac252a7222b76fdff31c29aad88ae63b4a`:

- an envelope written without sender-side wakeup started an idle native turn;
- the receiver replied `CLAUDE_FINAL_IDLE_PASS` and acknowledged the envelope;
- a second envelope arrived while Claude owned a 30-second Bash tool call;
- the receiver handled it after the tool checkpoint, replied
  `CLAUDE_FINAL_ACTIVE_PASS`, and acknowledged the envelope;
- closing the owning `claude-mailbox-final` tmux session stopped watcher process
  `85700`;
- the final Skills suite passed 54 tests, including notification-claim
  arbitration and terminal-interruption state handling;
- both feature branches matched their remote commit identities before the live
  proof.

This admits native macOS Claude delivery through the session-bound
SessionStart hook. It does not admit Codex changes.

### Claude 2.1.318 bypass-permissions inbound amendment

**Gate: LAUNCH-SCOPED ACCEPT REQUIRED FOR THE FINAL CANDIDATE**

The final exact-head replay on 2026-11-05 reached Claude's authenticated
socket and wrote the fixed mailbox prompt cleanly, but Claude held the message.
The receiver used `--dangerously-skip-permissions`, and the detached watcher
was a live verified process without a permission-mode classification.

A bounded distinguishing diagnostic kept the same real home directory,
mailbox address, SessionStart hook, exact mailbox scripts, and bypass mode:

- adding `crossSessionInbound: "accept"` to a project-local
  `.claude/settings.local.json` did not loosen the inbound policy;
- adding the same value to Claude's inline command-line `--settings` JSON
  auto-delivered the native watcher message;
- the receiver replied `CLAUDE_SETTINGS_DIAGNOSTIC_PASS`;
- the receiver acknowledged source envelope
  `20261105T020451108Z-67568-10d7d97ba6a6` in 12 seconds;
- no manual UI action delivered the message.

This diagnostic proves the mechanism but is not acceptance because it launched
Claude outside Agent Stack. The required implementation is the documented
launch-scoped setting in Agent Stack's generated native-Claude settings.

The governing provider sources are:

- [cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging)
  for `accept`, `hold`, `refuse`, unattended-worker guidance, and inbound
  outcomes;
- [Claude Code settings](https://code.claude.com/docs/en/settings) for inline
  `--settings` and precedence;
- [settings reference](https://code.claude.com/docs/en/settings-reference.md#crosssessioninbound)
  for the accepted values.

## Codex CLI 0.142.2 on macOS

**Gate: BLOCKED — CLIENT UPGRADE REQUIRED**

The installed arm64 macOS client passed the transport portion of the bounded
probe:

- `codex app-server` supports `unix://PATH`;
- `codex resume` supports `--remote unix://PATH` and
  `--remote-auth-token-env`;
- the generated installed-version schema contains the required thread and turn
  methods;
- the app-server created its Unix socket as `srw-------`, owned by the current
  user;
- the Unix socket accepted an HTTP WebSocket upgrade, establishing that the
  existing WebSocket RPC protocol can be carried over the private local socket.

The user completed a fresh protected device login for this exact CLI, and
`codex login status` confirmed ChatGPT authentication. Authenticated requests
then reached the service but every model advertised by the 0.142.2 app-server
catalog was rejected as unsupported for the ChatGPT account. The available
package version is 0.166.0.

No macOS Codex adapter or Agent Stack launch change is admitted from this
partial result. The guarded tmux compatibility path remains in place. After
an explicitly authorized Codex upgrade, rerun exact loaded-thread identity,
idle start, active-turn steering, launcher-child cleanup, fixture-free mailbox
reply and acknowledgement, and token-secrecy checks. No token value appeared
in arguments, files, logs, diagnostics, or user-visible output during this
probe.

## Codex CLI 0.166.0 on macOS

**Gate: PASS - AUTHENTICATED LOOPBACK NATIVE MAILBOX**

The upgraded arm64 macOS client retained ChatGPT authentication and completed a
real `gpt-6.1-sol` request. Its app-server also created an explicit Unix socket
as `srw-------`, owned by the current user, and accepted an authenticated
WebSocket client when started with:

```text
codex app-server --listen unix://PATH --ws-auth capability-token \
  --ws-token-sha256 HASH
```

The matching remote TUI cannot use that authenticated Unix endpoint. Codex
0.166.0 rejects this launch before it connects:

```text
ERROR: `--remote-auth-token-env` requires a `wss://` or loopback `ws://` remote.
```

This is the first divergent checkpoint from the reviewed macOS design. The
design requires Agent Stack to give the same raw token to the TUI and watcher
through private child environments while the app-server receives only the
token hash. The installed TUI accepts that token form for loopback WebSocket
endpoints, but not for `unix://PATH`.

No macOS Codex adapter or Agent Stack launch change is admitted. Loaded-thread
identity, idle start, active steering, mailbox reply and acknowledgement, and
launcher-child cleanup remain unproven because they depend on the rejected
launch contract. The guarded terminal compatibility path remains in place.
Further work needs an explicit design decision between a private Unix socket
without Codex bearer authentication and an authenticated loopback WebSocket
listener. No raw token appeared in command arguments, files, logs,
diagnostics, or user-visible output during this probe.

The reviewed authenticated loopback replacement then passed these macOS
mechanism checks through the real remote TUI:

- app-server bound an ephemeral `127.0.0.1` port chosen with port zero;
- the launcher derived exactly one listener owned by the exact app-server
  child PID before starting either client;
- missing and wrong bearer tokens were refused;
- stopping the child released the port, and a replacement process could bind
  that same port for the controlled child-exit/rebind case;
- the TUI resumed one exact cwd-matching loaded thread;
- idle `turn/start` completed a real `gpt-6.1-sol` turn;
- two concurrent `turn/start` calls returned one turn ID while retaining both
  distinct inputs and replies exactly once;
- wrong `expectedTurnId` steering was refused;
- closing the owning tmux session stopped the TUI and app-server, closed the
  listener, and left the raw token absent from arguments and proof files.

The probe also disproved one load-bearing adapter assumption. On this installed
runtime, `thread/read(includeTurns=false)` reports only
`{"type":"active","activeFlags":[]}` for an active thread.
`thread/turns/list`, `thread/items/list`, and
`thread/read(includeTurns=true)` return runtime "not supported yet" errors.
Notifications are scoped to the client that owns the turn, so a separate
session-bound watcher does not receive another client's active turn ID. A
production watcher therefore cannot satisfy the reviewed exact
`expectedTurnId` steering path.

The same installed runtime supports `thread/queue/add`. During a real
12-second active tool call, a second authenticated client added a distinct
queued prompt with a `clientUserMessageId`. App-server returned a queued
submission ID, automatically ran the queued prompt after the active turn, and
persisted the queued user marker and its assistant reply exactly once. This
also held when the thread became idle before queue acceptance: a second queued
prompt was accepted on the idle loaded thread, started automatically, and
persisted exactly once. Two simultaneous `thread/queue/add` calls from
separately authenticated clients returned distinct submission IDs and
persisted both distinct user markers and replies exactly once.

The runtime also supports `thread/settings/update`. For the exact loaded
thread, an accepted update set `approvalPolicy: "never"` and
`sandboxPolicy: { "type": "dangerFullAccess" }` for subsequent turns. A queued
turn then wrote a synthetic marker outside the workspace without an approval
prompt and completed its exact reply. This closes the macOS `ALLOW_ALL`
policy race without relying on concurrent `turn/start`.

These observations admit a macOS queue-based proposal only after its work
order and design review are updated. They do not replace the separately
admitted Windows start/steer contract.

The reviewed implementation then exposed and closed two composition gaps:

- a fresh remote TUI defaults to an ephemeral thread; idle queueing may be
  accepted, but active `thread/queue/add` is rejected with `-32600`. A focused
  native proof showed `-c ephemeral=false` creates a durable fresh TUI thread
  and accepts active queueing without a synthetic bootstrap turn;
- macOS can report one workspace as both `/tmp/...` and `/private/tmp/...`.
  Canonical filesystem identity plus exclusion of ephemeral macOS threads
  selects the durable TUI thread without recency or activity heuristics.

The final dirty candidate passed real TUI acceptance:

- active/concurrent envelopes
  `20261104T230348050Z-26663-51c12c71b668` and
  `20261104T230348103Z-26664-320bd7007000` were accepted by
  `thread/queue/add`, read, replied to with `CODEX_ACTIVE_CONCURRENT_V19`, and
  acknowledged;
- idle envelope `20261104T230607774Z-35721-f3ec8305c4a9` was accepted, read,
  replied to with `CODEX_IDLE_REPLY_V19`, and acknowledged;
- closing the owning tmux session stopped launcher, app-server, watcher, TUI,
  and monitor PIDs `26213,26241,26304,26365,26374` and closed
  `127.0.0.1:52374`;
- exact diff and proof-artifact scans found no raw capability token.

This evidence admits the reviewed macOS queue implementation after
two-family implementation review, committed-candidate identity, and remote
branch verification complete.
