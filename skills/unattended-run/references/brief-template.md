# Autopilot brief template

Two artifacts: the **charter** you persist and re-feed on the `/every` reminder
(the load-bearing one you arm yourself), and the **optional objective** you
best-effort send through the session-inbox SDK extension or print as a fallback
for `/autopilot`. Fill every `<SLOT>`; delete any clause that doesn't apply
rather than leaving a placeholder.

## Objective — OPTIONAL, persisted and handed to `/autopilot`

`/autopilot` is not an agent tool. After arming the charter re-brief, enqueue
the objective file into the current session through the SDK handoff as the final
tool action when targeting is safe. The handoff invokes the native autopilot
command and reads its state back to prove the exact objective was established.
Otherwise print its contents and explain that the user must paste it to
establish native autopilot. The charter re-brief continues to restore working
rules, but it does not replace the persistent objective.

Persist a complete work order, not a compressed slogan. Autopilot re-reads it
on every continuation, so include enough context to resume correctly after
compaction. Store only this objective body in a dedicated file such as
`docs/<run>-autopilot-objective.md`; the handoff helper passes it unchanged to
the native command:

> Work from `<PLAN_DOC>`[ for `<SCOPE>`] in `<WORKSPACE>`.
>
> Outcome: `<OUTCOME>`.
>
> Follow the plan in order and keep its current baton accurate. Use the
> charter's required process skills and push policy. Treat `<NON_GOALS>` as
> outside this run.
>
> Finish only when every item in the "`<DOD_REF>`" section is verifiably met.
> Do not substitute partial tests, code inspection, or a plausible
> implementation for the observable completion evidence named there.

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
- **`<OUTCOME>`** — the finished user-visible result.
- **`<NON_GOALS>`** — explicit boundaries that prevent the run from expanding
  into adjacent cleanup or redesign.

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
> `/dfrysinger-skills:development-loop` critical-path audit at run start, every
> phase boundary, and every scheduled re-brief: rebuild ready work and
> dependencies, mark the critical path, assign every substantial independent
> ready scope to an available subagent when delegation is safe, and advance
> another ready item whenever the current one is waiting. If I assigned
> independent agents, treat them as first-class owners: keep their scopes,
> workspaces or branches, owed evidence, blockers, and integration boundaries
> in the baton; unblock them promptly and consume their frozen reviewed commits
> without duplicating their work. Give every file-writing delegate an isolated
> worktree or checkout and never use the coordinator's worktree as a concurrent
> write target. Keep the
> coordinator focused on integration, decisions, unblocking, and unowned
> critical-path work. Batch coherent fixes before expensive builds, verifiers,
> or CI, and use proof impact mapping instead of replaying unaffected claims.
> Preserve actual serial gates, including one proof owner and one running
> candidate during live proof. `<PUSH_POLICY>`.
> Decide every reversible question yourself with rubber-duck rather than asking
> me. For systemic or critical work, preserve the plan's decision hierarchy,
> constraint provenance, revisit conditions, and any active reframe record in
> the current baton; inherited mechanisms do not become requirements merely
> because they survived compaction. `<COORDINATION>`. `<GRANTS>`. Stay on this
> course until the objective's
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
- **`<PUSH_POLICY>`** — derive this from the repository's own instructions.
  When the repository gives agents an owned branch namespace and pull-request
  path, default to `Push reviewed and validated work to your own branch and PR
  whenever you need`. Use `Don't push — keep working locally for this run`
  only when the user explicitly requests local-only work or a repository rule
  forbids remote publication. Keep ordinary branch publication separate from
  approval-gated production actions such as deployment, merge-queue mutation,
  infrastructure changes, or writes to shared resources.
- **`<COORDINATION>`** — when peers share the effort:
  name every user-assigned agent, its owned scope, workspace or branch, expected
  receipt or frozen handoff, and the durable surface used to monitor and
  unblock it. Give every file-writing agent an isolated worktree or checkout.
  Include: `Do not wait for an agent to push to main; consume its reviewed
  frozen commit from its owned branch or worktree as soon as its dependencies
  and integration boundary are ready.` Omit only when no independent agents
  were assigned.
- **`<GRANTS>`** — the standing permissions that keep the run unattended;
  compose only the ones that apply, and keep token authorization here (not in
  the objective):
  - `Freely burn real tokens as much as you need within reason`
  - `I'm not at the computer, so raise your app to the top and test/screenshot freely`
  - `You're authorized to create a testing account and repo on <SERVICE> for me; use <EMAIL_TOOL> to check my email as needed`
  - `Run <CI/workflow systems> as much as you need within reason`

For a systemic or critical run, the filled charter additionally names where
the governing plan records its constraint provenance and reframe gate, and the
current baton states whether any revisit condition is open.

## Worked example

**Objective file**:

> Work from `docs/checkout-refactor-plan.md` in the checkout-refactor worktree.
>
> Outcome: the checkout flow uses the new state model and the supported
> checkout scenarios work end to end.
>
> Follow the plan in order and keep its current baton accurate. Use the
> charter's required process skills and push policy. Do not redesign unrelated
> payment or account flows.
>
> Finish only when every item in the "Definition of Done" section is verifiably
> met. Do not substitute partial tests, code inspection, or a plausible
> implementation for the observable completion evidence named there.

**Charter** (persisted; re-fed on the reminder):

> Keep building against the plan at `docs/checkout-refactor-plan.md` in your
> worktree. Follow the required process skills below. Use rubber-duck to
> brainstorm solutions and align on
> paths forward whenever you get stuck. Keep the plan up to date so future agents
> can pick it up. At run start, every phase boundary, and every hourly
> re-brief, run `/dfrysinger-skills:development-loop`'s critical-path audit:
> rebuild ready work and dependencies, assign every substantial independent
> ready scope to an available subagent when delegation is safe, batch coherent
> fixes before expensive gates, and advance other ready work during waits while
> preserving exclusive live-proof gates.
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
