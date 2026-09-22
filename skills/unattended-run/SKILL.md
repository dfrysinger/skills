---
name: unattended-run
description: Keep a long, unattended Copilot CLI run on course with event-driven re-briefs and constraint challenges, one lightweight four-hour liveness backstop, and an optional autopilot objective delivered through the session-control SDK. Use when starting a long autopilot or `/goal` run against a plan doc, sharpening its objective, or preventing drift across context compactions.
---

# unattended-run

For a long, unattended Copilot CLI run, three things keep the agent on
course:

- **Event-driven governance** — the governing workflow re-runs its
  critical-path audit at task start, compaction or resumption, candidate
  movement, phase boundaries, failures, ownership handoffs, and material user
  direction. Systemic and critical work invokes `constraint-challenge` only
  when `development-loop` reports a material scope, architecture, trust,
  authority, policy, or reframe trigger.
- A lightweight **four-hour liveness backstop** — one `/every` reminder checks
  that the durable baton, owner, candidate or proof state, and schedule
  registry remain coherent. It performs the full re-brief only when that check
  finds stale or inconsistent state. **Arm it yourself with `manage_schedule`
  before any same-session compact. It is the load-bearing scheduled deliverable
  of this skill.**
- An **optional `/autopilot` objective** that drives the *what* until the agent
  determines the task is complete. A detached request asks the session-control
  extension to invoke the native `/autopilot` command directly, then reads the
  native objective state back to prove the exact objective was established.
  Fall back to printing it when that handoff is unavailable.

## Critical: use the session SDK, not terminal input

The objective handoff is not a terminal slash-command injection. The bundled
helper calls `extensions/session-control/request.mjs autopilot`. The target
extension invokes the bounded native `/autopilot` command through the SDK
without waiting for idle. An idle session starts the returned native prompt
through immediate SDK delivery; an active autopilot session updates its
objective in place. The extension then reads the resulting native objective
state back, confirms its canonical text exactly, confirms idle or steering
activation, and writes a durable completed or failed receipt.
The request removes only trailing line-ending bytes because the native command
parser removes them before storing objective state; interior line structure is
preserved. The request CLI derives deduplication from that canonical text and
the resolved session ID. This is expected and is **NOT a blocker**:

- Do **not** stop, and do **not** ask the user to restart or relaunch the CLI.
- Never put `/allow-all` in the objective or otherwise change permissions;
  permission escalation remains an explicit user choice.
- Do not tell the agent to call `task_complete`. Current CLI releases expose
  completion internally only while autopilot is active; the objective should
  define observable completion and let the CLI handle the transition.
- Autopilot remaining selected after completion is expected and harmless. It
  affects only how the next prompt is handled; do not turn it off as cleanup.
- The SDK request bypasses the native message FIFO. Run the helper detached and
  end the current turn; its 360-second maximum confirmation wait preserves the
  handoff budget and prevents an unbounded watcher. To self-compact during a run,
  use `self-compact`, which queues the compact and arms a watcher that submits
  continuation only after the session's `summary_count` proves compaction
  landed. Then end your turn. Selected autopilot mode alone does not reliably
  create the post-compact turn.
- The run does **not** need `/autopilot` to proceed — event-driven re-briefs
  and the liveness backstop keep it on course.

Arm the liveness backstop, send the objective through the target session's extension
when safe, and continue the actual work autonomously. If the extension is
unavailable, print the objective instead.

## When to use

- A run long enough that context compaction will happen before the plan is done,
  run unattended.
- For a short, attended task that fits in one context window, skip this and just
  do the work.

## Steps

### 1. Draft the charter and the objective
Fill both artifacts in [`references/brief-template.md`](references/brief-template.md):
the **charter** (the standing *how* — required process skills, push policy,
autonomy mandate, plan hygiene, critical-path audit, delegated ownership,
coordination, standing grants) and
the **objective** (plan doc, scope, outcome, boundaries, and observable
done-condition).

Derive the push policy from the repository's instructions. If agents have
owned branch namespaces and a pull-request workflow, publishing reviewed work
to that owned branch is the default. A local-only charter requires an explicit
user request or repository prohibition; do not infer it from separate approval
gates for deployment, merge queues, infrastructure, or shared resources.

