# Self-Compact Brief Protocol

## Objective

Replace inline compaction steers with a long assistant-side
`SELF_COMPACT_BRIEF`, a fixed short control template, and a fixed continuation
so self-compaction preserves meaningful state without shortening instructions,
depending on checkpoint prose markers, confusing concurrent runs, or
initiating a second compact.

## Non-goals

- Do not change Copilot CLI, `/compact`, tmux, or the session event schema.
- Do not build a general editor-state or terminal-rendering API.
- Do not reconstruct visually wrapped rows or permit arbitrary multiline
  commands in Copilot's editor.
- Do not preserve the positional `<steer>` argument as a compatibility path.
  Old callers must fail before watcher creation or editor mutation rather than
  silently use the unsafe inline protocol.
- Do not preserve `--continuation` or any other caller-selected compact or wake
  argument. `submit-compact.sh` accepts zero arguments.
- Do not support caller-selected long continuation prompts. Continuation intent
  belongs in `SELF_COMPACT_BRIEF`; the watcher sends one fixed short wake.
- Do not make automatic compaction retries or semantic shortening part of the
  helper. A failed run ends and reports its reason.
- Do not parse general shell syntax. Supported callers invoke one canonical
  absolute helper path using one of three literal zero-argument spellings.
- Do not guarantee that every detail named in a brief will be retained by the
  compaction model. The protocol guarantees that the full brief is available
  to that model and proves the resulting checkpoint through observable facts
  in live acceptance.

## Lane

**Critical.** The helper mutates a live editor that can contain an unsubmitted
user draft, and this design adds a bounded path that may press Enter without a
readable exact post-paste rendering. The boundary must fail closed before
typing unless the current assistant turn contains the brief and the editor was
observed empty immediately before the one allowed paste. It must never submit a
known mismatched or multiline buffer.

## Evidence and cause

### Hotel: inline steering degraded the retained state

The v0.100 helper wrapped every steer in:

```text
/compact <steer> Keep SCM:<8-hex-epoch>-<5-hex-pid>
```

Hotel's 52-column pane safely allowed 48 columns. The 33-column wrapper left
only 15 columns for the steer, so the useful
`Keep: 0f685b65 done; Drop: logs.` instruction was rejected. The calling agent
eventually shortened it to `Keep:1;Drop:`. Compaction succeeded, but the
generated checkpoint omitted the `SCM:` marker. The watcher therefore timed
out after a successful compact and did not continue.

The earliest divergence was the protocol's requirement that both meaning and
identity fit in one verified editor row. That requirement caused semantic
degradation, while checkpoint-prose marker matching still did not provide
reliable identity.

### Sierra: split payload and control succeeded

Sierra emitted a long assistant message headed `SELF_COMPACT_BRIEF`, including
three assistant-only identifiers, and then received:

```text
/compact Use SELF_COMPACT_BRIEF above.
```

The successful `session.compaction_complete` event recorded the exact
`customInstructions`, advanced the session summary count, and named checkpoint
010. That checkpoint retained the objective and all three identifiers.

The first typing attempt also exposed a draft race. The saved draft restored
after the brief-producing turn, so the editor contained:

```text
SIERRA_V100B_DRAFT/compact Use SELF_COMPACT_BRIEF above.
```

Exact verification prevented Enter. Re-stashing immediately before typing
made the second attempt safe.

After compaction, plain `proceed` caused Sierra to interpret the checkpoint's
next step as an instruction to compact again. The duplicate helper was stopped
before a second compact completed. This proves that a generic continuation is
not sufficiently bounded.

The live receipt is:

```text
~/.copilot/session-state/dc8dcc47-cbbc-5f0e-87fd-043acec5e7ae/files/sierra-self-compact-brief-20260804T1809Z/RESULT.md
```

## Reuse contract

The implementation reuses the existing ownership boundaries:

- `submit-compact.sh` remains the only foreground entry point. It resolves the
  active session, identifies its own `tool.execution_start` and `toolCallId`,
  acquires the lock, starts the watcher, writes a positive handoff token, and
  returns without editor mutation.
- `resume-after-compact.sh` remains the one-shot detached watcher. It adds
  persisted invocation authorization before its existing submission,
  completion proof, and continuation duties.
- `input-recovery.sh` remains the sole owner of UTF-8 locale selection, tmux
  capture, redraw, Ctrl-S transition classification, exact one-row comparison,
  activity cancellation, bounded clearing, and geometry restoration.
- `events.jsonl`, `workspace.yaml`, and the generated checkpoint file remain
  the authoritative state. No second state database or marker file is added.

New protocol-specific logic is required because the existing helper combines
three concerns that the live failures proved must be separated:

1. semantic payload, which may be long and belongs in conversation;
2. editor control, which must remain short and exactly bounded; and
3. compaction identity, which belongs in the event stream rather than generated
   checkpoint prose.

## Protocol

