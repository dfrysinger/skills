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
- **Transport = file queue.** Envelopes land at
  `$MAILBOX_ROOT/<recipient>/pending/<id>.json`, with attachments in a sibling
  `<id>/` directory. `MAILBOX_ROOT` defaults to `~/.copilot/mailbox` and may
  point at a shared OneDrive directory. Attachments are copied first and the
  envelope is published by a final same-directory rename, so a synced `.json`
  file is the complete-message marker.
- **Remote wakeup = recipient-local polling.** The packaged
  `mailbox-watcher` extension runs beside each Copilot session. It uses the
  tmux name when available, otherwise the live Copilot session name, and polls
  that mailbox's shared `pending/` directory every two seconds. New mail is
  bridged into the machine-local session-inbox request queue. Session-inbox
  heartbeats, claims, locks, receipts, and logs remain local and must not be
  placed in OneDrive.
- **Wakeup = short natural-language nudge through the recipient agent.** Sender
  writes the envelope, then `mailbox-poke.sh` resolves the recipient backend.
  Copilot sessions receive `check mailbox; skip if empty` as a real user turn
  through the plugin's `session-inbox` extension and SDK `session.send()` after
  the session reaches idle. Claude and Codex retain the guarded terminal path:
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
The script prints `wakeup: ... (verified | NOT verified | skipped)` so you know
whether the live wakeup landed; either way the envelope is durable.

The portable entry point, including on Windows, is:

```sh
node <plugin>/skills/mailbox/scripts/mailbox.mjs send <recipient-name> \
  --summary "<short title>" \
  --message "<free text>" \
  --file <path>
```

The shell wrapper adds only the macOS notification and Claude/Codex tmux
fallback.

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

- **Copilot wakeups wait for idle.** The unchanged session-inbox extension checks
  `session.rpc.metadata.isProcessing()` and `metadata.activity()`, but those
  snapshots are only secondary guards: it will not send until the runtime has
  emitted `session.idle`. It then requires the resulting `user.message` event
  to report `delivery: "idle"` before writing a successful receipt. A timed-out
  request remains durable and is deduplicated by mailbox envelope ID if a
  later poke retries it.
- **Claude and Codex wakeups remain fail-closed and best-effort.** Their poke
  requires a ready pane and verifies a transcript entry; otherwise rely on the
  osascript notification and resume hook.
- **Mailbox writeable by anyone with shell access.** Treat envelope contents as not-secret. Don't put credentials in messages or attachments.
- **No reply-thread bookkeeping.** If A sends to B and B wants to reply, B sends back to A's name. There's no thread-id linkage in v1.
- **Acked mail is moved, not deleted.** `delivered/` accumulates; periodically prune.
- **Do not sync `~/.copilot/session-inbox`.** A cloud file provider is not a
  distributed lock and can expose stale heartbeats or conflicting claims.
  Sync only `MAILBOX_ROOT`; keep `MAILBOX_STATE_ROOT` and session-inbox local.
- **One watcher owns one local name.** A private local lock under
  `MAILBOX_STATE_ROOT` prevents two watcher processes from repeatedly notifying
  the same agent. Duplicate Copilot sessions with the same `/rename` name fail
  closed during target resolution.
- **On a "check mailbox; skip if empty" wakeup, emit a REAL bash tool call** (proper function-call format) — never output literal `<invoke>` / XML-ish text as message content. Doing so makes the agent stall without ever running the check. If the current working directory's `readdir` is hanging (e.g. a OneDrive/File-Provider deadlock), `cd /tmp` first and list `~/.copilot/mailbox/<agent>/pending/` from there so the check can't hang on the cwd.

## Verification

- `mailbox-list.sh` — pending/delivered counts per mailbox + active tmux sessions.
- `mailbox-send.sh` reports `wakeup: ... (verified|NOT verified|skipped)` — anything other than `verified` means rely on the resume-hook or human notification.
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
