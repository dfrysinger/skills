---
name: unattended-run
description: Keep a long, unattended Copilot CLI run on course with an hourly progress nudge, a four-hour charter check, event-driven governance, and an optional autopilot objective. Use when starting a long autopilot or `/goal` run against a plan doc, sharpening its objective, or preventing drift or idle stalls across context compactions.
---

# unattended-run

For a long, unattended Copilot CLI run, four things keep the agent on
course:

- **Event-driven governance** — the governing workflow re-runs its
  critical-path audit at task start, compaction or resumption, candidate
  movement, phase boundaries, failures, ownership handoffs, and material user
  direction. Systemic and critical work invokes `constraint-challenge` only
  when `development-loop` reports a material scope, architecture, trust,
  authority, policy, or reframe trigger.
- An **hourly progress nudge** — a separate `/every` reminder checks the active
  owner's explicit handoff, advances independent ready work, and runs the
  critical-path audit while the Definition of Done is open. It assigns all
  independent ready scopes, not just the first useful action, and records
  the actual gate for each scope left unowned. When genuinely stuck, use
  one rubber-duck pass on one concrete blocker; do not brainstorm the same
  unchanged evidence every hour.
- A lightweight **four-hour charter check** — another `/every` reminder
  checks that the durable baton, owner or explicit blocker, candidate or proof
  state, and both schedule entries remain coherent. It performs a full
  re-brief only when state is stale or inconsistent. **Arm both reminders
  yourself with `manage_schedule` before any same-session compact.**
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
  and the two reminders keep it on course.

Arm both reminders, send the objective through the target session's extension
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
remains the named owner to invoke when either schedule must be armed,
migrated, repaired, or stopped.

Every charter includes the `/dfrysinger-skills:development-loop` critical-path
audit, even when another skill governs the run. Run it at task start,
compaction or resumption, candidate movement, every phase boundary, failure,
ownership handoff, and material user direction. The four-hour charter check
runs the same audit if it finds stale or inconsistent state. The hourly
progress nudge runs it whenever the Definition of Done is open, even when
one owner is already working:

- rebuild the remaining dependency graph and mark the critical path;
- assign every substantial independent ready scope to an available subagent
  with a separate ownership boundary, or execute cheap direct work; for
  every scope left unowned, name its actual dependency or exclusive gate.
  Complete the ready-lane audit before ending the hourly turn, rather than
  stopping after the first assignment;
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
  or other exclusive gates;
- preserve each launched model attempt's first outcome without treating it as
  a veto on new experiments. Separately identified, pre-registered repetitions
  on identical inputs can resolve variance; changed model, treatment, qualified
  case, limit, and transfer comparisons can answer distinct questions. Preserve
  old denominators, fixed controls, qualification, and stop rules. When stuck,
  give one rubber-duck pass a concrete blocker and ask for a distinguishing
  check or alternative; do not repeat the same brainstorm on unchanged evidence.
  Record each real stall in the plan or a linked evidence log: objective,
  expected next action, observed non-progress, first divergence, source
  receipt, and recovery or exact missing predicate. Label second-hand
  reports unverified until the agent's own handoff or transcript supports them.
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
with enough context to classify them. The schedule registry records both the
four-hour charter check and hourly progress nudge. A mechanism inherited
through compaction remains a mechanism, not a binding requirement.

Existing charters may still name a two-hour charter reminder, an eight-hour
challenge schedule, or a four-hour liveness check without an hourly nudge.
Migrate at the next safe phase boundary: finish in-flight live proof, list
schedules, and preserve legacy registry entries until replacements are live.
Reuse a matching four-hour charter check or create and confirm one; create
and confirm the hourly progress nudge separately. Persist both returned IDs
and `live` statuses, then stop superseded charter/challenge reminders and
remove their legacy entries. Re-list and require exactly one matching schedule
at each cadence before compacting. A missing hourly schedule does not make a
four-hour check a progress nudge. If the hourly creation fails, keep the
confirmed four-hour check live as the recovery path, mark progress pending,
and retry; do not compact yet. If the four-hour check cannot be confirmed,
keep prior schedules and do not replace their registry entries. The
migration itself never makes a constraint challenge due. To roll back a
completed migration, use
[`references/legacy-schedule-rollback.md`](references/legacy-schedule-rollback.md)
to recreate and confirm the prior schedules before stopping both replacements,
then restore their registry entries. Existing event triggers remain valid
throughout rollback.

Persist the objective body in its own file, without the `/autopilot` prefix,
because the detached helper sends the whole file. Persist the charter
separately so either reminder can re-read the standing operating
rules.

**Complete when** both files exist, no `<SLOT>` remains, both point at the same
Definition-of-Done heading, every skill in the manifest owns work or a gate
that remains in this run, the charter contains the complete critical-path
audit and any assigned-agent roster, and every systemic or critical charter
preserves the constraint and reframe pointers plus their current status.