The charter's skill manifest records:

- one **governing skill** that owns the run's process and completion gates;
- **execution skills** needed only in the phases they own;
- `self-compact` as the **context skill** that owns compaction.

When another skill hands work to `unattended-run`, make that caller the
governing skill. Otherwise choose the skill whose process owns the Definition
of Done. Do not preserve every currently loaded skill: planning, explanation,
and one-time investigation skills are not standing process dependencies.
`unattended-run` itself never belongs in the execution-skill manifest. It
remains the named owner to invoke when the liveness schedule must be armed,
migrated, repaired, or stopped.

Every charter includes the `/dfrysinger-skills:development-loop` critical-path
audit, even when another skill governs the run. Run it at task start,
compaction or resumption, candidate movement, every phase boundary, failure,
ownership handoff, and material user direction. When the liveness backstop
finds stale or inconsistent state, it runs the same audit before continuing:

- rebuild the remaining dependency graph and mark the critical path;
- assign every substantial independent ready scope to an available subagent;
- for every delegated agent, reconcile its explicit scope, owned path boundary,
  workspace or branch, session or coordination channel, evidence owed,
  blockers, and integration boundary; preserve a stable assignment ID and
  routable owner address in the durable baton. Mailbox agents use fully
  qualified `name@machine`; native subagents use their exact agent ID. A bare
  display name does not establish ownership or a status route. Preserve
  user-assigned agents as first-class external owners;
- read each delegated agent's explicit session result, task result, mailbox
  response, or handoff before reporting its status, waiting on it, or assigning
  successor work; never infer worker state from whether its worktree is dirty,
  clean, changing, or unchanged;
- when no explicit result from the current assignment exists, record the worker
  state as `unknown`, request status once through its recorded routable address,
  and advance other ready work. If the address is absent or ambiguous, record
  the ownership route as unresolved rather than guessing a machine or
  same-named agent;
- consume a completed handoff before inspecting its worktree, close the prior
  assignment, and treat any successor request as a new assignment;
- give every file-writing delegate an isolated worktree or checkout and keep
  the coordinator's worktree free of concurrent writers;
- freeze the completed commit or receipt and explicitly transfer worktree
  ownership before any other writer enters it; overlapping writers stop the
  lane until one routable owner is restored;
- keep the coordinator on integration, decisions, unblocking, and unowned
  critical-path work;
- batch coherent fixes before expensive gates and avoid replaying unaffected
  proof; and
- advance other ready work during waits without violating one-owner live-proof
  or other exclusive gates.
- for systemic or critical work, check the durable independent
  constraint-challenge record; require its `CLEAR` gate, or a `PARTIAL` gate
  whose `permitted_scope` contains the exact next action and whose
  `blocked_scope` does not, before advancing that action; execute any
  event-triggered challenge that `development-loop` reports due. Time passing
  alone never makes a challenge due. Supply relevant user statements as exact
  quotes with their available context. After a due challenge returns, compare
  its new gate with the exact next action again before continuing.

The charter names any user-assigned agent roster and its durable coordination
surface. "Use subagents liberally" alone is not a sufficient delegation
contract.

The plan must carry a plain **Definition of Done** covering exactly this run's
scope, under a unique heading both artifacts point at; if it's missing, write it
first — with `design-doc` for systemic or critical work, or at
`development-loop`'s handoff point for bounded work.

For systemic or critical work, the charter also points to the plan's decision
hierarchy, constraint-provenance record, and reframe gate. Its current baton
names any open revisit condition or active reframe record. It also records the
last completed independent constraint challenge, any unserviced event trigger,
and all relevant user statements received since that challenge as exact quotes
with enough context to classify them. The schedule registry records only the
four-hour liveness backstop. A mechanism inherited through compaction remains
a mechanism, not a binding requirement.