### 1. Emit `SELF_COMPACT_BRIEF`

Immediately before calling the helper, the agent emits one assistant message
whose first line is exactly:

```text
SELF_COMPACT_BRIEF
```

The brief is a work-order-style baton, not a compressed command. It contains:

- **Keep:** objective, decisions, active state, durable artifact paths,
  session-bound resources, and the next action;
- **Drop:** resolved investigation, superseded approaches, repeated
  explanation, and verbose tool output;
- **After compaction:** the action the resumed agent must perform, including
  the case-sensitive literal `do not compact again` as part of the
  continuation instruction.

For a soft-reset handoff, the brief may instruct the compaction model to make a
standing brief that points at the durable handoff and governing skills. For an
unattended run, it names the charter path and says exactly how to resume the
charter. The fixed watcher wake does not carry those long instructions.

The helper accepts zero arguments. A positional steer, `--continuation`, or any
other argument exits with status 2 before workspace resolution, lock
acquisition, watcher creation, run files, Ctrl-S, typing, or Enter.

The foreground helper returns after transferring ownership to its detached
watcher. The watcher, not the Bash tool subprocess, validates the brief and
submits the compact command. Callers still set `initial_wait` to at least 120
seconds for compatibility with older installed versions and to keep helper
startup errors in the initiating turn, but correctness no longer depends on
the assistant message becoming readable while the foreground tool is running.

### 2. Bind the persisted brief to this helper invocation

Copilot records logical event order before it guarantees that the corresponding
JSON lines are readable by a running tool subprocess. A valid
`assistant.message` can therefore remain unavailable until after its Bash tool
has exited. The foreground helper must not use same-process event visibility as
an authorization gate.

At startup, the foreground helper reads the latest visible event record and
filters to root-agent records whose top-level `agentId` is null. It requires
the most recent root-agent `tool.execution_start` to name the Bash tool, carry
a nonempty `toolCallId`, and have no later root-agent completion with that ID.
It records that candidate ID in owner-protected run metadata. Stale older
uncompleted Bash starts and interleaved subagent events do not create
ambiguity. If another root-agent start follows this candidate, or the detached
watcher later finds that the candidate is not the sole exact canonical helper
request, authorization fails closed before editor mutation.

After the foreground helper transfers the session lock and returns, the
detached watcher polls for one persisted authorization sequence keyed by that
recorded `toolCallId`. Every event in this authorization sequence must be a
root-agent event with top-level `agentId` null:

1. an `assistant.message` whose `toolRequests` array contains the recorded
   `toolCallId`;
2. exactly one `toolRequests` entry in that message;
3. that request names the Bash tool and carries one allowed literal
   zero-argument invocation of the foreground helper's canonical absolute
   path;
4. the already-recorded `tool.execution_start` with the same `toolCallId`;
5. a subsequent `tool.execution_complete` with the same `toolCallId`; and
6. the foreground-written positive `HANDOFF` artifact containing the owner
   token and `toolCallId`.

The brief may be in the tool-request message's `data.content`, or in the last
nonempty assistant `data.content` after the immediately preceding
`assistant.turn_start` and before that tool-request message. This supports both
runtime-observed event shapes: combined content plus tool request, and a
content-bearing message followed by a content-empty tool-only message. The
selected brief content must have all of this structure:

1. first line exactly `SELF_COMPACT_BRIEF`;
2. nonempty `Keep:` content on the same physical line as its label;
3. a `Drop:` section; and
4. a nonempty `After compaction:` instruction on the same physical line as its
   label, containing the case-sensitive literal `do not compact again`.

Brief authorization comes only from `data.content`. The tool request binds that
content to this invocation but cannot provide or complete the brief. A heading,
section, or no-recompact phrase found only in tool arguments does not qualify.
The allowed command spellings are generated from the foreground helper's
resolved absolute path: the bare path, the path enclosed in single quotes, or
the path enclosed in double quotes. No arguments, environment assignments,
shell expansions, redirections, separators, pipelines, or command
substitutions are accepted. Supported callers use the double-quoted canonical
absolute path.

An older brief from another assistant turn does not qualify. A user message,
checkpoint, tool argument, tool output, quoted design text, or ordinary
assistant narration that merely mentions the words does not qualify. A second
tool request in the same assistant message, a mismatched tool call ID, a
different helper command, a missing tool completion, or a missing or mismatched
`HANDOFF` cancels before editor mutation.

After the matched tool completion, the watcher waits for the initiating
interaction to quiesce. The runtime has three supported terminal shapes:

1. tool-free nonempty closing narration followed by
   `assistant.turn_end` in the authorizing turn;
2. direct `assistant.turn_end` with no closing narration, including a
   `session.task_complete` immediately before it; or
3. authorizing `assistant.turn_end`, then one tool-free closure assistant turn
   that starts, may contain ordinary nonempty narration, and ends.