**Handoff gate.** The finished brief is a complete work order, but do not
compact yet. A bare compact returns to an idle prompt; before step 2 there are
no reminders or objective to create the next turn.

For a same-session handoff, complete step 2 first. Once both reminders are
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
compaction event and checkpoint land. The charter check remains the durable
recovery path and the hourly nudge drives progress. Missing either reminder
or the verifier makes the handoff incomplete.

Use `/new` instead only if the planning conversation must remain separately
resumable. It starts a fresh session, so the new-session prompt itself must
invoke `unattended-run` and arm both reminders before doing any work:

```
/new Use /dfrysinger-skills:unattended-run against <brief-path>, arm the
four-hour charter check and hourly progress nudge, and start work.
```

See the `handoff` skill for both recipes.

### 2. Arm the four-hour charter check and hourly progress nudge
These schedules keep the run recoverable and moving, and you can create them
without the user. Persist the charter to a durable file both reminders read —
alongside the plan (e.g. `docs/<feature>-autopilot.md`) so a future agent
inherits it, or a session file for a throwaway run. The persisted file includes
the charter prose and its complete **Required process skills** manifest.

For a new charter, register `charter_check` (4h) and `progress` (1h), each
with `kind`, `id`, `interval`, and `status`. Run `manage_schedule action=list`.
Reuse an existing reminder only when its prompt matches the corresponding
contract below. Otherwise create and confirm each missing reminder, and
persist its returned ID and `live` status before stopping superseded
reminders. Follow the migration transaction above for legacy charters;
leave unrelated schedules alone.

Arm the four-hour check with `manage_schedule`, pointed at the charter:

```
manage_schedule action=create interval=4h \
  prompt="Finish any in-flight user-directed charter or plan edit before
  reading <charter-path> and its current plan baton; never overwrite newer
  state. List active schedules, reconcile BOTH charter registry entries,
  stop duplicate or legacy charter re-brief/challenge reminders, and re-list
  to require exactly one four-hour charter check and one hourly progress
  nudge. Check workspace, objective, phase, candidate/proof identity, owner
  route or explicit blocker, constraint gate, and registry. If any state is
  stale, missing, duplicated, or inconsistent, follow the charter's Required
  process skills and run development-loop's critical-path audit to repair it.
  Otherwise leave progress to the hourly reminder. Time alone never triggers
  a full re-brief or constraint challenge. During live proof remain read-only.
  When the shared Definition of Done is verified, stop BOTH registered
  schedules and every duplicate pointed at this charter; verify absence."
```

Arm the separate hourly progress nudge with `manage_schedule`:

```
manage_schedule action=create interval=1h \
  prompt="Finish any coherent in-flight charter or plan edit before reading
  <charter-path> and its current plan baton; never overwrite newer work.
  Reconcile each active owner's explicit handoff and unblock it. While the
  Definition of Done is open, run development-loop's critical-path audit
  across ALL independent ready scopes, including task lanes, model
  comparisons, case/proof repairs, and measured evaluator optimization.
  Assign each substantial ready scope to a separate routable owner and
  disjoint output path, or execute cheap direct work. For every unowned
  scope name the actual dependency, exclusive gate, or revisit predicate;
  an active owner on another lane is not a gate. Complete this audit before
  ending the turn. Preserve every launched model attempt's first outcome:
  a separately identified fresh repetition or experiment is allowed when
  its question, controls, qualification, denominator, and stop rule are
  stated. If stuck, give one concrete blocker to a rubber-duck agent for
  a falsifiable check or alternative; do not repeat the same brainstorm
  without new evidence. During live proof remain read-only around its
  candidate, worktree, fixture, and process. Time alone never triggers
  constraint-challenge. If no safe action is admissible, record each scope's
  exact blocker and revisit condition. When the shared Definition of Done is
  verified, stop BOTH registered schedules and verify absence."
```

The charter remains authoritative for skill and compaction policy. Both
reminders carry the same off-switch and must reconcile against both registry
entries. Do not let the hourly nudge duplicate a live proof or mistake an
immutable first outcome for a blanket ban on new experiments.

**Complete when** the charter names its governing, execution, and context
skills, the registry holds both returned IDs, and `manage_schedule
action=list` shows exactly one matching reminder at each cadence and no legacy
challenge schedule pointed at the charter. A same-session compact is forbidden
until both reminders are live.

### 3. Hand off `/autopilot` through native command invocation
After the charter exists and both reminders are live, invoke
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
Without it, the /every charter check and progress nudge repair stale state and
keep ready work moving, but do not provide the same persistent objective:

Paste `/autopilot ` followed by the complete contents of <objective-file>.
```

If `/allow-all` is needed, print it for the user; never include it in the SDK
handoff. The detached helper reports post-launch failure through its receipt and
macOS notification. The native objective drives what to finish; the four-hour
check repairs stale state, the hourly nudge advances ready work, and event
triggers drive normal re-briefs.

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

**Complete when** both registered schedules are stopped and the verified
task has finished normally.