Existing charters may still name a two-hour charter reminder or an eight-hour
challenge schedule. Migrate them at the next safe phase boundary: finish any
in-flight live proof and list schedules. Preserve every legacy registry entry,
add the pending `liveness` entry alongside them, create and confirm one
four-hour liveness backstop, then persist its returned identifier and `live`
status. Only after that replacement is live, stop every old charter or
challenge schedule pointed at the charter and remove its legacy registry entry.
Re-list and require exactly one matching liveness schedule before compacting.
The migration itself never makes a constraint challenge due. If the new
liveness schedule cannot be created or confirmed, remove only its pending
entry and leave the prior schedules and registry unchanged. Do not remove the
run's recovery path. To roll back a completed migration, use
[`references/legacy-schedule-rollback.md`](references/legacy-schedule-rollback.md)
to recreate and confirm the prior schedules before stopping the liveness
schedule, then restore their registry entries. Existing event triggers remain
valid throughout rollback.

Persist the objective body in its own file, without the `/autopilot` prefix,
because the detached helper sends the whole file. Persist the charter
separately so the liveness schedule can re-read only the standing operating
rules.

**Complete when** both files exist, no `<SLOT>` remains, both point at the same
Definition-of-Done heading, every skill in the manifest owns work or a gate
that remains in this run, the charter contains the complete critical-path
audit and any assigned-agent roster, and every systemic or critical charter
preserves the constraint and reframe pointers plus their current status.

**Handoff gate.** The finished brief is a complete work order, but do not
compact yet. A bare compact returns to an idle prompt; before step 2 there is no
liveness schedule or objective to create the next turn.

For a same-session handoff, complete step 2 first. Once the liveness backstop is
confirmed live, self-hand-off with a **soft reset**. Build this private
`self_compact` tool argument using `self-compact`'s brief protocol:

```text
Keep: Replace the conversation with a standing brief pointing at <charter-path>,
<objective-file>, and their shared Definition of Done.

Drop: Planning history and tool output already captured by the charter.

After compaction: Continue this charter at step 3, invoke the objective as the last action of that turn, then end the turn so it fires; do not compact again.
```

Call `self_compact` with that one `brief` argument as the final action. The
extension arms and hands off to its detached verifier, which authorizes after
tool completion, submits the compact, and resumes only after the matching
compaction event and checkpoint land. The live liveness schedule remains the
durable recovery path. Missing either the required schedule or the verifier
makes the handoff incomplete.

Use `/new` instead only if the planning conversation must remain separately
resumable. It starts a fresh session, so the new-session prompt itself must
invoke `unattended-run` and arm the liveness backstop before doing any work:

```
/new Use /dfrysinger-skills:unattended-run against <brief-path>, arm the
four-hour liveness backstop, and start work.
```

See the `handoff` skill for both recipes.

### 2. Arm the four-hour liveness backstop — do this yourself
This schedule keeps the run recoverable, and you can create it without the
user. Persist the charter to a durable file the run and reminder both read —
alongside the plan (e.g. `docs/<feature>-autopilot.md`) so a future agent
inherits it, or a session file for a throwaway run. The persisted file includes
the charter prose and its complete **Required process skills** manifest.

For a new charter, add a schedule registry to the persisted charter with one
`liveness` entry containing `kind`, `id`, `interval`, and `status`. For a
legacy charter, follow the migration transaction above and do not replace its
registry before the new schedule is confirmed. Run `manage_schedule
action=list`. Reuse one live liveness schedule already pointed at this file
only when its prompt matches the contract below, and persist its identifier.
Treat every other charter or challenge reminder pointed at this file as stale.
If no matching liveness schedule exists, create and confirm one replacement,
capture its returned identifier, and immediately change its registry status
from `pending` to `live`. Only then stop stale or duplicate reminders for this
objective; leave unrelated schedules untouched.

Arm the four-hour liveness schedule with `manage_schedule` (the tool `/every`
runs), pointed at the file so each tick re-reads the authoritative copy:

