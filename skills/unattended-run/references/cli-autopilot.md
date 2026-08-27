# How Copilot CLI autopilot works

The native `/autopilot` objective drives what the run must finish. The separate
`/every` re-brief restores the working rules after compaction; it does not
replace the objective's persistent goal and continuation state. Because
`/autopilot` and `/goal` are not agent tools, the skill establishes the
objective through the target session's SDK extension or prints it for the user
to paste when that handoff is unavailable.

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

- The agent may hand off a persisted multi-line objective after the `/every`
  reminder is live. The bundled detached helper calls the session-inbox request
  CLI with the bounded `autopilot` request, the target session ID or tmux
  session name, and `--prompt-file`.
- The extension waits for the target to become idle, persists the native
  objective by enqueuing the native `/autopilot` command through
  `commands.enqueue()`, then reads the resulting state with
  `workspaces.readAutopilotObjective()`. It accepts the handoff only when the
  native state contains the exact objective with an active or completed status
  and the matching native starting message reports idle delivery.
- The request CLI and bundled helper both retain receipts. The helper's receipt
  includes the objective and raw SDK request output; a completed extension
  receipt proves delivery without scraping TUI output.
- The 360-second delivery budget is a stop guard, not a retry trigger. A timeout
  leaves the extension request available for diagnosis; do not create a second
  objective handoff until the first receipt is resolved.
- On first use, the native command may show Copilot's autopilot permission
  dialog. The handoff remains unconfirmed until that dialog is resolved and the
  native starting message actually begins; objective-file creation alone is
  not reported as success.
- `/allow-all` remains user-controlled. Print it when needed; never
  include a permission escalation in the objective handoff.
- Autopilot mode is sticky by default for the next prompt. This is expected and
  requires no cleanup after the current objective finishes.
- The skill must not enqueue `/autopilot off`, change `stayInAutopilot`, or
  otherwise alter the user's selected mode.
- Escape / Ctrl+C cancels and stops autopilot from continuing.

The SDK handoff establishes native objective state and selects autopilot mode
directly; it does not type a slash command. Run it detached as the final action
so the current turn can end and the extension's idle gate can open. If the
handoff is unavailable, print the objective and do not ask the user to restart
the CLI.