After the authorizing turn ends, the watcher waits a short configurable
quiescence grace period, default two seconds. If no new event appears, shape 1
or 2 is complete and it records the activity baseline. If the next event begins
one assistant closure turn, it waits through that turn and records the baseline
at its end. A user message at any point after the authorizing tool request, any
tool request or tool execution after the matched completion, or a second
assistant turn before editor preparation is conflicting new work and cancels.
Passive lifecycle records such as `session.task_complete` do not count as new
work. Subagent events with non-null `agentId` are outside the root agent's
editor activity stream and are ignored throughout authorization, quiescence,
compaction identity, and post-compact activity checks.

The watcher waits a bounded 30 seconds for the complete persisted sequence,
positive handoff, tool completion, and one of the supported quiescent terminal
shapes.
Timeout, malformed JSON, ambiguous matches, or inability to establish the
binding releases the lock and exits without Ctrl-S, typing, or Enter. The event
baseline for activity and compaction identity is recorded only after
authorization.

### 3. Exclude concurrent helper runs

Before watcher creation or editor mutation, the submitter atomically acquires
one session-scoped lock directory under the active session's `files/`
directory. The lock carries:

- a unique owner token;
- foreground submitter PID;
- detached watcher PID after the watcher becomes ready;
- an atomically replaced state file whose value is `foreground`,
  `watcher-launching`, or `watcher-owned`; and
- creation time and run-file paths for diagnosis.

Only the owner token may update or release the lock. State-file replacement is
written to a sibling temporary file and renamed so readers never accept a
partially written transition.

The ownership sequence is:

1. The foreground acquires the directory in `foreground` state. Its trap may
   release the lock only while the state remains `foreground` and its owner
   token still matches.
2. Immediately before `tmux run-shell -b`, the foreground atomically changes
   the state to `watcher-launching`. From this transition onward, the
   foreground never releases the lock directly. Its exit trap writes
   `CANCELLED` unless the positive `HANDOFF` is already complete.
3. The watcher verifies the owner token, records its PID, atomically changes
   the state to `watcher-owned`, and only then writes `READY`.
4. The foreground observes `READY`, completes every remaining foreground
   check, atomically writes `HANDOFF` with the owner token and recorded
   `toolCallId`, reports that the verifier is armed, and returns without editor
   mutation.
5. Before `HANDOFF`, any foreground error, signal handled by its trap, or
   timeout writes `CANCELLED`. The watcher checks `CANCELLED` and `HANDOFF`
   before authorization and again immediately before editor preparation.
   Missing `HANDOFF`, mismatched handoff data, or `CANCELLED` releases without
   editor mutation. A hard kill before `HANDOFF` cannot authorize Enter; a live
   watcher times out and releases, while loss of both processes leaves the lock
   for inspection.
6. The watcher validates the persisted authorization sequence, records the
   post-authorization activity baseline, prepares and submits the compact
   command, and writes `ARMED` immediately before its final activity check and
   Enter.
7. The watcher is the only lock releaser in `watcher-owned` state and retains
   ownership through authorization, compact completion, continuation, timeout,
   or any fail-closed terminal path.

The watcher does not wait for a foreground-written `ARMED`; it owns that marker.
Before `ARMED`, a controlled watcher cancellation releases the lock. After
`ARMED`, a controlled cancellation holds through the existing compaction-start
deadline and follows the matching lifecycle if a start appears. An untrapped
watcher death after ownership transfer leaves the lock stranded for manual
inspection; it never makes a second compact eligible.

A second invocation exits before editor mutation whenever the lock exists,
except for one provably stale case: state is `foreground`, the owner token and
metadata are well formed, the recorded foreground PID is dead, and no
`watcher-launching`, watcher PID, `READY`, or `ARMED` evidence exists. Only that
state may be reclaimed automatically.

`watcher-launching`, `watcher-owned`, malformed metadata, a live recorded PID,
or any conflicting run-file combination is ambiguous and fails closed with the
exact lock path and cleanup guidance. PID death alone never permits reclaim
after watcher launch was attempted. This intentionally prefers a stranded lock
requiring inspection over an unobserved second compact.

The lock prevents two supported helper invocations from queuing compacts in the
same session. A compact control also carries a short per-run token, so a manual
or external compact cannot satisfy this watcher's event identity.

### 4. Use a fixed short control template

The submitter generates one eight-lowercase-hex run token before lock
acquisition. The compact control template is:

```text
/compact Use SELF_COMPACT_BRIEF. B:<8-hex>
```

The post-compact wake is:

```text
Compaction done; resume, do not compact.
```

The instantiated compact command is 43 columns and the continuation is 40
columns. Both are printable ASCII and must fit the current `pane_width - 4`
limit before lock acquisition or watcher start. The watcher rechecks its wake
command against the current width immediately before typing. Because
authorization is now deferred, the watcher also rechecks the compact command
against the current width immediately before its paste.

