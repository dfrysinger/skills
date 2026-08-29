---
name: mailbox
description: Hand a file or message to another named Copilot CLI, Claude Code, or Codex CLI session. Use when this session has produced a deliverable another named agent should pick up, or the user says to send something to an agent by name (e.g. "send this to juliett"). Copilot delivery uses a portable Node watcher and SDK session names; macOS tmux remains a compatibility identity and the guarded fallback for Claude and Codex.
---

# mailbox

Cross-session and cross-computer message + file handoff, keyed by agent name.

## When to use

- User says "send this to <name>", "hand this off to <name>", "deliver X to <name>".
- You have produced a concrete artifact (file, doc, summary) for another named agent session to consume.
- You want to delegate a task to another live Copilot, Claude, or Codex session.

Do NOT use mailbox for:
- Self-talk inside the same session (just write to disk normally).
- Notifying a terminal that is not a recognized agent CLI (osascript notification suffices).
- Heavy bidirectional RPC. This is one-shot delivery, not a chat protocol.

## How it works

- **Identity = a live agent name.** On macOS, a live tmux session name remains
  the first choice so existing Agent Stack sessions keep their established
  identity. When no live tmux identity matches, Copilot falls back to the
  session's current `/rename` name. Only fresh session-inbox heartbeats are
  eligible, so abandoned historical sessions with the same name are ignored.
  Outside tmux, set the current session name with `/rename <name>`. Portable
  command-line tools also accept `--name` or `COPILOT_AGENT_NAME`.
- **Cross-computer address = `name@machine`.** An unqualified name such as
  `hotel` is an intentional live broadcast to currently running matching
  watchers. Address one computer explicitly with `hotel@surface-pro`. Set the
  stable machine label with `COPILOT_AGENT_MACHINE`; there is no hostname
  fallback, and labels must be unique within one shared `MAILBOX_ROOT`.
- **Transport = file queue.** Envelopes land at
  `$MAILBOX_ROOT/<recipient>/pending/<id>.json`, with attachments in a sibling
  `<id>/` directory. `MAILBOX_ROOT` defaults to `~/.copilot/mailbox` and may
  point at a shared OneDrive directory. Attachments are copied first and the
  envelope is published by a final same-directory rename, so a synced `.json`
  file is the complete-message marker.
- **Remote wakeup = recipient-local polling.** The packaged
  `mailbox-watcher` extension runs beside each Copilot session. It uses the
  tmux name when available, otherwise the live Copilot session name, and polls
  the unqualified mailbox plus its configured `name@machine` mailbox every two
  seconds. Qualified mail is mapped back to the ordinary local session name.
  New mail is bridged into the machine-local session-inbox request queue. Session-inbox
  heartbeats, claims, locks, receipts, and logs remain local and must not be
  placed in OneDrive.
- **Wakeup = short natural-language nudge through the recipient agent.** Sender
  writes the envelope, then `mailbox-poke.sh` resolves the recipient backend.
  Copilot sessions receive `check mailbox; skip if empty` as a real user turn
  through the plugin's `session-inbox` extension and immediate SDK
  `session.send()`. An active Copilot turn receives the nudge through its
  steering lane, while an idle session starts it normally. The extension does
  not wait for idle before submitting it. Claude and Codex retain the
  guarded terminal path:
  they require an initialized backend-specific footer and empty input box
  before the same marked prompt is entered. The shared parser in
  `skills/_lib/agent-pane.sh` detects the nearest recognized agent process in
  the pane's descendant tree and dispatches to a backend-specific parser. This
  handles Claude panes whose tmux command is only a version string and Codex
  panes launched through Node, without mistaking a nested reviewer subprocess
  for the pane's owning agent. A non-Copilot pane whose box or process identity
  cannot be recognized receives no keys at all. Before every Enter, it requires
  the box contents (including any visual wrapping in a narrow pane) to still
  equal that exact poke after display whitespace is normalized. It marks
  delivery only when that input becomes empty and the unique marker appears in
  the agent transcript. A
  shell, startup screen, changed input, or disappearing pane receives no
  further keys; the durable envelope waits for the resume hook. **NOT `/mailbox`
  as a slash command** — slash dispatch races cold-start skill
  loading and fails as "unknown command" before the snapshot is ready.
  **Recipient agent: when you receive the message "check mailbox; skip if
  empty" (or are otherwise invoked as the mailbox skill with no args), run
  `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh`.
  If it reports `no pending mail`, say nothing and continue with whatever you
  were doing — no visible turn output needed. If there IS mail, surface and act
  on it per the receive workflow.**
