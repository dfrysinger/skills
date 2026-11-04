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

This admits native macOS Claude delivery through the session-bound
SessionStart hook. It does not admit Codex changes.

## Codex CLI 0.142.2 on macOS

**Gate: BLOCKED — PROTECTED LOGIN REQUIRED**

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

The exact-session and delivery portions could not run. The real Codex TUI
reported that its refresh token had already been used and required protected
sign-in. A remote TUI attached to the Unix app-server stopped at the same
sign-in flow before it could load and prove the expected workspace thread.

No macOS Codex adapter or Agent Stack launch change is admitted from this
partial result. The guarded tmux compatibility path remains in place. After
the user signs in to Codex, rerun exact loaded-thread identity, idle start,
active-turn steering, launcher-child cleanup, fixture-free mailbox reply and
acknowledgement, and token-secrecy checks. No token value appeared in arguments,
files, logs, diagnostics, or user-visible output during this probe.
