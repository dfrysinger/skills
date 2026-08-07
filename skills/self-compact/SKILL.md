---
name: self-compact
description: Keep Copilot CLI working context lean while preserving decisions, active state, drafts, and session-bound resources through deliberate compaction. Use when a task finishes, work changes phase, a review round ends, tool history grows, the agent becomes stuck or repetitive, a durable work order enables a soft reset, or a long-lived session needs retirement.
---

# self-compact

Compact a Copilot CLI conversation without squeezing the retained state into
the editor command. The full compaction payload lives in the final assistant
message. The helper submits one short control and resumes with one fixed wake.

## Prerequisites

- Copilot CLI running inside tmux.
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

### 2. Emit the final brief

Make the final assistant prose before the helper call use this exact structure:

```text
SELF_COMPACT_BRIEF

Keep: <complete load-bearing baton>

Drop: <resolved and disposable context>

After compaction: <exact next action>; do not compact again.
```

The first line must be exactly `SELF_COMPACT_BRIEF`. `Keep:` must be nonempty.
`Drop:` must be present. `After compaction:` must be nonempty and contain the
case-sensitive literal `do not compact again`. `Keep:` content and the complete
`After compaction:` instruction, including that literal, must be on the same
physical line as their labels. Additional detail may continue on later lines.

Default to exactly these three labeled lines and keep the whole brief under
800 characters. Exceed that only when unrecoverable session-bound state cannot
fit; never exceed it merely to summarize the conversation or copy a durable
artifact. A normal brief looks like:

```text
SELF_COMPACT_BRIEF

Keep: Continue from `docs/feature-plan.md` in `/worktree` on `feature/x`; watcher PID 123 remains intentionally paused.

Drop: Resolved history and tool output already reflected in the plan.

After compaction: Re-read the plan baton, confirm PID 123 is still paused, and execute its next unchecked item; do not compact again.
```

The brief is part of the conversation and is not typed into the editor.

### 3. Submit as the final tool action

Run the helper with no arguments:

```sh
"$HOME/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh"
```

Use that exact double-quoted canonical `$HOME` path. Tilde, arguments,
assignments, redirections, pipelines, and composed shell commands are not
supported. The verifier resolves that one portable spelling to the installed
helper and rejects every other expansion or composition. Set the Bash tool's
`initial_wait` to at least 120 seconds for compatibility with older installed
versions and to keep startup errors in the initiating turn.

Old positional steers and `--continuation` are errors. Do not shorten the brief
or retry with invented instructions when a run fails.

The foreground helper records its root-agent Bash tool-call identity, transfers
the session lock to a detached verifier, writes a positive handoff, and returns
without mutating the editor. After the initiating interaction has persisted and
quiesced, the verifier binds that tool call to the complete brief and submits:

```text
/compact Use SELF_COMPACT_BRIEF. B:<8-hex>
```

The token identifies this run in `session.compaction_complete`. It is not
required to appear in checkpoint prose.

After the helper reports that the verifier is armed, end the turn. Ordinary
closing narration is allowed, but do not make another tool call.

## Safety contract

### Draft isolation

Immediately before typing the control command, the shared input helper:

- refreshes attached tmux clients and stabilizes the prompt capture;
- verifies a UTF-8 locale before parsing Copilot's Unicode editor;
- uses Ctrl-S to classify and stash visible or hidden drafts;
- requires an observably empty editor before one literal paste;
- preserves logical row boundaries and rejects multiline ownership;
- cancels on new user or assistant activity;
- bounds Ctrl-U and Esc recovery and restores any temporary geometry change.

A restored or modified draft cannot be submitted as the compact command. If
the run observed or stashed any draft, Enter requires an exact stable one-row
render of the control command.

### Timed ambiguous-render fallback

When the editor was genuinely empty and no visible or hidden draft was observed
or stashed, the compact command may use a bounded fallback:

1. Paste the fixed command once.
2. Prefer exact one-row verification for five seconds.
3. If rendering remains empty, unreadable, or unstable, wait up to a total of
   30 seconds while checking activity and menu state.
4. Press Enter once only if no readable mismatch, multiline buffer, menu, or
   activity appeared.

A known prefix, suffix, altered byte, restored draft, or second prompt row
always fails closed. The continuation never uses this fallback.

### Run exclusion and completion identity

One session-scoped owner-token lock excludes concurrent helper runs. Ownership
passes to the detached watcher before editor mutation. Ambiguous transferred
locks fail closed rather than allowing a second compact.

The watcher accepts only the first completion after the observed compact start
when all of these match:

- `success` is true;
- `customInstructions` contains this run's exact token-bearing instruction;
- `checkpointNumber` advances beyond the baseline summary count;
- `workspace.yaml` reaches that checkpoint number; and
- exactly one numbered checkpoint file exists.

Checkpoint prose is not searched for a marker.

### Continuation

When no post-compact activity already exists, the watcher submits this exact
strictly verified wake:

```text
Compaction done; resume, do not compact.
```

The resumed agent reads the generated checkpoint and follows the
`After compaction:` instruction from the brief. The watcher is one-shot. It
does not retry compaction or shorten instructions.

## Outside tmux

Do not claim automatic submission. Emit the complete `SELF_COMPACT_BRIEF`, then
give the user this command:

```text
/compact Use SELF_COMPACT_BRIEF.
```

After compaction, the user can send:

```text
Compaction done; resume, do not compact.
```

## Failure handling

- Missing or malformed current-turn brief: write the required structure and
  invoke the helper once more as the final action.
- Existing or ambiguous session lock: inspect the exact lock path reported by
  the helper. Do not delete it while a watcher is live.
- Command mismatch, multiline input, activity, or draft-bearing unreadable
  rendering: the helper sends no Enter.
- No compaction start, failed completion, wrong token, missing checkpoint, or
  continuation mismatch: the watcher exits without retrying.
- A compact that succeeded without continuation: send the fixed continuation
  manually. Do not rerun the compact helper.

Detached failures remain in the per-run log under the active session's
`files/` directory and do not create a tmux crash overlay.

## Verification

- The final assistant message contains the complete brief structure.
- The helper was invoked with zero arguments and `initial_wait` of at least 120
  seconds as the final tool action.
- The compact event records this run's token-bearing custom instructions.
- The checkpoint number advances and its file exists without requiring marker
  prose.
- The fixed continuation occurs only when no post-compact activity exists.
- Any preserved draft returns unchanged.
- No second compact, watcher, or session lock remains after completion.
