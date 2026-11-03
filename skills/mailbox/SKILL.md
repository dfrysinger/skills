---
name: mailbox
description: Hand a file or message to another named Copilot CLI, Claude Code, or Codex CLI session. Use when this session has produced a deliverable another named agent should pick up, or the user says to send something to an agent by name (e.g. "send this to juliett"). Addresses distinguish providers and computers; managed Windows sessions use provider-native wakeups, while macOS tmux remains a compatibility path.
---

# mailbox

Cross-session and cross-computer message + file handoff, keyed by provider,
agent name, and optional machine.

## When to use

- User says "send this to <name>", "hand this off to <name>", "deliver X to <name>".
- You have produced a concrete artifact (file, doc, summary) for another named agent session to consume.
- You want to delegate a task to another live Copilot, Claude, or Codex session.

Do NOT use mailbox for:
- Self-talk inside the same session (just write to disk normally).
- Notifying a terminal that is not a recognized agent CLI (osascript notification suffices).
- Heavy bidirectional RPC. This is one-shot delivery, not a chat protocol.

## How it works

- **Identity = `[provider:]name[@machine]`.** Providers are `copilot`,
  `claude`, and `codex`; an omitted provider means Copilot for compatibility.
  `alpha`, `claude:alpha`, and `codex:alpha` are independent local mailboxes.
  Add `@machine` only for cross-computer transport, such as
  `codex:alpha@surface-pro`. Agent Stack exports the exact
  `MAILBOX_SELF_ADDRESS` for every managed process. Invalid explicit identity
  fails closed rather than falling back to another provider. On macOS, a live
  tmux session name remains
  the first choice so existing Agent Stack sessions keep their established
  identity. When no live tmux identity matches, Copilot falls back to the
  session's current `/rename` name. Only fresh session-inbox heartbeats are
  eligible, so abandoned historical sessions with the same name are ignored.
  On Windows, use `copilot-agent <name>` after placing
  `scripts/copilot-agent.cmd` on `PATH`, or call
  `scripts/copilot-agent.ps1 <name>` directly. The shorthand automatically
  creates or resumes the deterministic session, enables `--allow-all-tools`,
  and runs one interactive initialization turn so the mailbox watcher is
  active. Explicit `new|resume|open <name>` modes remain available. The
  launcher
  deterministically maps the
  canonical lowercase `(COPILOT_AGENT_MACHINE, name)` pair to one exact
  Copilot session UUID. `new` creates that UUID with the native name; `resume`
  uses the exact UUID, so historical sessions with the same display name are
  not ambiguous. Set `COPILOT_AGENT_MACHINE` explicitly before launch. Names
  are lowercase mailbox-safe values up to 100 characters; machine labels use
  the same lowercase characters up to 128. The wrapper follows `COPILOT_HOME`
  and refuses identity or config-store flags in its extra arguments. The
  interactive `/rename <name>` command changes an already running session but
  does not migrate it into the deterministic launcher identity. Portable
  mailbox commands also accept `--name` or `COPILOT_AGENT_NAME`. On non-Windows
  hosts outside tmux, use Copilot's native `--name` for a new session or
  `/rename <name>` for a running session; resume by exact session ID when
  historical names are ambiguous.
- **Cross-computer address includes `@machine`.** An address without a machine
  suffix means this computer only. There is no implicit broadcast or
  cross-machine aggregation. Set the stable machine label with
  `COPILOT_AGENT_MACHINE`; there is no hostname fallback.
- **Local mailbox = mutable delivery state.** Unqualified envelopes land at
  `$MAILBOX_LOCAL_ROOT/<recipient>/pending/<id>.json`, with attachments in a
  sibling `<id>/` directory. `MAILBOX_LOCAL_ROOT` defaults to
  `~/.copilot/mailbox`; legacy `MAILBOX_ROOT` remains a fallback for local-only
  configurations. Reading, notification markers, watcher locks, retries, and
  pending-to-delivered acknowledgement all stay on the local disk.
- **Remote transport = immutable files.** Qualified envelopes are first staged
  under   `MAILBOX_STATE_ROOT/remote-outbox`, then copied to the provider-qualified
  address path under `$MAILBOX_REMOTE_ROOT`. Attachments are published
  before the envelope. Published files are never edited, renamed, or deleted
  by delivery or acknowledgement. The recipient imports a complete remote
  envelope into its ordinary unqualified local mailbox and later publishes a
  separate immutable receipt under `$MAILBOX_REMOTE_ROOT/receipts/`.
- **Remote wakeup = recipient-local polling.** Each native watcher polls its
  exact local provider address plus the matching provider-qualified
  `@machine` import address. Qualified mail is copied into the ordinary local
  provider mailbox before notification.
  New mail is bridged into the machine-local session-inbox request queue. Session-inbox
  heartbeats, claims, locks, receipts, and logs remain local and must not be
  placed in OneDrive.