- **Resume-hook = the durable fallback.** If the recipient session is not
  running, the envelope remains in `pending/`. The watcher notices it after the
  computer syncs and a matching named Copilot session starts. Agent Stack may
  also call `mailbox-resume-hook.sh <name>` to include an immediate startup
  hint.

## Send (this session → another)

```sh
~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-send.sh <recipient-name> \
  --summary "<short title>" \
  --message "<free text — what is this, why send it>" \
  --file <path> [--file <path> ...]
```

Recipient name is the agent's live tmux name or Copilot `/rename` name (for
example, `juliett` or `kilo`). Attachments are copied rather than symlinked.
The script prints `wakeup: ... (verified | deferred | NOT verified | skipped)` so you know
whether the live wakeup landed; either way the envelope is durable.

The portable entry point, including on Windows, is:

```sh
node <plugin>/skills/mailbox/scripts/mailbox.mjs send <recipient-name[@machine]> \
  --summary "<short title>" \
  --message "<free text>" \
  --file <path>
```

The shell wrapper adds only the macOS notification and Claude/Codex tmux
fallback.

For a qualified remote recipient, the sender publishes the durable envelope but
does not wake a same-name session on the sender's computer. The recipient
machine's watcher delivers it after OneDrive sync. A nonmatching machine leaves
the envelope pending and cannot read or acknowledge it.

## Receive (this session got mail)

Three ways the receiver finds out:

1. **Wakeup prompt arrives as a user message.** When you see "check mailbox; skip if empty", or are otherwise invoked as the `mailbox` skill with no args, run `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh`. If it reports `no pending mail`, the wakeup was a stale race (mail was acked in the meantime) — say nothing and continue. If mail IS present, surface it.
2. **Resume-hook prepended to the session prompt.** When this happens you'll see "You have N unread mailbox envelope(s) ..." as part of your initial context. Run `mailbox-check.sh`.
3. **User says "check mail" / "any mailbox?"** Same response: run `mailbox-check.sh`.

Workflow once you know there's mail:

1. `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh` — list pending envelopes for this session. Outside tmux, use `node .../mailbox.mjs check --name <name>` or set `COPILOT_AGENT_NAME`.
2. `mailbox-read.sh <id>` — full message + attachment paths.
3. Surface summary + sender to the user concisely. Decide whether to act.
4. After acting (or skipping), `mailbox-ack.sh <id>` moves it to `delivered/`.

## Agent Stack integration

On macOS, set `MAILBOX_INTEGRATION="true"` in
`~/.config/remote-agent-stack/config`. Agent Stack calls `mailbox-poke.sh` with
the full backend-specific tmux session name when attaching or starting an
agent. Without this integration, mail still arrives durably but the recipient
will not notice until the user manually says "check mail".

## Pitfalls

- **Copilot wakeups use immediate native delivery.** Session-inbox submits the
  user message with SDK delivery mode `immediate`, so an active long-running or
  autopilot turn receives it as steering instead of leaving it stranded in the
  normal FIFO queue. Once `session.send()` returns a message ID, the watcher
  records the envelope as notified and does not retry it every polling cycle.
  The durable envelope remains pending until the recipient reads and
  acknowledges it. The immediate-delivery dedupe namespace is distinct from
  the retired queued-delivery namespace so pending envelopes created before
  0.108.9 receive one replacement nudge instead of replaying a cached
  `unconfirmed` result. During migration, a returned message ID or an `idle`,
  `queued`, or `steering` event from an older recipient extension also proves
  that replacement was accepted. Current senders use the
  `mailbox:immediate-v3` namespace and mark an envelope notified only after an
  `idle` or `steering` event. If the host temporarily places an immediate send
  in FIFO, session-inbox promotes that exact message into the steering lane;
  an unsteerable item is removed rather than left queued.
