---
name: self-compact
description: Keep Copilot CLI working context lean while preserving decisions, active state, and session-bound resources through deliberate compaction. Use when a task finishes, work changes phase, a review round ends, tool history grows, the agent becomes stuck or repetitive, a durable work order enables a soft reset, or a long-lived session needs retirement.
---

# self-compact

Keep the working context small without losing the state needed to continue.
Choose the lightest reset that fits; cross-agent handoffs remain owned by
`handoff`.

## When to use

- A task, implementation phase, debugging phase, or review round has ended.
- A long run of tool calls has made earlier output more distracting than useful.
- Progress becomes repetitive, confused, or stuck.
- A durable plan is complete enough to replace the conversation.
- A resumed session has become old or slow.

## Prerequisites

- Copilot CLI.
- `tmux` and `$TMUX_PANE` for verified self-submission.
- The `handoff` skill for soft resets, `/new`, or session retirement.

## Quick start

Persist any state that exists only in conversation, then make this the final
tool action of the turn:

```sh
~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh \
  'Keep: <objective, decisions, current state, remaining work>. Drop: <resolved detail, superseded approaches, verbose output>.'
```

Outside tmux, give the user that `/compact` command to run directly.

## Procedure

### 1. Choose the compaction depth

- **Routine:** Keep the active objective, decisions, current state, and remaining
  work. Drop resolved detail and tool output.
- **Phase boundary:** Keep only the baton the next phase needs: durable artifact
  paths, branch, acceptance criteria, landed work, remaining work, and next
  action.
- **Soft reset:** When a durable artifact is a complete work order, invoke
  `handoff` for its null-steered `/compact` procedure. Keep session-bound
  schedules, SQL data, checkpoints, and files.
- **Session retirement:** When a multi-day session is slow or oversized, invoke
  `handoff` and `rotate-session` so a genuinely fresh session can recover the
  recorded state.

The chosen branch is complete when it preserves everything needed for the next
action without retaining resolved history. Prefer routine compaction after
landing work so the user can still ask why; reserve a soft reset for work that
already has a complete durable brief.

### 2. Persist load-bearing state

For active multi-step work, update the existing plan, design, issue, or other
durable artifact with:

- objective and acceptance criteria;
- decisions and non-goals;
- branch, relevant paths, and current runtime state;
- what landed versus what remains;
- blockers and the exact next action.

Do not create a planning document for a trivial completed task. Git state and
the resulting commit are sufficient when no unwritten decision or follow-up
would be lost.

This step is complete when deleting the conversation would not erase any fact
required to continue correctly.

### 3. Write an explicit steer

Use both halves in one line:

```text
Keep: <exhaustive load-bearing state>; Drop: <resolved investigation, superseded options, repeated explanations, and verbose tool output>.
```

Keep the baton concise: name durable artifact paths and the next action instead
of copying the artifact's contents into the steer.

`/compact` changes chat history only. It does not alter files, git state,
session SQL, schedules, checkpoints, or session artifacts.

This step is complete when every retained item earns its place in the next
phase and every named dropped item is safe to forget.

### 4. Submit and stop

Run `scripts/submit-compact.sh` as the final tool action, passing a single-line
steer. The script first builds:

```text
/compact <steer> Keep SCM:<8-hex-epoch>-<5-hex-pid>
```

It requires printable ASCII and preflights both the complete marked command and
continuation against the real pane width before workspace resolution, watcher
launch, run-file creation, Ctrl-S, or typing. The safe limit is
`pane_width - 4`; on a 68-column pane the fixed syntax leaves exactly 31 steer
columns. If either command cannot fit, shorten it or point to a shorter durable
artifact and run the helper again.

Before parsing input, the shared helper selects a UTF-8 locale by trying an
explicit `SELF_COMPACT_LOCALE` first, then `C.UTF-8`, `en_US.UTF-8`, and
`UTF-8`. It accepts a candidate only when `locale charmap` succeeds and reports
UTF-8, and awk can parse and remove Copilot's Unicode prompt prefix and
recognize a realistic multi-glyph divider. This rejects C/POSIX byte matching
and nonexistent locale names that silently fall back. The helper exports both
`LC_ALL` and `LANG`. If none passes, input remains unknown: the foreground
helper prints a clear error and sends no editor key. The helper then refreshes
every client
attached to the target tmux session, requires prompt text, stash footer state,
and cursor position to remain identical across three captures, and uses a
trapped one-column resize/restore pulse when the prompt remains unreadable. The
pulse restores tmux geometry and `window-size` inheritance and skips windows
linked into another session. Logical input capture preserves Copilot's prompt
rows structurally after removing only prompt syntax and captured right-padding.
Exact helper ownership requires exactly one captured prompt row, byte-for-byte
equal to the expected printable-ASCII command. Any second row or newline,
including a command-shaped boundary at a space or mid-token, is non-exact.
Unreadable input is always `unknown`, never empty, and explicit multiline input
remains nonempty.

Menu detection never scans transcript output. It considers only the four lines
immediately after the editor divider and requires nearby `↑/↓` navigation,
`Enter select`, and `Esc close/cancel/dismiss` signals together. Generic prose
such as `press esc to cancel` or `select an option` does not mark a menu visible.

