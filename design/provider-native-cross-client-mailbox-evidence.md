# Provider-Native Cross-Client Mailbox Evidence

**Packet revision:** `provider-native-cross-client-mailbox-evidence-v1`

This packet records facts and binding decisions before architecture selection.
It intentionally does not propose a component layout.

## End user's job

The computer owner runs named Copilot CLI, Claude Code, and Codex CLI sessions
through Agent Stack. An agent must be able to send durable mail to another
named local or remote session, wake that exact live session immediately when
the provider supports it, and leave the mail queued with a truthful status when
it cannot prove delivery.

## Observable success

- `copilot:alpha`, `claude:alpha`, and `codex:alpha` identify three different
  local sessions even though all use the name `alpha`.
- `codex:alpha@surface-pro` selects remote transport to the Codex session on
  `surface-pro`; the `@machine` part does not enter local session identity.
- A local send to a live supported Claude or Codex Agent Stack session starts
  or steers a turn without simulated keyboard input.
- An unsupported, unavailable, held, refused, ambiguous, or mismatched target
  leaves the envelope pending and reports that state.
- Autopilot can upgrade and restart an idle session only when Agent Stack
  proves it owns that exact session. It never restarts an unowned session.

## Exact user authority

The complete exact quotes, questions, context, and authority classifications
are in
[`provider-native-cross-client-mailbox-decisions-v2`](provider-native-cross-client-mailbox-decisions.json).
All six events are resolved.

## Existing mailbox behavior

- `mailbox-core.mjs` accepts `NAME` or `NAME@MACHINE`.
- Unqualified messages use `MAILBOX_LOCAL_ROOT`.
- Qualified messages stage locally, publish immutable files through
  `MAILBOX_REMOTE_ROOT`, and import into an ordinary local mailbox.
- Mutable envelopes, acknowledgements, locks, claims, notification state, and
  diagnostics remain machine-local.
- The envelope is the durable source of truth. A wakeup is a separate attempt.
- Copilot immediate delivery uses the existing session-inbox extension and
  accepts only a receipt whose delivery is `idle` or `steering`.
- The current macOS path may fall back to guarded tmux input. The new user
  decision rejects that fallback for provider-native cross-client delivery.

Sources:

- [`windows-cross-computer-mailbox-addressing.md`](windows-cross-computer-mailbox-addressing.md)
- `skills/mailbox/scripts/mailbox-core.mjs`
- `skills/mailbox/scripts/mailbox-poke.sh`
- `extensions/session-inbox/request.mjs`

## Existing Agent Stack behavior

- Agent Stack owns provider choice, safe session name, isolated workspace,
  launcher arguments, and one-live-launch protection.
- Each provider remains the owner of its durable conversation.
- Native Windows uses an attached provider child process. Closing that process
  currently ends the launcher; a later launch resumes provider state.
- The Windows design explicitly excluded a resident supervisor and live
  process manager. Its reframe gate allows reconsideration when a
  provider-native cross-provider facility or explicit live-process requirement
  appears. Both are now present.
- The same name can be used for all three providers because their workspaces
  and state are separate.

Source:

- `C:\Users\dfrysinger\code\agent-stack-provider-mailbox\docs\windows-agent-stack-design.md`

## Provider capabilities

### Copilot CLI

The existing session-inbox extension joins the exact live Copilot session and
uses the SDK to send an immediate prompt. It already has target freshness,
generation, deduplication, receipt, and ambiguous-side-effect handling.

### Claude Code

[Claude Code cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging)
documents these properties:

- v2.1.224 or later supports the feature on macOS and Linux; native Windows
  requires v2.1.234 or later.
- Each eligible session binds a Unix socket or native Windows named pipe.
- `CLAUDE_CODE_MESSAGING_SOCKET` and a per-session
  `CLAUDE_CODE_MESSAGING_TOKEN` are exported to hooks and Bash commands.
- Native Windows requires the token in an authentication line.
- A message delivered to an idle session starts a new turn. An active session
  consumes it between tool calls.
- The session applies `crossSessionInbound` controls and normal permission
  boundaries. Incoming peer text cannot approve permissions or execute slash
  commands.
- A script or hook can post to its own session socket. The token can prove an
  own-child sender where process evidence is unavailable.
- The installed native Windows Claude version observed on 2026-11-03 is
  `2.1.302`.

### Codex CLI

[Codex app-server](https://developers.openai.com/codex/app-server) documents
these properties:

- The Codex TUI can connect to an app-server with `codex --remote`.
- The protocol is bidirectional JSON-RPC after an initialization handshake.
- `thread/resume` reopens a thread; `thread/read` and
  `thread/loaded/list` expose identity and runtime state.
- `turn/start` begins an idle turn.
- `turn/steer` adds input to an active turn.
- The CLI can generate schemas that match the exact installed version.
- Loopback WebSocket transport is available but marked experimental and
  unsupported. Unix sockets are available on macOS and Linux.
- WebSocket listeners support capability-token authentication and reject
  overload explicitly.

`codex queue` can persist work for later processing, but persistence alone does
not prove immediate delivery to the already loaded TUI. A supported immediate
path therefore requires the TUI and control client to reach the same managed
app-server.

## Binding boundaries

- Never place provider tokens in mailbox envelopes, remote transport, logs,
  diagnostics, command arguments, or chat output.
- Never use Windows `SendKeys`, console input injection, focus stealing, screen
  scraping, or macOS tmux keystrokes for this delivery path.
- Provider control endpoints remain machine-local.
- A provider control prompt is not user permission.
- A wakeup never acknowledges or removes the durable envelope.
- A remote route still imports into the exact provider-qualified local mailbox.
- Existing bare mailbox names remain Copilot-compatible aliases.
- Protected account login, MFA, SSO, and password entry remain user actions.

## Known unknowns for bounded implementation probes

- The exact Claude socket message line after authentication must be confirmed
  against the installed supported release without printing the token.
- The exact Codex `turn/steer` fields and remote TUI resume sequence must be
  generated or read from the installed version's schema.
- The portable process ownership and idle proofs needed for safe automatic
  upgrade/restart must be demonstrated on Windows and macOS.

If any unknown prevents exact identity, authenticated control, or fail-closed
state reporting, implementation must return to the design reframe gate rather
than add terminal injection.
