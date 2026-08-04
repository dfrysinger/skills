# Self-Compact Ambiguous Input Recovery

## Objective

Keep self-compaction automatic when Copilot's rendered input area cannot be
read reliably, while preserving drafts when the state transition is clear and
accepting bounded draft loss after a visible 10-second recovery period when it
is not.

## Non-goals

- Do not build a general terminal-screen parsing framework.
- Do not add a native Copilot input API or change Copilot CLI itself.
- Do not guarantee preservation of an unsubmitted draft when the TUI remains
  unreadable after the Ctrl-S transition and bounded redraw captures.
- Do not change checkpoint markers, session resolution, compaction completion
  checks, or the post-compaction event protocol.
- Do not make Esc-based recovery available to unrelated skills.

## Lane

**Critical.** The fallback can delete unsubmitted user text. The design must
bound that loss, prevent unknown text from being intentionally submitted as the
compact command, and retain a direct rollback to the existing fail-closed
behavior.

## Existing parts this builds on

The change reuses the existing self-compact helper and watcher:

- `submit-compact.sh` resolves the active Copilot session, creates the unique
  marker, starts the detached watcher, and sends keys to the owning tmux pane.
- `resume-after-compact.sh` proves the marked compact completed from
  `summary_count`, the checkpoint marker, and session events, then decides
  whether `proceed` is needed.
- Ctrl-S toggles Copilot's draft stash. A visible draft becomes hidden and
  returns after the next turn. An empty input with no hidden stash is unchanged.
- Ctrl-U clears visible editor text.
- Esc does not terminate a running tool or change the selected autopilot mode.
  It does stop further assistant work after that tool completes, which is
  compatible with self-compact's final-action contract.

No separate input-state helper exists in this repository. The current parser is
duplicated in the submitter and watcher, so this change should extract one
shared shell helper rather than add a third interpretation.

## Data flow

### 1. Refresh, then capture a stable state

Before sending an editor key:

1. Ask tmux to refresh every client attached to the target session.
2. Capture the input state.
3. If it remains unreadable, record the exact window geometry, resize the
   target window one column narrower, then restore the original geometry.
4. Capture again after the application handles both size changes.

The geometry restoration runs from a shell trap as well as the normal path.
The pulse is skipped when the original width cannot be reduced safely.
Scrolling and menu opening are not redraw mechanisms because they change input
focus. The resize pulse is scoped to the target tmux session and does not touch
other sessions.

The shared helper captures only the prompt area and nearby footer, not the whole
pane. A state contains:

- normalized visible input text when the prompt bounds are readable;
- whether the footer visibly reports `stashed`;
- cursor position;
- whether the same values remained stable across three captures.

An unreadable prompt, missing divider, or changing state is `unknown`, not
`empty`.

### 2. Classify a Ctrl-S transition

Capture state A, press Ctrl-S once, then capture state B.

- Text disappears and `stashed` appears: the visible draft was stored.
- Text appears and `stashed` disappears: a hidden draft was restored. Press
  Ctrl-S again and require the reverse transition.
- Both states are stably empty, the cursor remains in the empty position, and
  no stash indicator changes: there was no draft or hidden stash.
- Any other result is inconclusive.

Do not repeat Ctrl-S blindly when the state is inconclusive. The first press may
already have stored the draft; an unobserved second press would restore it.
Instead, give redraws one chance by recapturing state B without sending another
key.

### 3. Recover from an inconclusive state

When the transition remains inconclusive after the redraw captures:

1. Show a one-line tmux notice that self-compact will clear the input in 10
   seconds. This notice is allowed to use tmux's short display surface; watcher
   crashes and unexpected internal failures remain log-only.
2. Wait 10 seconds so the user can manually stash, submit, or copy the draft.
3. Re-read session events. If the user submitted text or a new assistant turn
   started during the grace period, cancel this compaction attempt without
   clearing or typing.
4. Send Ctrl-U once and capture another stable state.
5. If the input is clearly empty, continue.
6. Type the intended command once. If it renders exactly, Esc is not needed.
7. If text remains, the command is not exact, a menu is visible, or the state
   is still unreadable, clear the helper's attempted command with Ctrl-U, send
   one Esc, and capture again.
8. If a menu is visibly still open, send one additional Esc and capture again.
9. Send Ctrl-U, type the intended command for the second and final time, and
   capture again.
10. If the exact marked command still cannot be observed, clear the
    helper-authored text on a best-effort basis, show a one-line failure notice,
    cancel the attempt, and do not press Enter.