`B:<8-hex>` is event identity only. The checkpoint is not required to retain
it. There is no caller-controlled compact command. The submitter does not
shorten, rewrite, or retry either command.

### 5. Establish draft isolation immediately before typing

After persisted authorization, the watcher uses the shared input helper to
perform the Ctrl-S transition and prove the editor empty. This preparation
occurs immediately before control-command typing and after the brief-producing
foreground tool has returned.

The preparation contract is:

1. A visible draft becomes stashed and the editor becomes observably empty.
2. A hidden draft that becomes visible is re-stashed and the editor becomes
   observably empty.
3. A truly empty editor remains observably empty.
4. A readable nonempty or multiline residual is cleared only by the existing
   bounded, warned recovery path and must become observably empty.
5. Unknown or unstable state that cannot establish an empty editor does not
   authorize typing.

User or assistant activity after the event baseline cancels the attempt before
every editor mutation, capture, sleep boundary, and Enter.

The helper records whether this preparation observed or manipulated any visible
or hidden draft. That fact constrains the timed fallback below.

### 6. Submit by exact path or bounded timed fallback

The fixed compact command is delivered once as one literal paste. The helper
then uses one of two paths:

#### Exact path

If one stable captured prompt row is byte-for-byte equal to the fixed command,
the helper rechecks activity and presses Enter once.

#### Timed fallback

The fallback is allowed only when all of these are true:

- the editor was observed empty immediately before this one paste;
- preparation observed no visible draft, revealed no hidden draft, and did not
  stash or re-stash any text;
- no activity occurred after that observation;
- the command was pasted exactly once;
- the post-paste capture is empty, unreadable, or unstable, not a readable
  mismatch or multiline buffer;
- no concrete menu is visible;
- the helper has waited a configurable 20-30 second interval, default 25
  seconds, while checking activity before every capture and sleep boundary; and
- the final capture still does not show a readable mismatch or multiline
  buffer.

After those checks, the helper presses Enter once even though exact rendering
was not observable. If any draft existed or changed stash state during this
run, only the exact path may press Enter. A known prefix, suffix, altered
command, restored draft, or second prompt row always fails closed. Waiting is
never a substitute for the immediately preceding empty-editor proof.

If Enter submits nothing or compaction does not start, the existing short
start-deadline path cancels the watcher and clears only an exactly owned visible
control command. It does not retry or type a second command.

The fixed continuation remains on the strict exact path. There is no timed
fallback for continuation because a failed wake is recoverable through manual
input or the unattended run's schedule, while an ambiguous wake could submit a
restored draft after compaction.

### 7. Identify the completed compact from events

The watcher records:

- baseline event line;
- baseline `summary_count`;
- exact expected `customInstructions`, including the run's `B:<8-hex>` token;
  and
- the fixed continuation.

It waits for the first `session.compaction_start` after the event baseline,
using the existing turn-end/start deadline. It then evaluates the first
`session.compaction_complete` after that start.

The compact is accepted only when all are true:

1. `success` is `true`;
2. `customInstructions` is exactly
   `Use SELF_COMPACT_BRIEF. B:<this run's 8-hex token>`;
3. `checkpointNumber` is numeric and greater than the baseline
   `summary_count`;
4. `workspace.yaml` advances to at least that checkpoint number; and
5. exactly one checkpoint file with that zero-padded number exists under the
   session's `checkpoints/` directory.

A failed completion, a different custom instruction or token, a missing
checkpoint, or a summary count that does not advance ends the watcher without
continuation. The watcher evaluates the first completion after the observed
start and does not scan forward for a later matching token. Checkpoint prose is
never searched for a marker or phrase.

### 8. Resume without initiating another compact

After the accepted completion event, the watcher preserves the existing
post-compact activity race:

- if a user message or assistant turn already exists after completion, it does
  nothing;
- otherwise it waits the short grace period, prepares the fixed continuation
  through the strict exact path, and submits it once.

The continuation explicitly states that compaction is complete and forbids
another compact. The resumed agent reads the generated checkpoint and follows
the `After compaction` section inherited from `SELF_COMPACT_BRIEF`.

The watcher is one-shot. It cannot launch `submit-compact.sh`, rewrite a brief,
or retry failed compaction.

## Affected connection points

- `skills/self-compact/SKILL.md`
  - Replace inline steer instructions with the assistant-side brief template.
  - Require the `After compaction:` section to carry the case-sensitive literal
    `do not compact again`, matching the helper gate.
  - Document the fixed helper invocation, event identity, timed fallback, and
    no-retry rule.
- `skills/self-compact/scripts/submit-compact.sh`
  - Remove positional steer and marker creation.
  - Reject `--continuation` and every other argument.
  - Acquire and transfer the session-scoped run lock.
  - Record the latest visible uncompleted Bash start as the candidate
    `toolCallId` and record the canonical helper path for detached
    authorization.
  - Retain `CANCELLED` for pre-handoff failure and add atomic positive
    `HANDOFF`.
  - Return after watcher readiness without editor mutation.