- **Wakeup = short natural-language nudge through the recipient agent.** Sender
  writes the envelope, then `mailbox-poke.sh` resolves the recipient backend.
  Copilot sessions receive `check mailbox; skip if empty` as a real user turn
  through the plugin's `session-inbox` extension and immediate SDK
  `session.send()`. An active Copilot turn receives the nudge through its
  steering lane, while an idle session starts it normally. The extension does
  not wait for idle before submitting it. Agent Stack-managed Windows Claude
  sessions receive the same fixed nudge through Claude's authenticated
  messaging pipe. Managed Windows Codex sessions receive it through their
  launch-scoped authenticated loopback app-server, using exact thread and turn
  identity. Neither Windows adapter injects terminal input. On macOS, Claude
  and Codex retain the guarded terminal compatibility path:
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

Use a bare Copilot name or an explicit provider-qualified address, for example
`juliett`, `claude:kilo`, or `codex:alpha@surface-pro`. Attachments are copied
rather than symlinked. The script prints the structured wakeup outcome; either
way the envelope is durable until acknowledged.

The portable entry point, including on Windows, is:

```sh
node <plugin>/skills/mailbox/scripts/mailbox.mjs send <[provider:]name[@machine]> \
  --summary "<short title>" \
  --message "<free text>" \
  --file <path>
```

The shell wrapper adds only the macOS notification and guarded terminal
compatibility fallback.

For a qualified remote recipient, the sender stages the durable envelope
locally and attempts to publish it to `MAILBOX_REMOTE_ROOT`. A publication
failure leaves the local outbox intact for the watchers' later retries. The
sender does not wake a same-name session on its own computer. The recipient
machine's watcher imports it after OneDrive sync, then wakes the unqualified
local session. A nonmatching machine cannot import it. Local `check`, `read`,
and `ack` commands never operate directly on the shared transport.

## Receive (this session got mail)

Three ways the receiver finds out:

1. **Wakeup prompt arrives as a user message.** When you see "check mailbox; skip if empty", or are otherwise invoked as the `mailbox` skill with no args, run `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh`. If it reports `no pending mail`, the wakeup was a stale race (mail was acked in the meantime) — say nothing and continue. If mail IS present, surface it.
2. **Resume-hook prepended to the session prompt.** When this happens you'll see "You have N unread mailbox envelope(s) ..." as part of your initial context. Run `mailbox-check.sh`.
3. **User says "check mail" / "any mailbox?"** Same response: run `mailbox-check.sh`.

Workflow once you know there's mail:

1. `~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/mailbox/scripts/mailbox-check.sh` — list pending envelopes for this session. Outside tmux, use `node .../mailbox.mjs check --name <[provider:]name>` or set `MAILBOX_SELF_ADDRESS`.
2. `mailbox-read.sh <id>` — full message + attachment paths.
3. Surface summary + sender to the user concisely. Decide whether to act.
4. After acting (or skipping), `mailbox-ack.sh <id>` moves it to `delivered/`.

## Agent Stack integration

Set `MAILBOX_INTEGRATION="true"` in
`~/.config/remote-agent-stack/config`. Agent Stack calls `mailbox-poke.sh` with
the full backend-specific identity when attaching or starting an agent. On
Windows it launches provider-native Claude and Codex watchers and exports
`MAILBOX_SELF_ADDRESS`. Without this integration, mail still arrives durably
but the recipient will not notice until the user manually says "check mail".

For cross-computer delivery, also configure:

```sh
MAILBOX_LOCAL_ROOT="$HOME/.copilot/mailbox"
MAILBOX_REMOTE_ROOT="/path/to/OneDrive/copilot-mailbox"
COPILOT_AGENT_MACHINE="<stable-machine-label>"
```

Persist the machine route once so direct Copilot restarts do not depend on
inheriting those shell exports:

```sh
node <plugin>/skills/mailbox/scripts/mailbox.mjs configure \
  --machine "<stable-machine-label>" \
  --remote-root "/path/to/OneDrive/copilot-mailbox"
```

The command writes `~/.copilot/mailbox-config.json`. Environment variables
still override the persisted machine and remote root for an explicit process.

## Pitfalls

- **Copilot wakeups use immediate native delivery.** Session-inbox submits the
  user message with SDK delivery mode `immediate`, so an active long-running or
  autopilot turn receives it as steering instead of leaving it stranded in the
  normal FIFO queue. The watcher marks the envelope notified only after an
  `idle` or `steering` event; a returned message ID or `unconfirmed` result is
  not enough. Each delivery attempt uses an attempt-scoped
  `mailbox:immediate-v3` dedupe key. Caller timeouts reuse that key so a still
  running recovery cannot race a duplicate send. A durable ambiguous receipt
  preserves that key and writes a local `.unverified` marker, so later watcher
  polls do not generate duplicate native turns. A newer envelope remains
  independently wakeable, and a later confirmed wake marks every ready pending
  envelope notified.
  The durable envelope remains pending until the recipient reads and
  acknowledges it. If the host temporarily places an immediate send in FIFO,
  session-inbox snapshots the queue before submission and promotes only the
  single exact matching item that appeared afterward. An owned but unsteerable
  item is removed rather than left queued; ambiguous ownership leaves every
  queued item untouched. On macOS, only a receipt that explicitly proves the
  item was removed with no side effect may retry through the same guarded tmux
  input verification used for other terminal agents. This fallback never runs
  for an ambiguous send, a rotation barrier, or a missing/unrecognized pane,
  and it still requires the exact prompt to appear in the transcript before
  marking the envelope notified.