- **Claude and Codex wakeups remain fail-closed and best-effort.** Their poke
  requires a ready pane and verifies a transcript entry; otherwise rely on the
  osascript notification and resume hook.
- **Mailbox writeable by anyone with shell access.** Treat envelope contents as not-secret. Don't put credentials in messages or attachments.
- **No reply-thread bookkeeping.** If A sends to B and B wants to reply, B sends back to A's name. There's no thread-id linkage in v1.
- **Acked mail is moved, not deleted.** `delivered/` accumulates; periodically prune.
- **Do not sync `~/.copilot/session-inbox`.** A cloud file provider is not a
  distributed lock and can expose stale heartbeats or conflicting claims.
  Sync only `MAILBOX_ROOT`; keep `MAILBOX_STATE_ROOT` and session-inbox local.
- **One watcher owns each full mailbox address.** A configured session owns
  separate private locks for `hotel` and `hotel@surface-pro`. Duplicate Copilot
  sessions with the same `/rename` name still fail closed during local target
  resolution.
- **Sender and watcher share one notification claim.** Publishing a local
  envelope and the recipient's two-second watcher can notice the same mail at
  nearly the same time. A short machine-local claim under
  `MAILBOX_STATE_ROOT/notifying/` uses the full mailbox address, so only one
  path submits each route's SDK request while broadcast and qualified routes
  remain independent. The other path reports that notification is already in
  progress. Failed or abandoned claims are released or reclaimed, while the
  durable envelope remains pending.
- **Attachment stabilization must not erase notification state.** The watcher
  may temporarily exclude an envelope whose synced attachments have not yet
  remained unchanged for two polls. Marker cleanup compares against every
  pending envelope file, not only that poll's attachment-ready subset, so a
  valid sender-side notification survives until the envelope is acknowledged.
- **On a "check mailbox; skip if empty" wakeup, emit a REAL bash tool call** (proper function-call format) — never output literal `<invoke>` / XML-ish text as message content. Doing so makes the agent stall without ever running the check. If the current working directory's `readdir` is hanging (e.g. a OneDrive/File-Provider deadlock), `cd /tmp` first and list `~/.copilot/mailbox/<agent>/pending/` from there so the check can't hang on the cwd.

## Verification

- `mailbox-list.sh` — pending/delivered counts per mailbox + active tmux sessions.
- `mailbox-send.sh` reports `wakeup: ... (verified|deferred|NOT verified|skipped)` — `deferred` means a qualified remote envelope is durable but its machine watcher has not confirmed delivery; anything other than `verified` means rely on the resume-hook or human notification.
- `git -C ~/.copilot/skills status` clean after sending or receiving (mailbox queue lives at `~/.copilot/mailbox/`, not tracked in the skills repo).

## Scripts

- `scripts/mailbox-send.sh` — write envelope + copy attachments + best-effort recipient wakeup + osascript fallback.
- `scripts/mailbox-check.sh` — list pending for current session.
- `scripts/mailbox-read.sh <id>` — print full envelope + attachment paths.
- `scripts/mailbox-ack.sh <id>` — move pending → delivered.
- `scripts/mailbox-list.sh` — show all mailboxes + live tmux sessions.
- `scripts/mailbox-resume-hook.sh [<name>]` — designed to be called by the user's `ca` script to inject a "you have mail" hint into the resume prompt; prints empty when there's no mail.
- `scripts/mailbox-watch.sh [<name>]` — foreground portable poller; normally the packaged mailbox-watcher extension owns this automatically for Copilot.
- `scripts/mailbox.mjs` — cross-platform send/check/read/ack/list/resume-hint/poke/watch CLI.
- `scripts/mailbox-core.mjs` — reusable Node implementation used by the CLI and watcher extension.
