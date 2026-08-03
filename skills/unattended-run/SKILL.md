---
name: unattended-run
description: Keep a long, unattended Copilot CLI run on course. Autonomously arm an `/every` charter re-brief (via manage_schedule) that restores the run's operating rules on each tick so a compacted context doesn't drift, then best-effort self-enqueue the `/autopilot` objective through the current tmux pane. Use when starting a long autopilot or `/goal` run against a plan doc, when writing or sharpening an autopilot objective, or when keeping an unattended run from drifting over many context compactions.
---

# unattended-run

For a long, unattended Copilot CLI run, two things keep the agent on course:

- A recurring **charter re-brief** — an `/every` reminder that re-anchors the
  *how* (governing skills, worktree, push policy, autonomy mandate, plan
  hygiene, compaction discipline) on each tick, so a compacted context doesn't
  drift. **You arm this yourself with
  `manage_schedule`. It is the load-bearing deliverable of this skill.**
- An **optional `/autopilot` objective** that drives the *what* until the agent
  determines the task is complete. `/autopilot` is not an agent tool, but when
  the CLI is running inside tmux you can best-effort enqueue it into your own
  input field with `tmux send-keys`. Fall back to printing it when self-enqueue
  is unsafe or unavailable.

## Critical: `/autopilot` is UI injection, not an agent tool

`/autopilot` and `/goal` are user-only slash commands. They will **not** appear
in your tool list. Self-enqueue works by typing into the current tmux pane, just
like a mailbox wakeup; it does not make the slash command directly callable or
verifiable as a tool. This is expected and is **NOT a blocker**:

- Do **not** stop, and do **not** ask the user to restart or relaunch the CLI.
- Do **not** report the run as blocked because you can't see `/goal`.
- Never self-enqueue `/allow-all`; permission escalation remains an explicit
  user choice.
- Do not tell the agent to call `task_complete`. Current CLI releases expose
  completion internally only while autopilot is active; the objective should
  define observable completion and let the CLI handle the transition.
- Autopilot remaining selected after completion is expected and harmless. It
  affects only how the next prompt is handled; do not turn it off as cleanup.
- A slash command you inject lands at the **next turn boundary**, like any user
  message — including mid-run under autopilot. To self-compact during a run,
  send it and then end your turn; it runs immediately after. Autopilot supplies
  its own continuation afterward, so a standing-brief compact resumes the
  objective with no trigger word needed.
- The run does **not** need `/autopilot` to proceed — the `/every` re-brief you
  arm yourself is what keeps it on course.

Arm the re-brief, self-enqueue the objective when safe, and continue the actual
work autonomously. If self-enqueue is unavailable, print the objective instead.

## When to use

- A run long enough that context compaction will happen before the plan is done,
  run unattended.
- For a short, attended task that fits in one context window, skip this and just
  do the work.

## Steps

### 1. Draft the charter and the objective
Fill both artifacts in [`references/brief-template.md`](references/brief-template.md):
the **charter** (the standing *how* — required process skills, push policy,
autonomy mandate, plan hygiene, subagents, coordination, standing grants) and
the **objective** (plan doc, scope, one-line outcome, observable done-condition).
The charter's skill manifest records:

- one **governing skill** that owns the run's process and completion gates;
- **execution skills** needed only in the phases they own;
- `self-compact` as the **context skill** that owns compaction.

When another skill hands work to `unattended-run`, make that caller the
governing skill. Otherwise choose the skill whose process owns the Definition
of Done. Do not preserve every currently loaded skill: planning, explanation,
and one-time investigation skills are not standing process dependencies.
`unattended-run` itself never belongs in the manifest, because re-invoking it
could create another schedule.

The plan must carry a plain **Definition of Done** covering exactly this run's
scope, under a unique heading both artifacts point at; if it's missing, write it
first — with `design-doc` for systemic or critical work, or at
`development-loop`'s handoff point for bounded work.

**Complete when** no `<SLOT>` remains in either artifact, both point at the same
Definition-of-Done heading, and every skill in the manifest owns work or a gate
that remains in this run.

**Handoff point.** The finished brief is a complete work order — it says what to
do without the conversation that produced it. If a long planning run produced
it, self-hand-off here with a **soft reset**: a null-steered `/compact` whose
entire summary is a standing brief pointing at the brief path, followed by a
queued trigger word. That empties the conversation while keeping the session, so
a re-brief armed either before or after it stays live. Use `/new` instead only
if the planning conversation must remain separately resumable — it starts a
fresh session, so arm the `/every` re-brief *after* the handoff:

```
/new Use /dfrysinger-skills:unattended-run against <brief-path>, arm the /every
charter re-brief, and start work.
```

See the `handoff` skill for both recipes.

### 2. Arm the `/every` charter re-brief — do this yourself
This is the deliverable that keeps the run on course, and you can do it without
the user. Persist the charter to a durable file the run and its reminder both
read — alongside the plan (e.g. `docs/<feature>-autopilot.md`) so a future agent
inherits it, or a session file for a throwaway run. The persisted file includes
the charter prose and its complete **Required process skills** manifest.

Before creating a reminder, run `manage_schedule action=list`. Reuse the one
live charter re-brief already pointed at this file only when its prompt also
tells the agent to follow the charter's **Required process skills** protocol.
Treat a matching reminder with any other prompt as stale. Stop stale or
duplicate reminders for this objective and create one replacement; leave
unrelated schedules untouched. When no current matching reminder exists, arm
one with `manage_schedule` (the tool `/every` runs), pointed at the file so each
tick re-reads the authoritative copy:

```
manage_schedule action=create interval=1h \
  prompt="Re-read your autopilot charter at <charter-path> and its current plan
  baton. Follow the charter's Required process skills protocol exactly and
  reconcile the current work against it; execute any skill invocation or
  compaction action the charter says is due now rather than merely acknowledging
  it. Confirm the workspace, push policy, objective, and current phase, and
  correct any drift before continuing. Stop this schedule once the charter's
  referenced Definition of Done is verifiably met."
```

The charter remains authoritative for skill and compaction policy; the schedule
only points to it and requires due actions to happen. The tick also carries its
own off-switch, so it disengages on arrival rather than nagging forever.

**Complete when** the charter file names its governing, execution, and context
skills, and `manage_schedule action=list` shows exactly one reminder for this
objective live, pointed at that file, with a prompt that follows the charter's
**Required process skills** protocol.

### 3. Best-effort self-enqueue `/autopilot`, then proceed autonomously
After the charter exists and the `/every` reminder is live, enqueue the
single-line objective into your own Copilot CLI input when all of these hold:

- `TMUX_PANE` is set and `tmux display-message -p -t "$TMUX_PANE"
  '#{pane_id}'` succeeds.
- The user has not asked you to leave autopilot disabled.
- The objective contains no newline and is fully resolved, with no `<SLOT>`.

Type the text literally, then press Enter **and confirm it fired**. A single
Enter is unreliable: it often fails to submit, leaving the command sitting
unsent in the input box while you move on believing you triggered it. Retry
Enter until the pane proves the command took effect:

```bash
tmux send-keys -t "$TMUX_PANE" -l -- '/autopilot <objective>'
sleep 0.5
for i in 1 2 3 4 5; do
  tmux send-keys -t "$TMUX_PANE" Enter
  sleep 2
  tmux capture-pane -p -t "$TMUX_PANE" | grep -q 'Autopilot objective:' && break
done
```

`Autopilot objective:` is how the CLI renders an accepted objective, so seeing it
proves the command was interpreted rather than left in the box. If it never
appears, say so plainly and fall back below — do not claim autopilot is active.

Make this the **last tool action of the turn** so the submitted command becomes
the next queued user turn instead of racing later tool work.

If tmux targeting is unavailable or injection fails, print this fallback and
continue without blocking:

```
Optional — run this whenever you like for a tighter goal-driven loop
(the run already continues without it via the /every re-brief):

/autopilot <objective>
```

If `/allow-all` is needed, print it for the user; never self-enqueue it. The
`/every` re-brief remains the load-bearing mechanism either way.

**Complete when** the pane showed `Autopilot objective:`, or the fallback was
printed, and you have moved on with the actual work.

### 4. Stop cleanly when the Definition of Done is met
When every Definition-of-Done item is verifiably met:

1. Stop the charter schedule with `manage_schedule action=stop`.
2. Finish normally using the completion mechanism exposed by autopilot.

Autopilot remaining selected afterward is the current CLI default and requires
no cleanup. Do not enqueue `/autopilot off`, change `stayInAutopilot`, or
otherwise alter the user's selected mode.

**Complete when** the schedule is stopped and the verified task has finished
normally.