The helper presses Ctrl-S once and classifies the observed transition. A visible
draft must become empty; a hidden draft that becomes visible is re-stashed with
one verified reverse toggle; and a truly empty editor must remain empty at the
same cursor position with no stash change. An inconclusive result is recaptured
without another toggle. If it remains inconclusive, tmux shows a 10-second
warning. A normally typed command that becomes non-exact uses the same grace
instead of being cleared immediately. After every literal typing, the helper
polls stable captures read-only for up to
`SELF_COMPACT_RENDER_WAIT_SECONDS` (5 seconds by default), with
`SELF_COMPACT_RENDER_POLL_SECONDS` available for deterministic tests. It
returns as soon as the one-row exact gate sees the command. Activity
is checked before every capture and sleep boundary; no Ctrl-S, Ctrl-U, Esc,
resize pulse, or other editor action occurs during the render window. New user
or assistant activity cancels recovery, and the activity check runs
immediately before every fallback Ctrl-U and Escape. In Copilot's multiline
editor, Ctrl-U clears only from the cursor to the start of the current logical
line; it does not clear prior logical lines. A readable nonempty multiline
residual is therefore not considered cleared. Recovery begins only after the
render window expires and remains bounded: Ctrl-U first, one Esc when recovery
requires it, and a second Esc only while the concrete nearby multi-signal menu
chrome remains visible. Unproven menu state never authorizes the second Esc;
the later exact gate fails closed if the first did not repair the editor.
Recovery still allows at most two command typings and best-effort cleanup. The
helper fails closed unless the exact helper command alone appears on one row,
and never presses Enter on a multiline residual.

Before submitting, the script starts a detached watcher against the active
session's `summary_count`, event position, and a unique checkpoint marker. The
concise `SCM:` marker remains directly greppable in the checkpoint and run
filenames/logs retain their existing timestamp/PID identity. The
watcher command receives the verified locale explicitly because
`tmux run-shell -b` can start on macOS without `LANG` or `LC_ALL`; the watcher
verifies that locale again before parsing. Locale failure and other unexpected
watcher failures remain log-only and cannot create a tmux crash overlay.
The watcher accepts `session.compaction_start` before the submitting
`assistant.turn_end` or within 15 seconds afterward, with a final event read
at deadline expiry. If no start arrives, it
clears only an exactly readable helper-authored command, shows a one-line tmux
failure notice, and exits. A different draft or unreadable buffer is untouched.
Detached exit status is also log-only.

After the marked compact advances `summary_count`, the watcher exits on any
recorded failed compaction and checks for post-compact activity. If none exists,
the watcher first rechecks that `proceed` still fits the current pane, then the
same bounded helper prepares it with event checks before every Esc, before
typing, before every render-poll capture or sleep, and immediately before
Enter. Both callers use the same render wait for a fresh stable one-row exact
capture at the final Enter gate. Activity always wins; no Esc is sent after it
appears. The stashed draft returns after the continuation turn on the normal
readable path. Selected autopilot mode is not assumed to be a reliable wakeup,
and the watcher remains one-shot.

After the helper reports that the compact was submitted and the watcher armed,
end the turn. Its log is written under the active session's `files/` directory.

When `$TMUX_PANE` is unavailable, print the exact steered `/compact` command for
the user instead of claiming it ran. If pane-width preflight rejects either
command, shorten the steer or continuation by pointing to the durable artifact
and run it again as the final action.

This step is complete when the compact submission and watcher are both armed, or
the user has the exact compact command and knows to send `proceed` after it
finishes. A watcher failure after compaction is recorded in its log; send
`proceed` manually rather than rerunning the helper and queuing a second compact.

## Pitfalls

- A vague steer preserves noise and may discard the real baton.
- Conversation-only plans can silently narrow during compaction.
- Repeating a complete durable plan in the steer can exceed the visible input;
  reference its path instead.
- A soft reset immediately after landing erases useful rationale the user may
  still want to question.
- Plain text submitted while the agent is active becomes steering and can run
  before a queued `/compact`; continuation must wait for that compact's unique
  checkpoint marker and `summary_count` advance.
- If the TUI stays unreadable after the Ctrl-S transition and redraw pulse, the
  visible warning protects a bounded destructive fallback, not guaranteed draft
  preservation. Copy or submit an important draft during that 10-second grace.
- Ctrl-U is line-local in Copilot's multiline editor. If prior logical lines
  remain visible, exact verification rejects the buffer and recovery ends
  without Enter.
- tmux cannot distinguish a Copilot-drawn continuation row from a real logical
  newline. Never reconstruct row boundaries. Keep both commands within the
  preflighted one-row limit and reject every additional captured row.
- A freshly typed literal may remain absent from several otherwise stable
  captures. Do not classify those stale empty frames as a mismatch before the
  bounded read-only render window expires.
- A real detached `tmux run-shell -b` shell can have only `HOME` and a minimal
  `PATH`, with no locale variables. Never parse the Unicode prompt or divider
  until the requested locale reports a UTF-8 charmap and awk passes the
  multi-glyph probe; never fall back to `C`.
- Ordinary transcript text can mention Esc or selection. Never infer menu state
  from it; only concrete nearby multi-signal menu chrome can authorize the
  second Esc.
- Autopilot can remain visibly selected without generating a post-compact turn.
- `/new` strands session-bound state; use it only when preserving the old
  conversation matters.
- `/clear` destroys session state rather than cleaning working context.

## Verification

- Load-bearing state exists outside the conversation when needed.
- The steer names both what survives and what disappears.
- The helper reports `submitted compact; post-compact continuation watcher
  armed`, names its log, and no later tool call runs in that turn.
- Candidate-development note: long-row reconstruction and the prior long
  Sierra lifecycle were discovery experiments, not final acceptance. A logical
  newline can produce the same capture, so the final supported path is
  printable ASCII, concise `SCM:` syntax, pane-width preflight, and exactly one
  captured row at every ownership/Enter/cleanup gate. The previous live receipt
  is stale after this executable safety redesign; rerun the complete marked
  compact, checkpoint, continuation, draft restoration, watcher teardown, and
  geometry scenario before landing.