- `skills/self-compact/scripts/resume-after-compact.sh`
  - Validate the persisted brief, recorded candidate call ID, exact
    tool-request/start/completion binding, positive handoff, and one supported
    quiescent terminal shape after the foreground helper returns.
  - Own editor preparation, fixed compact submission, and the bounded timed
    compact-only fallback.
  - Report expected deferred failures through the run log and bounded tmux
    status message.
  - Replace marker grep with exact completion-event and checkpoint-number
    verification.
  - Use the fixed explicit continuation.
- `skills/self-compact/scripts/input-recovery.sh`
  - Expose or refactor the smallest shared operations needed to separate
    empty-editor proof from post-paste exact verification.
  - Preserve all existing locale, redraw, activity, menu, and geometry
    behavior.
- `skills/self-compact/scripts/submit-compact.test.sh`
  - Replace marker/steer scenarios and add the Hotel and Sierra regressions.
- `skills/handoff/SKILL.md`
  - Put standing-brief and resume instructions in `SELF_COMPACT_BRIEF`; invoke
    the helper without a steer.
- `skills/unattended-run/SKILL.md`
  - Put charter continuation in `SELF_COMPACT_BRIEF`; rely on the fixed wake.
- `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and
  `.codex-plugin/plugin.json`
  - Publish the completed change as the next plugin version.

## Failure model

| Failure | Required behavior |
| --- | --- |
| Agent omits the current-turn brief | Watcher times out and releases without editor mutation |
| Old brief remains in history | Reject because it predates the current turn |
| Assistant or tool arguments merely mention the heading | Reject because the current `data.content` lacks the required structure |
| Assistant message is not readable until tool completion | Detached watcher validates it after foreground return |
| Assistant message was readable before foreground startup | Recorded `toolCallId` still binds the persisted request and brief |
| Brief and tool request are split across assistant messages in one turn | Use the last nonempty content before the bound request |
| Subagent events interleave before or after helper events | Ignore non-root `agentId` records; preserve root-agent authorization and activity state |
| Assistant message carries another tool request | Reject the ambiguous invocation before editor mutation |
| Tool call ID or exact helper command does not match | Reject before editor mutation |
| Foreground fails before positive handoff | `CANCELLED` or missing `HANDOFF`; zero editor mutation |
| Interaction ends directly or with same-turn narration | Wait through authorizing `assistant.turn_end`, then establish baseline after grace |
| Normal closing narration follows in a new turn | Permit exactly one tool-free closure turn, then establish baseline |
| User message or new tool activity follows authorization | Cancel before editor mutation |
| Brief is long | No command-width impact |
| Draft restores after the brief message | Immediate Ctrl-S preparation stashes it before typing |
| Any draft was observed or stashed | Timed fallback is disabled; only exact rendering may authorize Enter |
| Another helper owns the session lock | Exit before watcher or editor mutation |
| Lock ownership is malformed or ambiguous | Fail closed with cleanup guidance |
| Watcher is terminated after `ARMED` or Enter | Lock remains held through matching completion/no-start handling, or is stranded on untrapped death |
| Editor contains known residual text | Never Enter; preserve or boundedly clear under existing rules |
| Renderer lags or is unreadable after a proven-empty paste | Wait 20-30 seconds, then allow one compact Enter only if no known mismatch appears |
| User or assistant activity begins | Cancel before the next editor action |
| Compact command is altered or multiline | Never Enter |
| Compaction succeeds but checkpoint omits arbitrary prose | Accept from exact event and checkpoint number |
| Another compact with different instructions occurs | Do not continue it |
| Compaction fails or never starts | Exit one-shot; no retry or continuation |
| Checkpoint next step discusses compaction | Fixed continuation says compaction is already done and forbids another |
| Continuation cannot render exactly | Leave it unsent; manual input or `/every` remains the backstop |
| Deferred authorization fails | Write the exact reason to the run log and show a bounded tmux status message with the log path |
| Detached watcher crashes before it can report | Log-only failure; no tmux crash overlay |

## Hard invariants

1. The semantic compaction payload is never typed into the editor.
2. The submitter accepts zero arguments, including no positional steer and no
   `--continuation`, and performs no semantic shortening.
3. A structurally complete current-turn assistant `SELF_COMPACT_BRIEF` in
   `assistant.message.data.content`, structurally bound to the exact helper tool
   request and matching start/completion events, is required before editor
   mutation.
4. Editor emptiness is observed after the brief-producing message and
   immediately before the single control-command paste.
5. The watcher authorizes only the foreground-recorded candidate `toolCallId`,
   positive owner-token handoff, one valid brief in the same assistant turn as
   that request, matching start/completion, and one supported quiescent
   terminal shape.
6. Authorization, quiescence, compact identity, and activity checks consume
   only root-agent events with top-level `agentId` null; subagent events cannot
   authorize or cancel editor mutation.
7. A readable mismatch, prefix, suffix, restored draft, or multiline buffer
   never authorizes Enter.
8. Timed ambiguous submission is available only when no draft was observed or
   stashed, and only for the fixed compact command after proven emptiness, one
   paste, no activity, no menu, and a 20-30 second wait.
9. Exact one-row submission remains the preferred path.
10. The continuation always uses strict exact verification and never the timed
   fallback.
11. One session-scoped lock excludes concurrent supported helper runs, and a
   per-run token distinguishes this compact from external compacts.
12. Compaction identity comes from the first completion after the observed
    start and exact token-bearing `customInstructions`, not checkpoint prose.
13. Continuation requires successful completion, checkpoint-number advancement,
    checkpoint-file existence, and no post-compact activity.
14. The continuation states that compaction is complete and forbids another
    compact.
15. No helper or watcher retries compaction, launches itself, or invents a
    shorter instruction.
16. Expected detached failures are visible through a bounded tmux status
    message and durable run log; unexpected crashes remain log-only.
17. Existing UTF-8, activity, geometry, menu, key-count, and one-shot bounds
    remain in force unless this document explicitly replaces them.

## Acceptance criteria and deterministic check contract

| Criterion | Setup and transition | Pass signal | Failure proves |
| --- | --- | --- | --- |
| Long meaning is independent of pane width | Emit a multi-paragraph brief in a 52-column pane and invoke the helper | Fixed 43-column token-bearing compact command reaches submission without shortening the brief | Semantic payload still depends on editor width |
| Current-turn brief is mandatory | Invoke with no brief, an older-turn brief, a user-message mention, a tool-output mention, a tool-argument mention inside the assistant event, an ordinary assistant bare mention, content moved off the `Keep:` or `After compaction:` label line, a structurally incomplete brief, and a semantically similar `After compaction:` section that omits the literal `do not compact again` | The foreground may arm the watcher, but every case produces zero Ctrl-S, typing, or Enter and releases the lock | Stale, non-assistant, non-brief, or template-drifted text can authorize compaction |
| Both publication orders authorize | In one case persist the valid brief/request/start before foreground startup; in another expose only the start, let foreground return, then persist the brief/request ordering, completion, and terminal shape | Both cases bind the foreground-recorded `toolCallId` and submit exactly one compact | Same-process visibility timing or a line-count baseline remains an authorization dependency |
| Stale uncompleted starts do not confuse identity | Seed several older uncompleted Bash starts, make the current canonical helper start the latest visible start, and separately batch the helper with a sibling tool request | The supported sole request binds the latest candidate; the batched request fails closed | Historical interrupted tools disable the helper, or parallel tools can be mistaken for this invocation |
| Subagent traffic is isolated | Interleave non-null-`agentId` tool requests, starts, completions, assistant turns, and messages before, between, and after the root helper request, completion, and quiescence | Root-agent authorization succeeds exactly once and post-compact activity remains unchanged; equivalent root-agent events cancel | Background agents can steal invocation identity or falsely cancel the root editor lifecycle |
| Split assistant event shape authorizes | Put the valid brief in a nonempty assistant message and the sole helper request in the following content-empty message before tool start | The last valid content in that assistant turn authorizes | Runtime message composition can nondeterministically block the supported path |
| Authorization is structurally bound | Vary canonical-path quoting, added arguments, assignments, expansions, redirections, separators, pipelines, command substitutions, tool name, tool call ID, request count, completion presence, and completion identity | Only one allowed literal zero-argument Bash request with matching start and completion authorizes editor mutation | Arbitrary shell syntax, tool-argument prose, or an unrelated tool can authorize compaction |
| Positive handoff is mandatory | Fail or kill the foreground after watcher launch before `HANDOFF`; separately complete `HANDOFF` and then return normally | Missing/cancelled handoff produces zero editor mutation; complete owner-token/call-ID handoff remains eligible | Tool completion can authorize after the foreground reported failure |
| All observed terminal shapes quiesce | After matched completion, exercise same-turn narration plus end, direct end including `session.task_complete`, and one nonempty tool-free closure turn; separately add a user message, tool request/execution, or second assistant turn | All three quiescent shapes remain eligible; every new-work variant produces zero editor mutation | Normal turn completion is confused with resumed work, or the exemption admits real new work |
| Deferred failure is observable | Cause authorization timeout and malformed binding | Run log contains the exact reason and tmux shows a bounded message with its path; zero editor mutation | The caller is told the verifier is armed but a later failure disappears silently |
| Positional steers are retired | Invoke with the old `'<steer>'` syntax | Usage error before workspace resolution or mutation | Unsafe callers can silently retain the old protocol |
| Caller-selected continuation is retired | Invoke with `--continuation '<prompt>'` and with an unknown option | Usage error before workspace resolution or mutation | Callers can still steer or lengthen the wake |
| Concurrent helper runs are excluded | Hold a live session lock and invoke a second helper; separately expose dead `foreground`, `watcher-launching`, `watcher-owned`, malformed, and conflicting run-file states | Only well-formed dead `foreground` with no launch evidence is reclaimed; every live, transferred, or ambiguous state blocks before mutation; each owner token releases only its own lock | Two queued compacts or unsafe stale-lock deletion are possible |
| Post-Enter watcher death retains exclusion | Terminate the watcher after `ARMED` and separately immediately after Enter | A controlled termination retains ownership through start handling; an untrapped death strands the lock; a second helper never mutates the editor | Watcher cleanup can release a live queued compact |
| Restored draft is re-stashed | Restore a unique draft after the brief and before helper preparation | Draft is absent before command typing and returns unchanged after continuation | Brief emission creates a draft-appending race |
| Exact compact remains preferred | Render the fixed command exactly | One paste, no timed wait, one Enter | The safer normal path was lost |
| Timed fallback is bounded | Begin with a truly empty editor and no hidden draft, recheck current width, prove empty, paste once, and keep capture unreadable for 25 test-scaled seconds | One width-safe paste, one wait, one Enter, no recovery typing | Renderer corruption still disables automation or a deferred resize can wrap an ambiguously submitted command |
| Timed fallback rejects draft-bearing runs | Begin with visible and hidden unique drafts, prepare to empty, then keep the post-paste capture unreadable through the deadline | Zero Enter; exact rendering remains required | An asynchronously restored private draft can be submitted |
| Timed fallback rejects known mismatch | After proven empty, render a prefix, suffix, altered byte, restored draft, or second row before deadline | Zero Enter; residual remains or only exact owned text is cleaned | Waiting can submit known wrong text |
| Activity cancels timed fallback | Record user or assistant activity during every wait boundary | No later capture-driven mutation or Enter | Helper can race a resumed turn |
| Successful foreground return does not lose ownership | Complete `HANDOFF`, then let the foreground return normally | Watcher-owned lock remains through authorization and lifecycle completion or timeout | Tool completion can strand or duplicate a deferred compact |
| Menu blocks timed fallback | Show concrete nearby menu chrome after paste | Zero Enter | Ambiguous paste can activate a menu choice |
| No brief marker is required in prose | Complete with exact event metadata and a checkpoint that omits `SELF_COMPACT_BRIEF` and any run marker | Watcher accepts and continues | Generated prose still controls identity |
| Exact completion identity | Produce success with this run's token, then variants with another token, untagged or different instructions, failure, missing number, stale count, or missing checkpoint | Only the exact token-bearing complete case continues | Unrelated or incomplete compaction can be claimed |
| First completion after start wins | Append a mismatched completion followed by a matching one | Watcher rejects the run and does not scan forward | A later compact can be mistaken for the submitted one |
| Continuation prevents duplicate compact | Land a checkpoint whose next step discusses compaction, then inject the fixed wake | User event contains exact fixed wake; no second compact starts | Generic continuation can restart compaction |
| Continuation stays strict | Make its render unreadable or mismatched | No continuation Enter and no timed fallback | Recoverable wake ambiguity can submit unknown text |
| Legacy safety stays bounded | Run existing locale, redraw, menu, multiline, resize, no-start, failure, and activity-race scenarios | Existing key/type maxima and fail-closed outcomes remain | Protocol refactor weakened the editor boundary |
| Helper is one-shot | Fail every compact and continuation outcome | No helper relaunch and no second compact paste | Retry loops can semantically degrade or duplicate compaction |

The deterministic suite must include named Hotel and Sierra regression cases,
not only generic helper tests:

- `hotel-long-brief-narrow-pane`
- `hotel-checkpoint-without-marker`
- `sierra-restored-draft-before-control`
- `sierra-brief-facts-retained`
- `sierra-continuation-forbids-recompact`
- `concurrent-helper-session-lock`
- `timed-fallback-rejects-stashed-draft`

The shell-level cases prove protocol mechanics. The retained-facts and
no-recompact claims require the live scenarios below because generated
checkpoint content and agent interpretation depend on the real model.

No pre-implementation guard is required. The existing functional shell harness
can make every invalid transition fail, and a structural text guard would add
no distinct evidence.

## Live acceptance contract

Run the real installed candidate in tmux using a disposable Sierra-class
session and a unique draft.

### Scenario A: long brief, restored draft, and event identity

1. Create enough tool output to make compaction meaningful.
2. Place a unique draft in the editor and stash it.
3. Emit a long `SELF_COMPACT_BRIEF` containing:
   - the active objective;
   - three new unique identifiers;
   - explicit discard instructions;
   - `After compaction: report the three identifiers and do not compact again`.
4. Invoke the helper with no positional steer.
5. Observe the foreground report watcher readiness and return before the brief
   is necessarily readable from `events.jsonl`.
6. Observe the detached watcher bind the persisted brief to the
   foreground-recorded `toolCallId`, positive handoff, exact helper request,
   matching completion, and the observed quiescent terminal shape, then submit
   the fixed short token-bearing control command.
7. Observe one successful
   compact event with that exact token in custom instructions, advanced
   checkpoint number, and existing checkpoint file.
8. Observe the fixed continuation as the next user message.
9. Observe the resumed agent report all three identifiers without invoking
   another compact.
10. Observe the original draft restored unchanged and no watcher process or run
   marker file remaining.

PASS requires every checkpoint. A missing identifier, altered draft, second
compact, stranded watcher, marker-prose dependency, or manual editor repair is
FAIL.

### Scenario B: timed ambiguous-render fallback

Use the real TUI only if a known non-destructive way can make tmux capture
unreadable while preserving a visible client. If real corruption cannot be
summoned reliably, execute the timed fallback in the deterministic tmux harness
and record Scenario A as the real-model acceptance. Do not manufacture visual
corruption by changing the implementation or weakening the proof candidate.

The fallback PASS signal is one proven-empty transition, one paste, a
20-30 second wait, one Enter, a matching compact event, and no submitted draft.

## Migration

This is an intentional breaking change to an internal personal helper.

1. Update `self-compact`, `handoff`, and `unattended-run` instructions in the
   same release.
2. Change helper usage to:

   ```sh
   "/absolute/path/to/submit-compact.sh"
   ```

3. Set the invoking Bash tool's `initial_wait` to at least 120 seconds.
4. Move all steer and continuation meaning into the immediately preceding
   `SELF_COMPACT_BRIEF`.
5. Use the exact double-quoted canonical absolute helper path. Tilde,
   `$HOME`, arguments, assignments, and shell composition are unsupported and
   fail closed.
6. Keep the old positional syntax and `--continuation` as hard errors with
   migration guidance for one release. Do not interpret or ignore supplied
   text.
7. Publish and install the new plugin version only after deterministic and live
   acceptance pass.

No session data migration is required. Existing checkpoints, schedules, and
session event logs remain readable.

## Rollback

Rollback restores v0.100's exact-render-only submission behavior but does not
restore semantic shortening as an approved practice:

1. Disable the timed fallback so unreadable post-paste rendering exits without
   Enter.
2. Retain immediate empty-editor proof, fixed short commands, current-turn
   brief verification, detached structural invocation binding, session
   locking, token-bearing event identity, and explicit continuation.
3. If the split protocol itself is implicated, restore the v0.100 scripts and
   plugin manifests from Git, update the installed plugin, and require manual
   `/compact` for briefs that exceed one row.

The critical boundary is proven fail-closed when deliberate missing-brief,
nonempty, mismatched, multiline, menu, activity, lock-contention,
lock-handoff, draft-bearing fallback, failed-event, and missing-checkpoint cases
all produce zero unauthorized Enter presses and no continuation. Rollback is
complete when the exact normal path and full live lifecycle pass with the timed
fallback disabled.

## Definition of Done: Self-Compact Brief Protocol

- The reviewed design's protocol, invariants, deterministic checks, migration,
  rollback, and live acceptance are implemented.
- `submit-compact.sh` accepts zero arguments, including no steer or
  `--continuation`, transfers ownership without editor mutation, and returns.
- The detached watcher requires a structurally complete current-turn
  `SELF_COMPACT_BRIEF` from assistant content in the bound assistant turn,
  foreground-recorded `toolCallId`, positive owner-token handoff, exact helper
  request, matching tool start/completion, and one supported quiescent terminal
  shape before it proves immediate editor emptiness and submits the fixed short
  token-bearing control command.
- Every documented caller invokes the helper with a Bash `initial_wait` of at
  least 120 seconds and the exact double-quoted canonical absolute path.
- One session-scoped owner-token lock excludes concurrent helper runs and is
  released safely by foreground and watcher terminal paths; positive handoff
  is required, and post-`ARMED` termination never makes a second compact
  eligible.
- The exact path remains preferred; the compact-only timed fallback satisfies
  every gate and numeric bound in this document and is unavailable when any
  draft was observed or stashed.
- `resume-after-compact.sh` proves the first matching successful event and
  checkpoint number without grepping checkpoint prose.
- The fixed continuation states that compaction is complete, forbids another
  compact, and remains strict-exact only.
- `self-compact`, `handoff`, and `unattended-run` all use the new protocol and
  contain no old positional-steer examples.
- The targeted deterministic suite passes, including all named Hotel and Sierra
  regressions and retained v0.100 safety scenarios.
- The complete live Scenario A passes on the reviewed tree; Scenario B is
  either proven live or explicitly covered by the deterministic harness under
  its stated exception.
- Dual review has no verified in-scope must-fix finding.
- The final reviewed tree passes its targeted tests and final live lifecycle.
- Plugin manifests carry the new version, the personal plugin is installed
  from the landed commit, the worktree is clean, and no watcher remains.
