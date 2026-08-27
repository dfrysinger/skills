---
name: mailbox
description: Hand a file or message to another named Copilot CLI, Claude Code, or Codex CLI session in a different tmux pane. Use when this session has produced a deliverable another named agent should pick up, or the user says to send something to an agent by name (e.g. "send this to juliett"). Requires macOS + tmux.
---

# mailbox

Cross-session message + file handoff, keyed by tmux session name.

## When to use

- User says "send this to <name>", "hand this off to <name>", "deliver X to <name>".
- You have produced a concrete artifact (file, doc, summary) for another named agent session to consume.
- You want to delegate a task to another live tmux-resident Copilot, Claude, or Codex session.

Do NOT use mailbox for:
- Self-talk inside the same session (just write to disk normally).
- Notifying a terminal that is not a recognized agent CLI (osascript notification suffices).
- Heavy bidirectional RPC. This is one-shot delivery, not a chat protocol.

## How it works

- **Identity = tmux session name.** No registry. Agent Stack opens or resumes a backend-specific tmux session; that full tmux session name IS the agent's mailbox name. Copilot uses `<name>`, Claude uses `claude-<name>`, and Codex uses `codex-<name>`. Sender: `tmux display-message -p '#{session_name}'` to learn its own. Recipient: same.
- **Transport = file queue.** Envelopes land at `~/.copilot/mailbox/<recipient>/pending/<id>.json` with attachments in a sibling `<id>/` directory. Durable, debuggable with `ls`.
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
- **Resume-hook = the durable fallback.** If the recipient session isn't running yet, the wakeup is skipped and the envelope sits durably in pending/. The user's `ca <name>` script should call `mailbox-resume-hook.sh <name>` before launching Copilot to inject a "you have N unread" hint into the resume prompt.

## Send (this session → another)

```sh
~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-send.sh <recipient-name> \
  --summary "<short title>" \
  --message "<free text — what is this, why send it>" \
  --file <path> [--file <path> ...]
```

Recipient name is the tmux session name (e.g., `juliett`, `kilo`). Attachments are copied (not symlinked). The script prints `wakeup: ... (verified | NOT verified | skipped)` so you know whether the live wakeup landed; either way the envelope is durable.

## Receive (this session got mail)

Three ways the receiver finds out:

1. **Wakeup prompt arrives as a user message.** When you see "check mailbox; skip if empty", or are otherwise invoked as the `mailbox` skill with no args, run `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh`. If it reports `no pending mail`, the wakeup was a stale race (mail was acked in the meantime) — say nothing and continue. If mail IS present, surface it.
2. **Resume-hook prepended to the session prompt.** When this happens you'll see "You have N unread mailbox envelope(s) ..." as part of your initial context. Run `mailbox-check.sh`.
3. **User says "check mail" / "any mailbox?"** Same response: run `mailbox-check.sh`.

Workflow once you know there's mail:

1. `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh` — list pending envelopes for this session.
2. `mailbox-read.sh <id>` — full message + attachment paths.
3. Surface summary + sender to the user concisely. Decide whether to act.
4. After acting (or skipping), `mailbox-ack.sh <id>` moves it to `delivered/`.

## Agent Stack integration

Set `MAILBOX_INTEGRATION="true"` in
`~/.config/remote-agent-stack/config`. Agent Stack calls `mailbox-poke.sh` with
the full backend-specific tmux session name when attaching or starting an
agent. Without this integration, mail still arrives durably but the recipient
will not notice until the user manually says "check mail".

## Pitfalls

- **Copilot wakeups wait for idle.** The extension checks
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