This is an explicit destructive fallback for draft preservation. Command
submission remains fail-closed unless the exact marked command becomes visible.
The fallback must not become the default path when a clear Ctrl-S transition
exists.

### 4. Submit the compact command

Type the exact marked `/compact` command.

- When the rendered command is stable and exact, press Enter normally.
- Never press Enter on an unverified buffer. The accepted risk is loss of an
  unsubmitted draft, not transmission of that draft as an ordinary user
  message.

After Enter, the watcher first waits for the submitting `assistant.turn_end`.
From that boundary it requires a new `session.compaction_start` within 15
seconds. A start before turn end is also accepted. On expiry it clears only the
buffer that still exactly equals the helper-authored marked command. If the
buffer is different or unreadable, it sends no editor key. It then cancels
itself and shows a one-line failure notice. It then treats a failed
`session.compaction_complete`, and the marked successful checkpoint as the
authoritative outcomes. A failed or absent compact never produces a
success-shaped continuation.

### 5. Resume after compaction

If session events already show post-compact user or assistant activity, do
nothing. Otherwise use the same Ctrl-S and Ctrl-U recovery policy before
submitting `proceed`. Recheck events before every Esc, before typing, and
immediately before Enter. If activity appeared, remove only helper-authored
text and exit. Esc is forbidden after post-compact activity exists.

The restored user draft should return after the `proceed` turn. In the
inconclusive fallback, that draft may have been cleared and is not promised.

## Failure model

- **Stale borders, wrapped dividers, or a log overlay covering the editor:** the
  state becomes `unknown`; it is never interpreted as empty or nonempty. The
  recovery uses key semantics rather than trying to parse the overlay.
- **Footer redraw hides `stashed`:** the transition can still be classified by
  a repeatable full-to-empty input delta. If neither signal is reliable, the
  grace fallback runs.
- **Ctrl-S restores a hidden draft:** the reverse transition stores it again.
- **User types during the grace period without submitting:** forced clearing
  may delete that text. The notice and delay are the protection; preservation
  is not guaranteed.
- **User submits during the grace period:** the new session event cancels the
  compaction attempt so the helper does not clear or type into the new turn.
- **Esc suppresses remaining assistant work:** expected. Self-compact must be
  the final tool action and the watcher owns continuation.
- **Forced clearing fails to remove visible text:** Ctrl-U is the primary
  recovery. Esc is used only when the intended command does not render exactly
  or a menu is visible. If the exact command never becomes observable, Enter
  is not sent.
- **Enter does not start compaction:** a short start deadline clears the buffer
  only when it still exactly equals the helper-authored marked command, cancels
  the watcher, and visibly reports failure rather than waiting for the full
  checkpoint timeout. A different or unreadable buffer is left untouched.
- **Nothing is available to compact:** the watcher exits on the failed
  compaction event without polling for the full timeout.
- **Detached watcher crashes or hits an unexpected internal error:** the failure
  remains in the per-run log and does not become a tmux overlay. Planned
  recovery warnings use the one-line tmux notice surface.

## Hard invariants

1. A readable nonempty draft is stashed rather than cleared.
2. Unreadable rendering is never labeled empty.
3. Ctrl-U or Esc applied to text the helper did not author is used only after
   one inconclusive Ctrl-S transition and a 10-second grace period. Cleanup of
   the helper's own rendered command is allowed without that delay.
4. The helper never reports success until the marked compact is armed for
   event-based verification.
5. `proceed` is sent only after the exact marked compact completed and no
   post-compact activity already exists.
6. A failed compact cannot trigger `proceed`.
7. Detached process exit status, crashes, and internal errors are log-only.
   The planned 10-second clear warning, bounded recovery-abort warning, and
   bounded no-compaction-start failure are explicit one-line tmux notices.
8. The watcher is one-shot and cannot relaunch itself.
9. Esc is never sent after post-compact activity is recorded.
10. Enter is never sent unless the complete marked command is observed exactly.

## Acceptance criteria and check contract