```
manage_schedule action=create interval=4h \
  prompt="If you are currently making a user-directed edit to the plan, design
  doc, brief, or charter, finish the current coherent edit and persist it first.
  Then re-read your autopilot charter at <charter-path> and its current plan
  baton. Never replace an in-flight revision with the older persisted version.
  List active schedules and reconcile them against the charter registry. Stop
  duplicate liveness reminders and every legacy charter re-brief or challenge
  schedule pointed at this charter. Re-list and require exactly one matching
  four-hour liveness schedule. Check only whether the workspace, objective, current phase,
  candidate or proof identity, active owner routes, and registry are present
  and mutually consistent. If they are current, do not run a full re-brief or
  constraint challenge merely because this tick fired; continue the current
  plan. If any state is stale, missing, duplicated, or inconsistent, follow the
  charter's Required process skills protocol and run
  /dfrysinger-skills:development-loop's critical-path audit before continuing.
  For systemic or critical work, invoke constraint-challenge only when
  development-loop reports a material scope, architecture, trust, authority,
  policy, or reframe trigger. Time passing alone is not a trigger. During active live proof,
  remain read-only and advance only work that cannot mutate its candidate,
  worktree, fixture, or process. Stop this schedule once the charter's
  referenced Definition of Done is verifiably met by stopping every schedule
  identifier in the charter registry plus any live schedule pointed at this
  charter, then verifying their absence."
```

The charter remains authoritative for skill and compaction policy. The
liveness tick carries its own off-switch, so it disengages on arrival rather
than nagging forever.

**Complete when** the charter file names its governing, execution, and context
skills; the registry contains the identifier returned at creation; and
`manage_schedule action=list` shows exactly one four-hour liveness reminder for
this objective and no challenge schedule pointed at the charter. The reminder
checks coherent state cheaply and invokes the **Required process skills**
protocol only when it finds stale or inconsistent state. A same-session
compact is forbidden until this criterion passes.

### 3. Hand off `/autopilot` through native command invocation
After the charter exists and the liveness reminder is live, invoke
the persisted objective in your own Copilot CLI session when all of these hold:

- The user has not asked you to leave autopilot disabled.
- The objective file is readable, self-contained, and fully resolved, with no
  `<SLOT>`.
- You know either the current Copilot session ID or the exact tmux session name
  whose session-control extension should receive the request. Prefer the session
  ID from the current session context; use the tmux name only as a targeting
  fallback.

Launch the bundled handoff as a **detached** Bash process, then end the current
turn immediately:

```bash
"<skill-dir>/scripts/enqueue-autopilot.sh" \
  --target-session '<current-session-id>' \
  '<objective-file>'
```

When only the tmux session name is available, replace the target arguments with
`--target-tmux '<exact-tmux-session-name>'`.

Invoke Bash with `mode:"async"`, `detach:true`, and a short `initial_wait`.
This must be the final tool action: emit no prose and call no more tools after
launching it. The helper executes:

```text
autopilot --target-session ID or --target-tmux NAME --prompt-file FILE
```

It rejects empty, slash-prefixed, permission-changing, or unresolved objectives;
caps the receipt wait at 360 seconds; requires the SDK receipt to prove both
`objectiveSet: true` and `delivery: "idle"` or `"steering"`; preserves the request output and objective under
`~/.copilot/autopilot-enqueue/`; and notifies the user if delivery cannot be
confirmed. The session-control extension also retains its JSON request receipt.

If neither target can be identified or the request helper is unavailable,
print this fallback and
continue without blocking:

```
The native autopilot objective could not be established automatically.
Without it, the /every liveness backstop repairs stale working state but does
not provide the same persistent goal-driven continuation:

Paste `/autopilot ` followed by the complete contents of <objective-file>.
```

If `/allow-all` is needed, print it for the user; never include it in the SDK
handoff. The detached helper reports post-launch failure through its receipt and
macOS notification. The native objective drives what to finish; the `/every`
liveness backstop repairs stale state after compaction while event triggers
drive normal re-briefs.

**Complete when** the detached handoff was launched as the last action, or the
fallback was printed because SDK targeting was unavailable.

### 4. Stop cleanly when the Definition of Done is met
When every Definition-of-Done item is verifiably met:

1. Stop every schedule identifier in the charter registry and every live
   schedule pointed at this charter with `manage_schedule action=stop`, verify
   their absence with `manage_schedule action=list`, and persist their stopped
   state.
2. Finish normally using the completion mechanism exposed by autopilot.

Autopilot remaining selected afterward is the current CLI default and requires
no cleanup. Do not enqueue `/autopilot off`, change `stayInAutopilot`, or
otherwise alter the user's selected mode.

**Complete when** the liveness schedule is stopped and the verified task
has finished normally.
