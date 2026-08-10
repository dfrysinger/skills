# Autopilot brief template

Two artifacts: the **charter** you persist and re-feed on the `/every` reminder
(the load-bearing one you arm yourself), and the **optional objective** you
best-effort self-enqueue through tmux or print as a fallback for `/autopilot`.
Fill every `<SLOT>`; delete any clause that doesn't apply rather than leaving a
placeholder.

## Objective — OPTIONAL, self-enqueued or printed for `/autopilot <objective>`

`/autopilot` is not an agent tool. After arming the charter re-brief, enqueue
this line into the current tmux pane as the final tool action when targeting is
safe; otherwise print it as an optional convenience and proceed. The run stays
on course through the charter re-brief without it.

One self-contained, completion-detectable line. Autopilot re-reads it on every
continuation and determines completion from it, so keep it short and make the
done-condition observable:

> Achieve the Definition of Done in `<PLAN_DOC>`[ for `<SCOPE>`], the
> "`<DOD_REF>`" section: `<ONE_LINE_OUTCOME>`. Keep working through the plan;
> finish only once every item in the "`<DOD_REF>`" section is verifiably met.

Objective slots:

- **`<PLAN_DOC>`** — the durable, committed plan the run executes and updates.
- **`<SCOPE>`** — the whole plan, or a bound like "phase E"; omit the clause for
  the whole plan.
- **`<DOD_REF>`** — the exact, unique heading of the Definition of Done that
  covers this run's scope. It is the objective's sole completion authority, and
  the charter and the reminder point at the same heading, so all three stop on
  one condition that can't drift apart. Its items must be observable (tests
  green, the E2E scenario passes, the feature works end to end) so
  autopilot stops only when they genuinely hold.
- **`<ONE_LINE_OUTCOME>`** — the finished result in one plain phrase.

## Charter — persisted to a file, re-fed on the `/every` reminder

The standing operating rules. This is the *how*; the objective owns the *what*
and the stop condition, so the charter closes by pointing back at `<DOD_REF>`.
Keep the skill manifest structured so the hourly reminder can restore the
process after compaction without copying each skill's rules.

> Keep building against the plan at `<PLAN_DOC>`[ through `<SCOPE>`] in your
> `<WORKSPACE>`. Follow the required process skills below.
> If a reminder arrives while you are making a user-directed edit to the plan,
> design doc, brief, or charter, finish the current coherent edit and persist it
> to the authoritative file before reconciling against that file. Never replace
> an in-flight revision with the older persisted version.
> Use rubber-duck to brainstorm solutions and align on paths forward whenever
> you get stuck. Keep the plan up to date so future agents can pick it up. Use
> subagents liberally to parallelize work whenever possible. `<PUSH_POLICY>`.
> Decide every reversible question yourself with rubber-duck rather than asking
> me. `<COORDINATION>`. `<GRANTS>`. Stay on this course until the objective's
> Definition of Done (the "`<DOD_REF>`" section) is met.
>
> ### Required process skills
>
> - **Governing:** `<GOVERNING_SKILL>` — owns the run's phase order, gates, and
>   completion process. Invoke it at run start and after compaction when it is no
>   longer active.
> - **Execution:** `<EXECUTION_SKILLS>` — invoke each only when the current
>   phase reaches the work it owns. Use `None` when the governing skill needs no
>   project-specific companion.
> - **Context:** `/dfrysinger-skills:self-compact` — at the governing workflow's
>   compaction points, or when context becomes noisy or repetitive, persist the
>   complete baton and invoke and follow this skill as the final action. Do not
>   compact merely because the hourly reminder fired or while active live proof
>   is in progress.

Charter slots:

- **`<WORKSPACE>`** — where the work happens (e.g. "your feature worktree"), so
  a reminded agent re-confirms it's in the right tree.
- **`<GOVERNING_SKILL>`** — the skill that handed work to `unattended-run`, or
  otherwise the one process that owns the Definition of Done. For product work
  this is normally `/dfrysinger-skills:development-loop`.
- **`<EXECUTION_SKILLS>`** — only project or domain skills that own a remaining
  implementation, testing, deployment, or review phase. Do not include every
  skill currently loaded, and never include `unattended-run` itself.
- **`<PUSH_POLICY>`** — the one policy most worth pinning, pick one:
  - `Don't push — keep working locally for this run`
  - `Push to remote and merge when each phase is done, tested E2E and reviewed clean`
  - `Push reviewed and validated work whenever you need`
- **`<COORDINATION>`** — when peers share the effort:
  `If coordinating with other agents, don't wait for them to push to main —
  cherry-pick what you need from their worktree/branch`. Omit when solo.
- **`<GRANTS>`** — the standing permissions that keep the run unattended;
  compose only the ones that apply, and keep token authorization here (not in
  the objective):
  - `Freely burn real tokens as much as you need within reason`
  - `I'm not at the computer, so raise your app to the top and test/screenshot freely`
  - `You're authorized to create a testing account and repo on <SERVICE> for me; use <EMAIL_TOOL> to check my email as needed`
  - `Run <CI/workflow systems> as much as you need within reason`

## Worked example

**Objective** (`/autopilot`):

> Achieve the Definition of Done in `docs/checkout-refactor-plan.md`, the
> "Definition of Done" section: the checkout flow is refactored and its full
> test suite passes. Keep working through the plan; finish only once every item
> in the "Definition of Done" section is verifiably met.

**Charter** (persisted; re-fed on the reminder):

> Keep building against the plan at `docs/checkout-refactor-plan.md` in your
> worktree. Follow the required process skills below. Use rubber-duck to
> brainstorm solutions and align on
> paths forward whenever you get stuck. Keep the plan up to date so future agents
> can pick it up. Use subagents liberally to parallelize work whenever possible.
> Push to remote and merge when each phase is done, tested E2E and reviewed
> clean. Decide every reversible question yourself with rubber-duck rather than
> asking me. Stay on this course until the objective's Definition of Done (the
> "Definition of Done" section) is met.
>
> **Required process skills**
>
> - **Governing:** `/dfrysinger-skills:development-loop`
> - **Execution:** `None`
> - **Context:** `/dfrysinger-skills:self-compact`
