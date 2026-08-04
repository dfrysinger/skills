---
name: handoff
description: Compact the current conversation into a structured handoff document for another agent — or for a fresh instance of yourself — to pick up where this one left off. Use when the user says "hand off to <name>", "do a handoff", "summarize this session for another agent", wants to pass work to a different Copilot CLI session, or when the `self-compact` rule calls for a self-handoff (a null-steered soft-reset `/compact`, or `/new`). If a recipient is named (e.g., "hand off to juliett"), the skill auto-delivers via the mailbox skill after writing the doc.
argument-hint: "What will the next session be used for? Optionally include a recipient name (e.g., 'send to juliett about X') to auto-deliver via the mailbox skill, or say 'self' to restart yourself fresh."
---

# handoff

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save to the temporary directory of the user's OS - not the current workspace.

Include a "suggested skills" section in the document, which suggests skills that the agent should invoke.

Do not duplicate content already captured in other artifacts (PRDs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

For work that spans multiple sessions, persist durable goals and plans to a committed repo doc (e.g. `docs/<feature>-plan.md`), not just the conversation or session checkpoints — context compaction can otherwise silently narrow the scope. Reference that doc from the handoff.

Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.

## Automated delivery to another agent session (optional)

If the user names a recipient session ("send to juliett", "hand this to kilo", "deliver to alpha", etc.) AND the `mailbox` skill is available, after writing the handoff document automatically dispatch it via mailbox so the recipient agent picks it up without manual file passing:

```sh
~/.copilot/skills/mailbox/scripts/mailbox-send.sh <recipient> \
  --summary "handoff: <one-line topic>" \
  --message "Continuing <topic>. Read the attached handoff doc, then resume." \
  --file <path-to-handoff-doc>
```

The recipient's mailbox skill will surface this on its next `/mailbox` dispatch (immediate if their tmux session is running, on next `ca <recipient>` if they're cold). Tell the user: "Handoff sent to <recipient> — they'll see it on their next turn."

If the user did NOT name a recipient, do not invoke mailbox; just write the doc and report the path so the user can hand it off manually or via `/mailbox` themselves.

## Self-handoff: restart yourself fresh (optional)

Use this when a durable artifact — a design doc, plan, or autopilot brief — has
become a complete work order for what comes next, so the conversation that
produced it no longer earns its context. Also use it when compacting has stopped
helping and a clean slate would serve better than another `/compact`. After
landing work, stay in the conversation instead: the user may want to interrogate
what shipped and why. A self-handoff writes the handoff doc, then starts a fresh
conversation that reads the doc and continues.

There are two ways to restart. **Prefer the soft reset** — it gives you the same
clean slate without losing anything.

### Soft reset (preferred): a null-steered `/compact`

The compaction steer has total authority over what the summary contains, so a
steer that preserves nothing empties the conversation as thoroughly as `/new`
would — while keeping the **same session**, so armed schedules, the SQL
database, `plan.md`, `checkpoints/`, and `files/` all survive.

The summary is context, not a turn, so compaction alone will not wake you. Write
the summary as a **standing brief** and use `self-compact`'s helper with a custom
continuation. It arms a watcher before queuing the compact, then waits for the
session's `summary_count` to prove compaction landed before submitting the next
turn:

```sh
~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh \
  --continuation 'continue' \
  'Discard the entire conversation — no history, no tool output, no decisions. Output as the ENTIRE summary exactly: STANDING BRIEF — Read <handoff-path> and <plan-doc-path>, then continue that work. Re-invoke <skills>.'
```

Then end the turn. Caveats: this overwrites the live conversation in place, so
unlike `/new` there is no old session to resume; and the command lands at the
**next turn boundary**, so end your turn to let it run rather than continuing to
make tool calls. The helper's watcher, not selected autopilot mode, owns the
post-compact wakeup.

### `/new` (exception): when the old conversation must survive

Use `/new` only when you want the old conversation preserved as a separately
resumable session — for example, when the user may still want to interrogate it.
It keeps the same tmux window and Copilot process, but starts a **new session**
and backgrounds the old one, so the fresh conversation loses:

