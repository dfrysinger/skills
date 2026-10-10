---
name: rotate-session
description: Rotate a long-lived Copilot CLI session into a fresh one that rebuilds context by reading the old session's plan, checkpoints, todos, and transcript off disk. Use when the user says "rotate this session" or "start fresh but keep where we are", or when a session has grown slow to load or fails to load at all.
argument-hint: "Optionally, what the fresh session should focus on first."
---

# rotate-session

Copilot replays a session's whole event log on resume, so a session carried for
weeks grows into the gigabytes and eventually fails to load, leaving an agent
with no history. Rotating early avoids that. The old session keeps its own
state, so a mistimed rotation costs nothing: resume its id.

## Steps

### 1. Find the current session id

It is the last path component of the session folder named in your session
context. If that isn't available, walk up from your own shell to the `copilot`
process that owns the session lock. Do not just take the newest lock, which
usually belongs to a different agent:

```sh
p=$$
while [ "$p" -gt 1 ]; do
  f=$(ls ~/.copilot/session-state/*/inuse."$p".lock 2>/dev/null | head -1)
  if [ -n "$f" ]; then basename "$(dirname "$f")"; break; fi
  p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
  [ -z "$p" ] && break
done
```

### 2. Inventory mode, objective, and schedules independently

Rotation starts a **new session**. The old one's `plan.md`, `checkpoints/`,
`files/`, SQL tables, and transcript stay on disk and get read back in step 3,
but **selected agent mode, native `/autopilot` objective, and armed `/every`
schedules do not carry over**. Do not require an active charter to preserve
mode or unrelated schedules.

Run `manage_schedule action=list` first and record every live interval and
exact prompt and whether it is an unattended-run charter check or progress
nudge. Identify those reminders by their live prompts and reconcile their
charter path, plan, Definition of Done, and registry against the persisted
charter. The fresh session re-arms every unrelated live schedule with its
recorded cadence and prompt. Give charter reminders to `unattended-run` to
reconcile and re-arm instead of replaying their old prompts first; otherwise
duplicates can result. Old schedule IDs never transfer. Tell the user which
schedules were carried.

Read the last root `user.message` agent mode and **only the status** of the
native objective from this session's own state. Do not print objective text
while inventorying. The latest user-message mode is a recorded selection,
not proof that the user has not switched modes since that message; confirm
against the currently visible CLI mode before rotation. If neither source
establishes the selected mode, ask rather than guessing. An active native
objective and a visibly disabled autopilot mode are conflicting signals;
resolve that conflict before rotating. A `completed` objective does not
become active again just because autopilot mode is still selected.

```sh
OLD='<old-session-id>'
python3 - "$HOME/.copilot/session-state/$OLD" <<'PY'
import json
import sys
from pathlib import Path

folder = Path(sys.argv[1])
mode = "unknown"
with (folder / "events.jsonl").open() as events:
    for line in events:
        event = json.loads(line)
        if event.get("type") == "user.message" and not event.get("agentId"):
            mode = event.get("data", {}).get("agentMode") or mode
path = folder / "autopilot-objective.json"
status = "missing"
if path.exists():
    try:
        state = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid native objective state: {error.msg}")
    current = state.get("current") if isinstance(state, dict) else None
    status = current.get("status", "missing") if isinstance(current, dict) else "missing"
print(f"mode={mode} objective={status}")
PY
```

When the selected mode is autopilot, pass `--mode autopilot` to the rotation
script; otherwise omit it. A recorded `current.status` of `active` means
the objective needs an autonomous refresh through `unattended-run` even if
no matching charter schedule exists. Include the plan/charter paths and
objective-file path if known; if no persisted brief exists, the fresh session
must recover scope from the retired native objective and create the brief
before refreshing it. A missing or completed objective is **not** a reason
to invent a new one. A malformed or unreadable objective state is a blocker
to objective migration; do not silently replace it.

**Complete when** the seed has the confirmed selected mode, objective status,
exact live schedule inventory, and resolvable pointers for anything it must
refresh.

### 3. Rotate

For the normal macOS Agent Stack path, the bundled script verifies the current
tmux pane and exact old session lock, waits for the authorizing assistant turn
to end, disables pane input for the final activity check and replacement, then
starts a new Copilot process with a new UUID and the seed as its initial prompt.
Input is immediately restored on the replacement process or on any failure.
This is process replacement, not terminal typing: it does not use `send-keys`,
paste buffers, or the CLI FIFO.

Base the seed prompt on this, adding the schedules from step 2 and anything the
user wants the fresh session to do first:

```
You are continuing work from session <OLD>, which was retired because its
transcript grew too large. Your conversation history is empty but all of its
state is on disk under ~/.copilot/session-state/<OLD>. Before anything else
rebuild context from it, skipping quietly over whatever does not exist: read
plan.md; read the three newest files in checkpoints/; list files/; run sqlite3
on session.db for "SELECT id,title,status FROM todos WHERE status != 'done'";
read the tail of the conversation with the session_store_sql tool using
source=local: SELECT turn_index,user_message,assistant_response FROM turns
WHERE session_id='<OLD>' ORDER BY turn_index DESC LIMIT 15; and read
/tmp/rotate-session-<OLD>.log, which records how this rotation went. Then
summarize where things stand and what you believe the next step is, and wait
for my go-ahead before acting.
```

Always add this state inventory to the seed, replacing its last sentence with
the applicable recovery instruction below:

```
Retired state: selected mode <MODE>; native objective <STATUS>; plan
<PLAN_PATH_OR_NOT_RECORDED>; charter <CHARTER_PATH_OR_NOT_RECORDED>;
objective file <OBJECTIVE_PATH_OR_NOT_RECORDED>; Definition of Done
<HEADING_OR_NOT_RECORDED>. Live schedules (interval and exact prompt):
<SCHEDULES_OR_NONE>. After rebuilding context, confirm the rotation log
and recheck the retired objective status and latest plan baton. If any
brief or schedule prompt points inside the retired session, copy that
artifact to a durable path owned by this session and update its pointers
before scheduling. Re-arm unrelated schedules at their recorded cadences
and prompts, using new IDs; do not duplicate charter reminders.

If the objective remains active and its Definition of Done is not met,
invoke /dfrysinger-skills:unattended-run. Reconcile the existing plan and
charter or create a brief if none was recorded. Read the retired native
objective only if needed to recover its scope and boundaries. Derive a
new concise objective from the latest baton and current progress, not a
copy of the retired objective. Use unattended-run to reconcile and arm
exactly one four-hour charter check and one hourly progress nudge with NEW
schedule IDs, then hand the new objective to native /autopilot through
its SDK helper as the final action of that turn. End the turn so work
continues autonomously; do not wait for another go-ahead.

If the retired objective has completed or the Definition of Done is met,
do not restart it. Preserve the selected mode independently and reconcile
all live schedules. For a live charter whose work is not done, invoke
unattended-run only to rebind its reminders and registry; do not establish
a new native objective. Apply the charter's normal off-switch when
completion is verified. With no active objective, do not invent one.
Summarize the current state and wait for my go-ahead before starting new
work.
If migration fails, state the exact missing predicate rather than silently
discarding state or running a stale objective.
```

The fresh session must confirm the replacement session's seed and rotation
result before arming anything. If the selected mode was autopilot, the
launcher preserves it independently of objective status. Do not pass an
active objective to the launcher as raw prompt text.

The template asks only for `todos`, so name any custom SQL tables that matter.
The fresh session reads recorded state, not live state.

Run the script rather than sending `/new` yourself. It snapshots the seed and
opens the durable result log synchronously. Under tmux it starts one short-lived
detached verifier, which waits for the current turn boundary before calling
`tmux respawn-pane` with a private launcher. The launcher starts the fresh
session with an explicit UUID, preserves the pane's name, working directory,
remote mode, and allow-all mode, and supplies the exact seed through
`--interactive`.

Automated rotation is supported only from the current Copilot tmux pane.
Outside tmux, the script fails before consuming or snapshotting the prompt.
Never replace this with FIFO submission or terminal input injection.

```bash
OLD='<old-session-id>'
SELECTED_MODE='<confirmed-mode>'
MODE_ARGS=()
if [ "$SELECTED_MODE" = autopilot ]; then MODE_ARGS=(--mode autopilot); fi
SEED=$(mktemp "${TMPDIR:-/tmp}/copilot-rotate-input-${OLD}.XXXXXX") || exit 1
trap 'rm -f -- "$SEED"' EXIT
if ! cat >"$SEED" <<'PROMPT'
<the seed prompt from above>
PROMPT
then
  echo "Could not write rotation seed" >&2
  exit 1
fi
[ -s "$SEED" ] || { echo "Rotation seed is empty" >&2; exit 1; }

~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/rotate-session/scripts/rotate.sh \
  "$OLD" "$SEED" --consume-prompt "${MODE_ARGS[@]}"
```

Use the unique `mktemp` path exactly as shown. A fixed `/tmp/rotate-seed.txt`
can be overwritten by another agent rotating at the same time. The script
synchronously snapshots and validates the prompt before it backgrounds, then
consumes the temporary input only because the caller passes
`--consume-prompt`. The seed prompt must contain the exact value of `OLD`; this
binds the recovery instructions to the session being retired. A failed
rotation preserves only its private recovery snapshot and names that file in
the log. If creating or writing the seed fails, stop; never inspect or reuse an
existing seed file.

Make this the **last action of the turn** and end the turn, because the pane's
current Copilot process will be replaced. The script returns
`rotation requested` immediately and writes the replacement UUID and final
result to the log afterwards.

The verifier requires the old turn to end without intervening user activity,
then requires the exact seed to be the replacement session's first root user
message before removing the recovery snapshot. The fresh session must still
read the result log during recovery. Unsupported, failed, ambiguous, or
timed-out rotation preserves the private recovery snapshot. Do not issue
another rotation until the first request's outcome is resolved.

At the replacement boundary, the verifier disables pane input and creates
`rotation.barrier` in the retired session folder. The session-control extension
rejects new work while that barrier exists, and the verifier cancels if an
older request is still executing. A successful rotation leaves the barrier on
the retired session so delayed mailbox or continuation requests cannot wake it
later. If the user intentionally resumes the retired session for active work,
remove that barrier first.

**Complete when** the script has printed `rotation requested` and you have ended
the turn without further tool calls. The fresh session confirms the outcome
from `/tmp/rotate-session-<OLD>.log`. If you are still running after the request
should have completed, report the logged result rather than assuming rotation.

## Notes

- If the log reports an unsupported, failed, or timed-out request, the prompt
  is in the private recovery file it names. Resolve any ambiguous request
  receipt before deciding whether to submit it manually or retry anything.
- The supported automated path requires tmux. It deliberately replaces the
  pane process only after the authorizing turn ends; it never types into the
  pane.
- Reading `~/.copilot/session-state` sits outside most agent workspaces, so the
  fresh session may hit an "Allow directory access" prompt. Choosing "add these
  directories to the allowed list" makes it one-time.
- To reclaim context **without** leaving the session, use the soft reset in the
  `handoff` skill instead, which keeps schedules and SQL live. Rotate only when
  the on-disk event log is the problem.
