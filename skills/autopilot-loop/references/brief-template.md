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

> Keep building against the plan at `<PLAN_DOC>`[ through `<SCOPE>`] in your
> `<WORKSPACE>` using `<DEV_SKILLS>` and `<TEST_SKILL>` for end-to-end testing.
> Use rubber-duck to brainstorm solutions and align on paths forward whenever
> you get stuck. Keep the plan up to date so future agents can pick it up. Use
> subagents liberally to parallelize work whenever possible. `<PUSH_POLICY>`.
> Decide every reversible question yourself with rubber-duck rather than asking
> me. `<COORDINATION>`. `<GRANTS>`. Stay on this course until the objective's
> Definition of Done (the "`<DOD_REF>`" section) is met.

Charter slots:

- **`<WORKSPACE>`** — where the work happens (e.g. "your feature worktree"), so
  a reminded agent re-confirms it's in the right tree.
- **`<DEV_SKILLS>`** — the development skill(s) this project uses, always
  including the shipping loop (`/dfrysinger-skills:development-loop`)
  plus any project dev skill (e.g. a language- or framework-specific dev skill).
- **`<TEST_SKILL>`** — the project's end-to-end testing skill (e.g. your
  project's E2E skill), or the loop's own E2E gate when none is separate.
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
> worktree using `/dfrysinger-skills:development-loop` for development
> and end-to-end testing. Use rubber-duck to brainstorm solutions and align on
> paths forward whenever you get stuck. Keep the plan up to date so future agents
> can pick it up. Use subagents liberally to parallelize work whenever possible.
> Push to remote and merge when each phase is done, tested E2E and reviewed
> clean. Decide every reversible question yourself with rubber-duck rather than
> asking me. Stay on this course until the objective's Definition of Done (the
> "Definition of Done" section) is met.
