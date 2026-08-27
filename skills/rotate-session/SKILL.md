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

### 2. Carry the schedules over yourself

`/new` starts a **new session**. The old one's `plan.md`, `checkpoints/`,
`files/`, SQL tables, and transcript stay on disk and get read back in step 3,
but **armed `/every` schedules do not carry over**. They stay bound to the old
session, and the fresh session cannot re-arm what it cannot see.

So run `manage_schedule action=list` first, and if anything is live, append its
interval and prompt text to the seed prompt below with an instruction to re-arm
it. Tell the user which ones you carried.

### 3. Rotate

The bundled script targets the old session by ID through the session-inbox SDK
extension. It does not require tmux or terminal rendering.

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

The template asks only for `todos`, so name any custom SQL tables that matter.
The fresh session reads recorded state, not live state.

Run the script rather than sending `/new` yourself. It snapshots the seed and
opens the durable result log synchronously, then backgrounds one session-inbox
request equivalent to:

```text
new-session --target-session OLD --prompt-file SEED
```

The target extension places `/new` in the old session's native FIFO command
queue immediately. The CLI chooses when it executes the command. The request
is one-shot: the script never retries `/new` or resends the seed.

```sh
OLD='<old-session-id>'
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
  "$OLD" "$SEED" --consume-prompt
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

Make this the **last action of the turn** and end the turn, because `/new`
replaces the conversation you are running in. The script backgrounds itself, so
it returns `rotation requested` immediately and writes the request path,
extension receipt, and final result to the log afterwards.

A completed `new-session` receipt means the local CLI accepted the queued
`/new`; it is not the final proof. The script then requires exactly one fresh
replacement heartbeat from the same local CLI process, with an update after
that receipt, and verifies the exact seed in the replacement event log before
removing the recovery snapshot. If `/new` tears down the old extension before
it can write the receipt, a request-bound command marker supplies the same
process lineage and boundary for verification. The fresh session must still
read the result log during recovery. A failure or timeout with no verified
replacement preserves the private recovery snapshot and warns that the request
may still be queued. Do not issue another rotation until the first request's
outcome is resolved.

**Complete when** the script has printed `rotation requested` and you have ended
the turn without further tool calls. The fresh session confirms the outcome
from `/tmp/rotate-session-<OLD>.log`. If you are still running after the request
should have completed, report the logged result rather than assuming rotation.

## Notes

- If the log reports a failed or timed-out request, the prompt is in the private
  recovery file it names. Resolve the existing request receipt before deciding
  whether to paste or retry anything.
- Reading `~/.copilot/session-state` sits outside most agent workspaces, so the
  fresh session may hit an "Allow directory access" prompt. Choosing "add these
  directories to the allowed list" makes it one-time.
- To reclaim context **without** leaving the session, use the soft reset in the
  `handoff` skill instead, which keeps schedules and SQL live. Rotate only when
  the on-disk event log is the problem.