| Criterion | Setup and action | Pass signal | Failure proves |
| --- | --- | --- | --- |
| Empty input remains safe | Run the state transition with no visible or hidden draft | No text is introduced; compact is submitted | Ctrl-S or recovery mutated an empty editor |
| Visible draft is preserved | Put unique text in input, run compact and continuation | Text disappears before compact and returns unchanged after continuation | Draft storage or restoration is broken |
| Hidden draft is preserved | Pre-stash unique text, then run compact | Helper restores and re-stashes it before command submission; text returns later | Toggle direction was inferred incorrectly |
| Resize refresh is nondestructive | Start with unreadable rendering and known geometry, then pulse width | Geometry is restored exactly; no input, mode, or autopilot state changes | Refresh can disturb the session |
| Corrupt rendering recovers when key clearing repairs the editor | Feed an unstable or unreadable prompt state, then make Ctrl-U or Esc restore readable input | Visible tmux notice, 10-second grace, exact marked command, one Enter | Recoverable ambiguity still disables automation or loops |
| Persistently unreadable rendering does not transmit unknown text | Keep the prompt unreadable through the bounded recovery | Helper-authored text is cleared where possible, no Enter occurs, and a visible failure notice appears | Residual draft text can be submitted as a user message |
| Recovery is numerically bounded | Exercise every ambiguous branch with a shortened test delay | At most one grace wait, one Ctrl-S transition, four Ctrl-U presses including final cleanup, two Esc presses, two command typings, and zero unverified Enter presses | Recovery can hang, toggle, clear, or type repeatedly |
| Unknown text is not appended intentionally | Begin fallback with visible text and make parsing unreadable | Ctrl-U and any required Esc recovery occur before the marked command is typed | The command can be deliberately concatenated with a draft |
| Exact submissions retain strict verification | Use readable rendering | Exact command comparison and normal Enter confirmation remain active | The fallback weakened the normal path |
| Missing compaction start fails promptly | Consume Enter without recording `session.compaction_start` | An exact remaining helper command is cleared, watcher exits within the short deadline, visible failure is shown | A stranded command can wait for the long checkpoint timeout |
| No-start expiry preserves a new draft | Begin a new unsubmitted draft during the 15-second start deadline | Buffer mismatch prevents Ctrl-U; the draft remains unchanged while the watcher cancels | Timeout cleanup can delete new user text |
| Queued compact is not timed from Enter | Delay `session.compaction_start` until after a delayed `assistant.turn_end` | Watcher does not expire before turn end and accepts a start within 15 seconds afterward | A valid queued compact can be cancelled prematurely |
| Post-compact activity wins | Record a user message or assistant turn after compaction | No `proceed` is injected | Watcher can steer an already resumed turn |
| Grace-period submission wins | Record a user message during the 10-second wait | Recovery cancels without Ctrl-U, Esc, or command typing | The helper can clear or type into a user-started turn |
| Esc is conditional | Make Ctrl-U produce an exact rendered command with no visible menu | No Esc key is sent | Esc can suppress work when it is unnecessary |
| Post-compact Esc race is closed | Start activity during continuation recovery | No Esc or Enter occurs after the activity event; the turn reaches its normal end | Watcher can interrupt a resumed turn |
| Failed compaction stops promptly | Record `session.compaction_complete` with `success:false` | Watcher exits immediately | Failure can wait 30 minutes or inject continuation |
| Esc does not terminate the current tool | Run a bounded real shell command and send one Esc | Shell completes; autopilot selection remains | Fallback can terminate the helper itself |

Deterministic shell tests cover all state transitions, retry counts, key order,
visible-notice delivery, geometry restoration, event races, and event outcomes.
Live Sierra tests cover refresh and one-column resize restoration, Ctrl-S
behavior, Ctrl-U with single-line and multiline drafts, Esc during a running
tool, visible and hidden draft restoration, and one complete
compact-to-continuation lifecycle. Rendering corruption is tested
deterministically because a real corrupt redraw cannot be requested reliably.

## Rollback

Restore the existing fail-closed policy: if Ctrl-S state, exact rendering, or
input clearing cannot be verified, cancel the watcher and do not submit
`/compact` or `proceed`. This rollback is confined to the shared input helper
and its two callers; checkpoint and event verification remain unchanged.

The rollback is proven when every ambiguous-state test exits before command
submission and the existing normal-path tests still pass.

## Definition of Done: Ambiguous Input Recovery

- One shared input-state helper owns refresh, geometry restoration, capture,
  stabilization, Ctrl-S transition classification, grace timing, and forced
  clearing.
- Both compact submission and post-compact continuation use that helper.
- The normal readable path remains strict.
- The ambiguous path stays within the numeric key and typing bounds in the
  check contract and presses Enter only after exact command verification.
- The documented draft-loss tradeoff appears in the skill.
- Deterministic tests and the bounded live Sierra scenarios pass.
- The plugin is versioned, published, installed, and leaves no watcher running.
