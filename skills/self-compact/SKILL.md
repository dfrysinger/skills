---
name: self-compact
description: Keep Copilot CLI working context lean while preserving decisions, active state, drafts, and session-bound resources through deliberate compaction. Use when a task finishes, work changes phase, a review round ends, tool history grows, the agent becomes stuck or repetitive, a durable work order enables a soft reset, or a long-lived session needs retirement.
---

# self-compact

Compact a Copilot CLI conversation through the private `self_compact` extension
tool and the session-inbox SDK extension. The complete compaction payload stays
in the structured tool call instead of visible assistant prose. A detached
verifier binds that exact tool invocation to one run token, waits for the turn
to become idle, requests native compaction, and sends one fixed continuation.

## Prerequisites

- Copilot CLI with the plugin's `self-compact` and `session-inbox` extensions
  loaded.
- A durable plan, design, issue, handoff, or charter for any state that must
  survive independently of the conversation.
- `handoff` for session retirement or a soft reset built around a standing
  brief.

## Procedure

### 1. Choose what survives

The native compactor already reads and summarizes the conversation. The brief
is a steering delta for facts the generated checkpoint might not preserve
precisely; it is not a second session summary.

Prefer one durable baton pointer plus only exceptional live state:

- the authoritative plan, charter, issue, handoff, or receipt path;
- the active workspace or branch only when the pointer does not establish it;
- session-bound resources that cannot be recovered from the durable baton,
  such as a live PID, paused watcher, authenticated profile, or running agent;
- one exact next action.

Do **not** restate completed work, review findings, validation results, the
remaining plan sequence, acceptance criteria, or decisions already present in
the durable baton. Update that artifact before compacting instead. Drop
resolved investigation and tool output generically rather than enumerating
them.

### 2. Build the private brief

Build one `brief` string with this exact structure:

```text
Keep: <complete load-bearing baton>

Drop: <resolved and disposable context>

After compaction: <exact next action>; do not compact again.
```

`Keep:` must be the first line and must be nonempty. `Drop:` must be present.
`After compaction:` must be nonempty and contain the case-sensitive literal
`do not compact again`. `Keep:` content and the complete `After compaction:`
instruction, including that literal, must be on the same physical line as
their labels. Additional detail may continue on later lines.

Default to exactly these three labeled lines and keep the whole brief under
800 characters. Exceed that only when unrecoverable session-bound state cannot
fit; never exceed it merely to summarize the conversation or copy a durable
artifact.

Do not print this brief in assistant prose. It belongs only in the structured
tool argument, where it remains available in collapsible tool activity and the
private session event record for debugging.

### 3. Submit as the final action

Call `self_compact` with exactly one argument, `brief`, containing the string
from step 2. Make it the only tool request in the final root assistant turn.
After it reports that the SDK verifier is armed, end the turn immediately:
write no closing narration and make no other tool call.

The extension validates the brief and invokes the private submitter with only
the current session ID and SDK tool-call ID. The submitter recovers the exact
brief from the persisted structured tool request, acquires a session-scoped
lock, starts a detached verifier, records a positive handoff, and returns
without reading or changing terminal input.

The verifier waits for that exact tool call and its assistant turn to finish,
then invokes:

```text
extensions/session-inbox/request.mjs compact
  --target-session <current session>
  --instructions-file <bound instructions>
  --continuation-file <fixed continuation>
  --timeout <bounded wait>
```

The instructions file contains the exact `brief` argument followed by:

```text
SELF_COMPACT_RUN_TOKEN: <8-lowercase-hex>
```

That exact token-bearing payload must appear on the matching compaction
completion event.

## Safety contract

### Draft non-interference

Self-compact does not capture the pane, type into the editor, press keys, stash
input, clear input, resize a window, or otherwise use tmux to drive Copilot.
The SDK request is handled only after the session is idle, so an unsubmitted
draft remains untouched.

### Current-turn authorization

The submitter accepts exactly one running root `self_compact` tool call whose
request:

- has the exact tool-call ID supplied by the extension;
- is the only tool request in its assistant message;
- contains one complete `brief` argument in the required current format; and
- has no conflicting root tool or user activity before execution.

The detached verifier requires the same tool-call identity, the exact handoff
receipt, and the end of that authorizing turn before creating the SDK request.

The request protocol has no event-boundary or cancellation field. The verifier
rejects conflicting root activity already persisted before enqueueing, but
activity that races after request creation can leave the request pending until
a later idle boundary. Do not interact with the session after the handoff until
the fixed continuation arrives.

### Run exclusion and one-shot behavior

One session-scoped owner-token lock excludes concurrent helper runs. The
verifier creates one request with a run-specific dedupe key and never retries
it.

A definitive failed receipt releases the lock. A timeout, missing receipt, or
missing token-bound completion is ambiguous and retains the lock so another
run cannot silently duplicate a compact. Do not delete an ambiguous lock
until its per-run log and session-inbox receipt directories establish the
outcome.

### Completion and checkpoint identity

After a completed SDK receipt, the verifier still requires:

- `success` on a root `session.compaction_complete` event;
- `customInstructions` equal to the exact brief plus this run's token;
- a checkpoint number greater than the baseline `summary_count`;
- `workspace.yaml` reaching that checkpoint number; and
- exactly one numbered checkpoint file.

Checkpoint prose is not searched for a marker.

### Continuation

The session-inbox extension submits this exact continuation through immediate
SDK delivery:

```text
Compaction done; resume, do not compact.
```

The extension subscribes before requesting compaction and requires the matching
successful `session.compaction_complete` event. A manual compaction can finish
while the session is already idle, so the CLI does not guarantee a later
`session.idle` transition. After a short state-settling interval, the extension
uses immediate delivery and verifies the result. If the continuation still
enters FIFO and cannot be promoted to steering, it removes the queued item and
fails the run instead of leaving delayed work behind.

The session-inbox receipt proves that the SDK accepted the message; it does not
depend on the CLI's FIFO queue. The verifier then requires exactly one matching
root `user.message` with native `idle` or `steering` delivery after the matching
completion. Queued delivery is rejected. It never types or retries the
continuation.

## Failure handling

- The fixed continuation belongs only to a compaction initiated through this
  skill's `self_compact` tool. Native threshold compactions have no bound
  continuation file and will not emit `Compaction done; resume, do not
  compact.` Check for token-bearing `customInstructions` and a matching
  `self-compact-*.log` before diagnosing a missing continuation as this skill's
  failure.
- Missing or malformed tool brief: correct the structure and call
  `self_compact` once more as the final action.
- Existing or ambiguous session lock: inspect the exact lock and log paths
  reported by the tool; do not delete a live or outcome-ambiguous lock.
- Failed session-inbox receipt: inspect the per-run log. No compact was
  accepted, and the lock is released.
- Ambiguous request result or missing token-bound completion: inspect the
  per-run log plus `~/.copilot/session-inbox/{processing,completed,failed}`.
  Do not rerun while the lock remains.
- Successful compact with failed checkpoint or continuation verification:
  do not compact again. The exclusion lock remains. If continuation is absent,
  send the fixed continuation manually.

Detached output remains in the per-run log under the active session's `files/`
directory.

## Verification

- The final assistant message does not expose the brief.
- `self_compact` was the only and final tool request, with one `brief` argument.
- The per-run log contains one completed session-inbox receipt.
- The compact event records the exact brief and run token.
- The checkpoint number advances and exactly one numbered file exists.
- The fixed continuation occurs exactly once.
- Existing terminal input is unchanged.
- No second request, live verifier, or non-ambiguous session lock remains.