- any armed schedules (`/every` reminders stay bound to the old session);
- the session SQL database (the `todos` table and any custom tables);
- the session `plan.md`, `checkpoints/`, and `files/`.

So before restarting, persist every load-bearing item to a **durable, committed
repo doc** (e.g. `docs/<feature>-plan.md`) — open todos, current phase, decisions,
what's landed vs. remaining — and reference that doc from the handoff. Name in
the seed prompt any skill the fresh conversation must re-run to rebuild session
state, such as re-arming a schedule. The old session retains its own state, so a
mistimed handoff is recoverable by resuming that session id.

None of that state is actually lost, only unreachable by default. It stays on
disk under your own session folder, whose path is in your session context and
whose final path component is the session id. So rather than trusting the
handoff doc to have captured everything, put that id in the seed prompt and have
the fresh conversation read the state back for itself:

- `<old-session-dir>/plan.md`, the plan as it stood.
- The two newest files in `<old-session-dir>/checkpoints/`, for recent history.
- `<old-session-dir>/files/`, for persisted artifacts.
- Unfinished todos:
  `sqlite3 <old-session-dir>/session.db "SELECT id,title,status FROM todos WHERE status != 'done'"`
- The tail of the conversation, via `session_store_sql` with `source=local`:
  `SELECT turn_index, user_message, assistant_response FROM turns WHERE session_id='<old-id>' ORDER BY turn_index DESC LIMIT 12`

Tell it to skip anything missing without comment, since `plan.md` and `files/`
are often empty, and to summarise where things stand before acting, so you can
correct a bad reconstruction before it builds on top of one. This recovers
recorded state, not live state: armed schedules stay bound to the old session
either way, and only the `todos` table is named, so point the prompt at any
custom tables that matter.

Steps:

1. Write the handoff doc (as above) and persist the durable plan doc.
2. Commit or stash the working tree so the fresh conversation starts from a
   settled state.
3. As the **last action of the turn**, from inside tmux, send `/new` with a seed
   prompt that points the fresh conversation at the handoff doc, then end the
   turn so the queued command runs next:

```sh
cat > /tmp/handoff-seed.txt <<'PROMPT'
Read the handoff at <handoff-path> and the plan at <plan-doc-path>. Then recover the retired session <old-id> from ~/.copilot/session-state/<old-id>: its plan.md, the two newest files in checkpoints/, anything in files/, its unfinished todos from session.db (table todos, status not done), and its last 12 turns via session_store_sql with source=local. Skip whatever is missing. Summarise where things stand, then continue the work. Re-invoke any skills listed under "suggested skills."
PROMPT

~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/rotate-session/scripts/rotate.sh \
  <old-id> /tmp/handoff-seed.txt
```

Send the seed with that script rather than typing `/new` into the pane. A
message that arrives while the CLI is busy is **queued**, and a queued message
only drains at a turn boundary, which a brand-new session never reaches on its
own, so a hand-typed seed can sit undelivered while the session looks empty. The
script waits for the prompt to render before submitting, confirms the fresh
session recorded it, and re-sends if it did not. It writes the outcome to
`/tmp/rotate-session-<old-id>.log`, so report what that log says rather than a
handoff you did not observe.

`/new <prompt>` starts a clean conversation seeded with that prompt in the same
tmux window and Copilot process, with no relaunch and no confirmation dialog.
Outside tmux, report the handoff path and let the user run `/new` themselves.

### Retiring a long-lived session

A session accumulates a full event log on disk that the CLI reloads whenever the
session is resumed, so one resumed daily for weeks grows into the gigabytes and
slows the app. Neither a soft reset nor `/new` reclaims that — both keep writing
to a session-state folder. When a named agent has been resumed for more than a
few days, recommend that the user retire the session and start a genuinely fresh
one rather than resuming.

Retiring loses no recorded state: the old session stays on disk, and the fresh
one can read it back with the same recipe as the `/new` seed prompt above.
Armed schedules do not survive, so re-arm them from the new session.