- **Wakeup outcomes are truthful and fail closed.** `verified` is reserved for
  an acknowledged native delivery. `submitted`, `held`, `refused`, and
  `ambiguous` are durable terminal outcomes for that exact attempt and do not
  replay automatically. `deferred` writes no terminal marker and may retry.
  Claude and Codex Windows transports currently prove submission, not provider
  execution, so success is reported as `submitted`. Missing integration or an
  unmanaged provider session remains queued with managed-relaunch or upgrade
  guidance.
- **Codex remote permissions are set by `turn/start`.** Codex rejects
  permission-override flags on a remote TUI resume. When Agent Stack
  `ALLOW_ALL` is true, the native watcher starts an idle mailbox turn with
  approval policy `never` and sandbox policy `dangerFullAccess`; Codex applies
  that policy to the turn and subsequent turns. Steering an already active
  turn keeps that turn's existing permission policy.
- **Mailbox writeable by anyone with shell access.** Treat envelope contents as not-secret. Don't put credentials in messages or attachments.
- **No reply-thread bookkeeping.** If A sends to B and B wants to reply, B sends back to A's name. There's no thread-id linkage in v1.
- **Acked mail is moved, not deleted.** `delivered/` accumulates; periodically prune.
- **Do not sync local mailbox or session state.** A cloud file provider is not
  a distributed lock and can expose stale heartbeats, conflicting claims, or
  partial mutable state. Keep `MAILBOX_LOCAL_ROOT`, `MAILBOX_STATE_ROOT`, and
  session-inbox local. Only `MAILBOX_REMOTE_ROOT` belongs in OneDrive.
- **One watcher owns each local or import route.** A configured session owns
  separate local locks for `hotel` delivery and `hotel@surface-pro` import.
  Duplicate Copilot
  sessions with the same `/rename` name still fail closed during local target
  resolution.
- **Sender and watcher share one notification claim.** Publishing a local
  envelope and the recipient's two-second watcher can notice the same mail at
  nearly the same time. A short machine-local claim under
  `MAILBOX_STATE_ROOT/notifying/` uses the full mailbox address, so only one
  path submits each local SDK request. The other path reports that notification
  is already in progress. Claims carry random ownership IDs; a live owner is
  never reclaimed by age alone, and an older owner cannot remove a successor's
  claim. Dead or released claims may be reclaimed while the durable envelope
  remains pending.
- **Attachment stabilization must not erase notification state.** The watcher
  may temporarily exclude an envelope whose synced attachments have not yet
  remained unchanged for two polls. Marker cleanup compares against every
  pending envelope file, not only that poll's attachment-ready subset, so a
  valid sender-side notification survives until the envelope is acknowledged.
- **On a "check mailbox; skip if empty" wakeup, emit a REAL bash tool call** (proper function-call format) — never output literal `<invoke>` / XML-ish text as message content. Doing so makes the agent stall without ever running the check. If the current working directory's `readdir` is hanging (e.g. a OneDrive/File-Provider deadlock), `cd /tmp` first and list `~/.copilot/mailbox/<agent>/pending/` from there so the check can't hang on the cwd.

## Verification

- `mailbox-list.sh` — pending/delivered counts per mailbox + active tmux sessions.
- `mailbox-send.sh` reports the structured outcome (`verified`, `submitted`,
  `held`, `refused`, `ambiguous`, or `deferred`). The envelope remains durable
  until the recipient acknowledges it.
- `git -C ~/.copilot/skills status` clean after sending or receiving (mailbox queue lives at `~/.copilot/mailbox/`, not tracked in the skills repo).

## Scripts

- `scripts/mailbox-send.sh` — write envelope + copy attachments + best-effort recipient wakeup + osascript fallback.
- `scripts/mailbox-check.sh` — list pending for current session.
- `scripts/mailbox-read.sh <id>` — print full envelope + attachment paths.
- `scripts/mailbox-ack.sh <id>` — move pending → delivered.
- `scripts/mailbox-list.sh` — show all mailboxes + live tmux sessions.
- `scripts/mailbox-resume-hook.sh [<name>]` — designed to be called by the user's `ca` script to inject a "you have mail" hint into the resume prompt; prints empty when there's no mail.
- `scripts/mailbox-watch.sh [<name>]` — foreground portable poller; normally the packaged mailbox-watcher extension owns this automatically for Copilot.
- `scripts/copilot-agent.ps1 [new|resume|open] <name> [copilot args...]` — deterministic Windows launcher; shorthand `<name>` auto-creates/resumes with allow-all and initializes the mailbox listener.
- `scripts/copilot-agent.cmd <name> [copilot args...]` — PATH-friendly Windows command shim for the installed launcher.
- `scripts/mailbox.mjs` — cross-platform send/check/read/ack/list/resume-hint/poke/watch CLI.
- `scripts/mailbox-core.mjs` — reusable Node implementation used by the CLI and watcher extension.
