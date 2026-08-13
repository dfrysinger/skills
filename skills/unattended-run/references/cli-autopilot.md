# How Copilot CLI autopilot works (optional reference)

Background on the **optional** `/autopilot` objective. You never need this to
run the skill — `/autopilot`/`/goal` are not agent tools, and the `/every`
re-brief you arm yourself is what keeps a run on course. When running inside
tmux, the skill may best-effort enqueue the objective through the CLI input;
otherwise it prints the objective for the user.

## The objective and the continuation loop

- `/autopilot <objective>` (alias `/goal <objective>`) sets an objective;
  objective-form autopilot is on by default in current builds.
- While an objective is active, autopilot keeps re-continuing the agent toward
  it, re-stating it each turn. A bare `/autopilot` with no objective caps its
  continuations after a few turns, so a plain run stops early.
- The run stops continuing when the CLI determines the task is complete, so the
  objective's done-condition should point at an observable Definition of Done.
  Do not couple skill text to the internal `task_complete` tool.

## Launching the run

- The agent may hand off `/autopilot <objective>` through its current tmux pane
  after the `/every` reminder is live. The bundled detached helper waits for
  the active turn to reach an idle boundary before typing.
- Confirm acceptance from visible TUI output. Current builds print
  `Started autopilot objective #<n>:`; older builds print
  `Autopilot objective:`. Either means injection succeeded.
- Do not report injection failure if either accepted-objective confirmation is
  visible, even when the charter reminder is described separately.
- `/allow-all` remains user-controlled. Print it when needed; never
  self-enqueue a permission escalation.
- Autopilot mode is sticky by default for the next prompt. This is expected and
  requires no cleanup after the current objective finishes.
- The skill must not enqueue `/autopilot off`, change `stayInAutopilot`, or
  otherwise alter the user's selected mode.
- Escape / Ctrl+C cancels and stops autopilot from continuing.

These remain user-interface slash commands, not agent tools. A synchronous
`tmux send-keys` loop launched by the active turn cannot verify its own next
turn and must not be used. The detached helper verifies visible acceptance; if
the handoff is unavailable, print the objective and do not ask the user to
restart the CLI.
