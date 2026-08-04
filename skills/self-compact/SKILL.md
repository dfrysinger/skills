---
name: self-compact
description: Keep Copilot CLI working context lean while preserving decisions, active state, and session-bound resources through deliberate compaction. Use when a task finishes, work changes phase, a review round ends, tool history grows, the agent becomes stuck or repetitive, a durable work order enables a soft reset, or a long-lived session needs retirement.
---

# self-compact

Keep the working context small without losing the state needed to continue.
Choose the lightest reset that fits; cross-agent handoffs remain owned by
`handoff`.

## When to use

- A task, implementation phase, debugging phase, or review round has ended.
- A long run of tool calls has made earlier output more distracting than useful.
- Progress becomes repetitive, confused, or stuck.
- A durable plan is complete enough to replace the conversation.
- A resumed session has become old or slow.

## Prerequisites

- Copilot CLI.
- `tmux` and `$TMUX_PANE` for verified self-submission.
- The `handoff` skill for soft resets, `/new`, or session retirement.

## Quick start

Persist any state that exists only in conversation, then make this the final
tool action of the turn:

```sh
~/.copilot/installed-plugins/_direct/dfrysinger--skills/skills/self-compact/scripts/submit-compact.sh \
  'Keep: <objective, decisions, current state, remaining work>. Drop: <resolved detail, superseded approaches, verbose output>.'
```

Outside tmux, give the user that `/compact` command to run directly.

## Procedure

### 1. Choose the compaction depth

- **Routine:** Keep the active objective, decisions, current state, and remaining
  work. Drop resolved detail and tool output.
- **Phase boundary:** Keep only the baton the next phase needs: durable artifact
  paths, branch, acceptance criteria, landed work, remaining work, and next
  action.
- **Soft reset:** When a durable artifact is a complete work order, invoke
  `handoff` for its null-steered `/compact` procedure. Keep session-bound
  schedules, SQL data, checkpoints, and files.
- **Session retirement:** When a multi-day session is slow or oversized, invoke
  `handoff` and `rotate-session` so a genuinely fresh session can recover the
  recorded state.

The chosen branch is complete when it preserves everything needed for the next
action without retaining resolved history. Prefer routine compaction after
landing work so the user can still ask why; reserve a soft reset for work that
already has a complete durable brief.

### 2. Persist load-bearing state

For active multi-step work, update the existing plan, design, issue, or other
durable artifact with:

- objective and acceptance criteria;
- decisions and non-goals;
- branch, relevant paths, and current runtime state;
- what landed versus what remains;
- blockers and the exact next action.

Do not create a planning document for a trivial completed task. Git state and
the resulting commit are sufficient when no unwritten decision or follow-up
would be lost.

This step is complete when deleting the conversation would not erase any fact
required to continue correctly.

### 3. Write an explicit steer

Use both halves in one line:

```text
Keep: <exhaustive load-bearing state>; Drop: <resolved investigation, superseded options, repeated explanations, and verbose tool output>.
```

Keep the baton concise: name durable artifact paths and the next action instead
of copying the artifact's contents into the steer.

`/compact` changes chat history only. It does not alter files, git state,
session SQL, schedules, checkpoints, or session artifacts.

This step is complete when every retained item earns its place in the next
phase and every named dropped item is safe to forget.

### 4. Submit and stop

Run `scripts/submit-compact.sh` as the final tool action, passing a single-line
steer. The helper starts the watcher, then presses Ctrl-S exactly once
immediately before typing the command. Ctrl-S safely stashes any draft and is a
no-op when both the input and stash are empty; it is a toggle, so pressing it a
second time would restore the draft. The helper requires the input to remain
empty across several captures after stashing, then fails closed unless the full
command renders exactly and Enter clears the input. Before submitting, it arms a detached watcher against
the active session's `summary_count` and a unique marker that the compact must
preserve in its checkpoint. Watcher failures remain in the per-run log instead
of becoming tmux interface messages. The helper queues only
`/compact`; plain text sent during an active turn is steering, not a FIFO message
behind the slash command. After both the count and marker prove that specific
compact landed, the watcher checks the event log. If autopilot or another prompt
already started a post-compact turn, it exits. Otherwise it presses Ctrl-S
again to preserve any draft restored at turn end, then submits `proceed`
immediately. The stashed draft returns after that continuation turn, so no input
is discarded. Selected autopilot mode is not assumed to be a reliable wakeup.

After the helper reports that the compact was submitted and the watcher armed,
end the turn. Its log is written under the active session's `files/` directory.

When `$TMUX_PANE` is unavailable, print the exact steered `/compact` command for
the user instead of claiming it ran. If the helper says the steer is too long to
verify, shorten it by pointing to the durable artifact and run it again as the
final action.

This step is complete when the compact submission and watcher are both armed, or
the user has the exact compact command and knows to send `proceed` after it
finishes. A watcher failure after compaction is recorded in its log; send
`proceed` manually rather than rerunning the helper and queuing a second compact.

## Pitfalls

- A vague steer preserves noise and may discard the real baton.
- Conversation-only plans can silently narrow during compaction.
- Repeating a complete durable plan in the steer can exceed the visible input;
  reference its path instead.
- A soft reset immediately after landing erases useful rationale the user may
  still want to question.
- Plain text submitted while the agent is active becomes steering and can run
  before a queued `/compact`; continuation must wait for that compact's unique
  checkpoint marker and `summary_count` advance.
- Autopilot can remain visibly selected without generating a post-compact turn.
- `/new` strands session-bound state; use it only when preserving the old
  conversation matters.
- `/clear` destroys session state rather than cleaning working context.

## Verification

- Load-bearing state exists outside the conversation when needed.
- The steer names both what survives and what disappears.
- The helper reports `submitted compact; post-compact continuation watcher
  armed`, names its log, and no later tool call runs in that turn.
