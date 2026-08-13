---
name: mailbox
description: Hand a file or message to another named Copilot CLI session in a different tmux pane. Use when this session has produced a deliverable another named agent should pick up, or the user says to send something to an agent by name (e.g. "send this to juliett"). Requires macOS + tmux.
---

# mailbox

Cross-session message + file handoff, keyed by tmux session name.

## When to use

- User says "send this to <name>", "hand this off to <name>", "deliver X to <name>".
- You have produced a concrete artifact (file, doc, summary) for another named agent session to consume.
- You want to delegate a task to another live tmux-resident Copilot session.

Do NOT use mailbox for:
- Self-talk inside the same session (just write to disk normally).
- Notifying a non-Copilot terminal (osascript notification suffices).
- Heavy bidirectional RPC. This is one-shot delivery, not a chat protocol.

## How it works

- **Identity = tmux session name.** No registry. The user's `ca <name>` script opens or resumes a tmux session named `<name>` running Copilot CLI; that tmux session name IS the agent's name. Sender: `tmux display-message -p '#{session_name}'` to learn its own. Recipient: same.
- **Transport = file queue.** Envelopes land at `~/.copilot/mailbox/<recipient>/pending/<id>.json` with attachments in a sibling `<id>/` directory. Durable, debuggable with `ls`.
- **Wakeup = short natural-language nudge via tmux send-keys.** Sender writes
  the envelope, then `mailbox-poke.sh` resolves the recipient pane and requires
  a live `copilot` process, initialized Copilot footer, and empty `❯` input
  prompt before sending `check mailbox; skip if empty` with the envelope ID as
  a delivery marker. Before every Enter, it requires the bottommost input line
  to still equal that exact poke. It marks delivery only when that input becomes
  empty and the uniquely marked prompt appears in the Copilot transcript. A
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

1. **Wakeup prompt arrives as a user message** (sender did send-keys with "check mailbox; skip if empty"). When you see this prompt, or are otherwise invoked as the `mailbox` skill with no args, run `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh`. If it reports `no pending mail`, the wakeup was a stale race (mail was acked in the meantime) — say nothing and continue. If mail IS present, surface it.
2. **Resume-hook prepended to the session prompt.** When this happens you'll see "You have N unread mailbox envelope(s) ..." as part of your initial context. Run `mailbox-check.sh`.
3. **User says "check mail" / "any mailbox?"** Same response: run `mailbox-check.sh`.

Workflow once you know there's mail:

1. `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh` — list pending envelopes for this session.
2. `mailbox-read.sh <id>` — full message + attachment paths.
3. Surface summary + sender to the user concisely. Decide whether to act.
4. After acting (or skipping), `mailbox-ack.sh <id>` moves it to `delivered/`.

## ca-script integration

The user is expected to wire the resume-hook into their `ca` agent-launcher:

```sh
# inside ca <name>, just before exec'ing copilot:
HINT="$(~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-resume-hook.sh "$NAME" 2>/dev/null || true)"
copilot --resume "$SESSION_ID" ${HINT:+--prompt "$HINT"}
```

Without this hook, mail still arrives durably but the recipient won't notice until the user manually says "check mail".

## Pitfalls

- **Live mid-generation wakeup is fail-closed but still best-effort.** Do not
  assume send-keys lands. The poke requires a ready Copilot pane and verifies a
  transcript entry; otherwise rely on the osascript notification and resume
  hook. Never send wakeup keys merely because the tmux session exists.
- **Mailbox writeable by anyone with shell access.** Treat envelope contents as not-secret. Don't put credentials in messages or attachments.
- **No reply-thread bookkeeping.** If A sends to B and B wants to reply, B sends back to A's name. There's no thread-id linkage in v1.
- **Acked mail is moved, not deleted.** `delivered/` accumulates; periodically prune.
- **On a "check mailbox; skip if empty" wakeup, emit a REAL bash tool call** (proper function-call format) — never output literal `<invoke>` / XML-ish text as message content. Doing so makes the agent stall without ever running the check. If the current working directory's `readdir` is hanging (e.g. a OneDrive/File-Provider deadlock), `cd /tmp` first and list `~/.copilot/mailbox/<agent>/pending/` from there so the check can't hang on the cwd.

## Verification

- `mailbox-list.sh` — pending/delivered counts per mailbox + active tmux sessions.
- `mailbox-send.sh` reports `wakeup: ... (verified|NOT verified|skipped)` — anything other than `verified` means rely on the resume-hook or human notification.
- `git -C ~/.copilot/skills status` clean after sending or receiving (mailbox queue lives at `~/.copilot/mailbox/`, not tracked in the skills repo).

## Scripts

- `scripts/mailbox-send.sh` — write envelope + copy attachments + best-effort send-keys wakeup with verification poll + osascript fallback.
- `scripts/mailbox-check.sh` — list pending for current session.
- `scripts/mailbox-read.sh <id>` — print full envelope + attachment paths.
- `scripts/mailbox-ack.sh <id>` — move pending → delivered.
- `scripts/mailbox-list.sh` — show all mailboxes + live tmux sessions.
- `scripts/mailbox-resume-hook.sh [<name>]` — designed to be called by the user's `ca` script to inject a "you have mail" hint into the resume prompt; prints empty when there's no mail.
