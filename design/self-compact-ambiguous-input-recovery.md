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
- Do not change checkpoint grep semantics, session resolution, compaction
  completion checks, run filenames/logs, or the post-compaction event protocol.
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
- Ctrl-U clears from the cursor to the start of Copilot's current logical line.
  It does not clear prior lines in a multiline draft.
- Esc does not terminate a running tool or change the selected autopilot mode.
  It does stop further assistant work after that tool completes, which is
  compatible with self-compact's final-action contract.

No separate input-state helper exists in this repository. The current parser is
duplicated in the submitter and watcher, so this change should extract one
shared shell helper rather than add a third interpretation.

## Data flow

### 1. Preflight one-row commands

Before resolving the workspace, creating run files, starting the detached
watcher, pressing Ctrl-S, or typing into the editor, the foreground submitter
builds both complete commands and reads the real tmux pane width. The marked
command is:

```text
/compact <steer> Keep SCM:<8-hex-epoch>-<5-hex-pid>
```

The marker remains unique and directly greppable in the checkpoint while
shortening the fixed instruction. Both this complete marked command and the
continuation must contain printable ASCII only and be no longer than
`pane_width - 4`. The four-column margin reserves the prompt/editor chrome and
additional conservative edge room. Failure prints a foreground instruction to
shorten the steer or continuation, or reference a shorter durable artifact.
It leaves no watcher, run file, Ctrl-S, or typed text.

At 68 columns the safe row limit is 64. The fixed marked-command syntax uses 33
columns, so the exact maximum steer is 31 printable ASCII columns.

The watcher receives only commands that passed this preflight. Immediately
before post-compact editor mutation, it rechecks the continuation against the
current pane width so a later resize also fails closed.

### 2. Establish a parser-safe locale

The shared helper initializes before any input parsing or normalization. If
`SELF_COMPACT_LOCALE` is set, it tries that locale first, then the small
portable fallback order `C.UTF-8`, `en_US.UTF-8`, and `UTF-8`. A candidate is
accepted only when `locale charmap` succeeds under that requested locale and
reports UTF-8, and a real awk check can parse the Copilot prompt prefix, remove
it from `❯ proceed`, and recognize a realistic multi-glyph Unicode divider.
The multi-glyph run rejects C/POSIX byte-regex behavior; the charmap check
rejects missing names that silently fall back. `locale -a` or one divider glyph
is not proof that the requested locale is active or that awk behaves correctly.

The accepted candidate is exported as both `LC_ALL` and `LANG`. The submitter
also prefixes the detached watcher command with that verified locale, and the
watcher verifies it again during its own helper initialization. If no candidate
passes, input state remains `unknown`: the foreground submitter exits with a
clear error, while the detached watcher writes the internal failure only to its
per-run log. Neither path sends an editor key or Enter.

### 3. Refresh, then capture a stable state

Before sending an editor key:

1. Ask tmux to refresh every client attached to the target session.
2. Capture the input state.
3. If it remains unreadable, record the exact window geometry and the effective
   and configured `window-size` state, resize the target window one column
   narrower, then restore both geometry and option inheritance.
4. Capture again after the application handles both size changes.

The restoration runs from a shell trap as well as the normal path. The pulse is
skipped when the original width cannot be reduced safely or the window is
linked into another session. Scrolling and menu opening are not redraw
mechanisms because they change input focus.

The shared helper captures the prompt area and nearby footer. A state contains:

- the captured prompt rows in order, with only Copilot prompt syntax and
  captured terminal right-padding removed; row boundaries remain structural;
- whether the footer visibly reports `stashed`;
- cursor position;
- whether concrete menu chrome is visible in the four lines immediately after
  the editor divider; and
- whether the same values remained stable across three captures.

An unreadable prompt, missing divider, or changing state is `unknown`, not
`empty`. State-transition classification uses only stable empty versus nonempty
rows. An explicit multiline input remains nonempty even when one of its rows is
blank.

Exact helper ownership requires exactly one captured prompt row. After removing
only prompt syntax and captured right-padding, that row must be byte-for-byte
equal to the expected printable-ASCII command. Any second row, including a
blank row or a command-shaped logical newline at a space or in the middle of a
token, is non-exact. There is no row-boundary reconstruction because tmux
cannot reliably distinguish Copilot-drawn visual continuation rows from real
logical newlines.

Menu detection never scans transcript output. It accepts visible-menu state
only when the small post-divider region contains all three concrete Copilot
signals: `↑/↓` navigation, `Enter` plus `select`, and `Esc` plus
`close`/`cancel`/`dismiss`. Generic prose such as `press esc to cancel` or
`select an option` leaves menu state zero/unknown.

Literal typing is followed by bounded read-only render polling rather than one
immediate stable-state decision. For up to
`SELF_COMPACT_RENDER_WAIT_SECONDS` (5 seconds by default), the helper repeats
stable captures and returns as soon as the one-row exact gate sees the command.
`SELF_COMPACT_RENDER_POLL_SECONDS` controls the testable polling interval. The
activity callback runs before every capture and sleep boundary. No Ctrl-S,
Ctrl-U, Esc, resize pulse, or other editor action occurs during this window.
Recovery begins only after the window expires without an exact match.

### 4. Classify a Ctrl-S transition

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

### 5. Recover from an inconclusive state

When the transition remains inconclusive after the redraw captures, or a
normally typed helper command no longer compares exactly:

1. Show a one-line tmux notice that self-compact will clear the input in 10
   seconds. This notice is allowed to use tmux's short display surface; watcher
   crashes and unexpected internal failures remain log-only.
2. Wait 10 seconds so the user can manually stash, submit, or copy the draft.
3. Re-read session events. If the user submitted text or a new assistant turn
   started during the grace period, cancel this compaction attempt without
   clearing or typing.
4. Send Ctrl-U once and capture another stable state. Ctrl-U is line-local in
   Copilot's multiline editor.
5. Continue as cleared only if the complete logical input is clearly empty. A
   readable nonempty prior line is residual text, not a successful clear.
6. Type the intended command once. Poll stable captures for the bounded render
   window. If its captured rows match the complete expected command under the
   one-row exact rule, Esc is not needed.
7. If the visible input does not match that exact expected command, a concrete
   menu is visible, or the input state is unreadable, apply the bounded Ctrl-U
   and first Esc recovery and capture again.
8. Send one additional Esc only when the concrete nearby multi-signal menu
   chrome is still visible. Generic or unproven menu state never authorizes the
   second Esc; the later exact gate fails closed if the first Esc did not repair
   the editor.
9. Send Ctrl-U, type the intended command for the second and final time, and
   apply the same bounded read-only render polling.
10. If the exact marked command still cannot be observed, clear the
    helper-authored text on a best-effort basis, show a one-line failure notice,
    cancel the attempt, and do not press Enter.

This is an explicit destructive fallback for draft preservation. Command
submission remains fail-closed unless the exact marked command becomes visible.
Readable multiline residual text cannot compare equal to a single-line helper
command and is never submitted. No cursor movement, Backspace, End, paste, or
other speculative editor key is part of recovery.
The fallback must not become the default path when a clear Ctrl-S transition
exists.

### 6. Submit the compact command

Type the exact marked `/compact` command.

- When exactly one captured prompt row is stable and byte-exact, press Enter
  normally.
- Immediately before Enter, use the same bounded render wait for a fresh stable
  exact capture, then recheck activity once more. A stale earlier exact capture
  never authorizes submission.
- Captured terminal padding is display-only. Any additional row or newline,
  and any missing, extra, doubled, or changed internal byte, rejects. Helper
  commands are single-line and do not intentionally end in whitespace.
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
authoritative outcomes. The deadline loop performs one final event read at
expiry so a start from the final interval is accepted. A failed or absent
compact never produces a success-shaped continuation.

### 7. Resume after compaction

If session events already show post-compact user or assistant activity, do
nothing. Otherwise use the same Ctrl-S and Ctrl-U recovery policy before
submitting `proceed`. Recheck events before every Esc, before typing, and
before every render-poll capture or sleep, and immediately before Enter. If
activity appeared, remove only helper-authored text and exit. Esc is forbidden
after post-compact activity exists.

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
- **Ctrl-U leaves a prior logical line:** the residual remains readable and
  nonempty because Ctrl-U is line-local. The bounded Ctrl-U/Esc sequence may
  finish, but exact comparison fails, the helper shows its failure notice, and
  Enter is not sent.
- **A command appears across multiple captured rows:** tmux cannot prove whether
  the boundary is visual or logical, so every exact ownership, Enter, and
  cleanup gate rejects it. Supported commands are preflighted to fit one row.
- **The steer or continuation cannot fit safely:** foreground preflight exits
  before watcher launch, files, Ctrl-S, or typing. A later pane shrink causes
  the watcher to skip continuation before editor mutation.
- **Copilot delays rendering freshly typed text:** stable empty frames are not
  treated as the final typed state until the bounded read-only render window
  expires. Exact rendering wins immediately; a delayed wrong rendering still
  reaches the existing grace and bounded fail-closed recovery.
- **Enter does not start compaction:** a short start deadline clears the buffer
  only when it still exactly equals the helper-authored marked command, cancels
  the watcher, and visibly reports failure rather than waiting for the full
  checkpoint timeout. A different or unreadable buffer is left untouched.
- **Nothing is available to compact:** the watcher exits on the failed
  compaction event without polling for the full timeout.
- **Detached watcher crashes or hits an unexpected internal error:** the failure
  remains in the per-run log and does not become a tmux overlay. Planned
  recovery warnings use the one-line tmux notice surface.
- **Detached tmux shell has no locale:** macOS awk can misparse the Unicode
  divider under the resulting C locale and report visible `proceed` as empty.
  Initialization requires an active UTF-8 charmap plus the multi-glyph parser
  probe before capture; if none works, the helper leaves state unknown and
  exits without Enter.
- **Transcript prose mentions menu controls:** menu detection never scans it.
  Only concrete multi-signal chrome next to the editor can authorize a second
  Esc.

## Hard invariants

1. A readable nonempty draft is stashed rather than cleared.
2. Unreadable rendering is never labeled empty.
3. Ctrl-U or Esc applied to text the helper did not author is used only after
   one inconclusive Ctrl-S transition or non-exact command verification and a
   10-second grace period. Cleanup of a stably exact helper-authored command is
   allowed without that delay.
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
11. A readable nonempty multiline residual is never classified as cleared or
    submitted.
12. After literal typing, render polling sends no editor key and checks activity
    before every capture and sleep boundary.
13. Input parsing runs only after the requested locale reports a UTF-8 charmap
    and awk passes the prompt plus multi-glyph divider probe; locale failure
    leaves state unknown and authorizes no Enter.
14. Every exact ownership, Enter, and cleanup gate requires exactly one captured
    prompt row; no row-boundary reconstruction is permitted.
15. Both commands pass printable-ASCII and pane-width preflight before watcher
    launch, file creation, Ctrl-S, or typing.
16. A second Esc requires concrete nearby `↑/↓`, `Enter select`, and
    `Esc close/cancel/dismiss` menu chrome.

## Acceptance criteria and check contract

| Criterion | Setup and action | Pass signal | Failure proves |
| --- | --- | --- | --- |
| Empty input remains safe | Run the state transition with no visible or hidden draft | No text is introduced; compact is submitted | Ctrl-S or recovery mutated an empty editor |
| Visible draft is preserved | Put unique text in input, run compact and continuation | Text disappears before compact and returns unchanged after continuation | Draft storage or restoration is broken |
| Hidden draft is preserved | Pre-stash unique text, then run compact | Helper restores and re-stashes it before command submission; text returns later | Toggle direction was inferred incorrectly |
| Resize refresh is nondestructive | Start with unreadable rendering and known geometry and window-size state, then pulse width | Geometry and inherited/configured sizing state are restored exactly; linked windows are skipped; no input, mode, or autopilot state changes | Refresh can disturb the session |
| Corrupt rendering recovers when key clearing repairs the editor | Feed an unstable or unreadable prompt state, then make Ctrl-U or Esc restore readable input | Visible tmux notice, 10-second grace, exact marked command, one Enter | Recoverable ambiguity still disables automation or loops |
| Persistently unreadable rendering does not transmit unknown text | Keep the prompt unreadable through the bounded recovery | Helper-authored text is cleared where possible, no Enter occurs, and a visible failure notice appears | Residual draft text can be submitted as a user message |
| Recovery is numerically bounded | Exercise every ambiguous branch with a shortened test delay | At most one grace wait, one Ctrl-S transition, four Ctrl-U presses including final cleanup, two Esc presses, two command typings, and zero unverified Enter presses | Recovery can hang, toggle, clear, or type repeatedly |
| Unknown text is not appended intentionally | Begin fallback with visible text and make parsing unreadable | Ctrl-U and any required Esc recovery occur before the marked command is typed | The command can be deliberately concatenated with a draft |
| One-row ownership is exact | Capture one prompt row containing the complete expected compact or continuation | Only byte-for-byte equality after prompt syntax and captured right-padding is accepted | Exact ownership can normalize user text |
| Every second row is non-exact | Capture command-shaped second rows at an expected-space boundary, a mid-token boundary, and as a blank row | No exact match, cleanup, or Enter | A logical newline can be reconstructed into the helper command |
| Captured right-padding is display-only | Vary transient spaces at the single captured row end across otherwise identical stable captures | The row remains stable and the expected command still matches | A redraw can spuriously reject an exact helper command |
| Exact submissions retain strict verification | Compare commands with altered internal whitespace or residual prefixes and suffixes, including explicit multiline residual | Only the exact expected command matches and normal Enter confirmation remains active | Exact ownership accepts altered user text |
| One-row cleanup uses the same gate | Leave a helper-shaped command across two captured rows, then run activity or no-start cleanup | No Ctrl-U because ownership is non-exact | Cleanup can delete a logical multiline buffer |
| Width preflight is mutation-free | Use a 68-column pane with a 32-column steer, then with a 65-column continuation | Foreground error before run-shell, run files, Ctrl-S, typing, or Enter | Unsupported wrapping can reach the watcher or editor |
| Maximum 68-column steer succeeds | Use the 31-column maximum with the concise fixed command format | One compact Enter, one continuation Enter, and a retained `SCM:` checkpoint marker | The safe format leaves no practical steer room |
| Non-ASCII input is rejected | Put a non-ASCII byte in the steer or continuation | Foreground failure before watcher or editor mutation | Byte length can diverge from display width |
| Delayed exact rendering does not trigger recovery | Keep the fake renderer empty for several captures after compact or continuation typing, then show the exact command | One typing, zero Esc, no grace warning, and one Enter for the delayed command | Renderer latency can be mistaken for a command mismatch |
| Delayed wrong rendering remains fail-closed | Keep the fake renderer empty for several captures, then show a non-exact command through the render deadline | Grace and bounded recovery run; typing and key maxima hold; no Enter occurs | Render polling can wait forever or weaken exact ownership |
| Detached locale is parser-safe | Invoke the real helper under `env -i HOME=... PATH=/usr/bin:/bin` with visible `❯ proceed` and a full Unicode divider | Initialization exports one verified UTF-8 locale and capture/matching yields hex `70726f63656564` | The watcher can classify visible continuation text as empty |
| Non-UTF-8 and missing locales are rejected | Probe real `C`, `POSIX`, and a bogus locale, then request `C` through normal initialization | All three direct probes fail and initialization advances to a real UTF-8 fallback | Byte-regex behavior or silent locale fallback can be trusted |
| Locale failure is fail-closed | Force every locale probe to fail in both helper callers | Input state remains unknown, the foreground reports the locale error, the watcher reports it only on stderr/log, and no Enter or tmux notice occurs | Initialization failure can continue into editor mutation or create a crash overlay |
| Multiline Ctrl-U residual fails closed | Put the cursor at the end of line 2, make Ctrl-U leave line 1, and run bounded recovery | No Enter, visible failure notice, key/type bounds respected, and residual text is never queued | Line-local clearing can submit unknown prior lines |
| Missing compaction start fails promptly | Consume Enter without recording `session.compaction_start` | An exact remaining helper command is cleared, watcher exits within the short deadline, visible failure is shown | A stranded command can wait for the long checkpoint timeout |
| No-start expiry preserves a new draft | Begin a new unsubmitted draft during the 15-second start deadline | Buffer mismatch prevents Ctrl-U; the draft remains unchanged while the watcher cancels | Timeout cleanup can delete new user text |
| Queued compact is not timed from Enter | Delay `session.compaction_start` until after a delayed `assistant.turn_end`, including the final deadline interval | Watcher does not expire before turn end and its final expiry read accepts a start within 15 seconds afterward | A valid queued compact can be cancelled prematurely |
| Post-compact activity wins | Record a user message or assistant turn after compaction | No `proceed` is injected | Watcher can steer an already resumed turn |
| Grace-period submission wins | Record a user message during the 10-second wait | Recovery cancels without Ctrl-U, Esc, or command typing | The helper can clear or type into a user-started turn |
| Esc is conditional | Make Ctrl-U produce an exact rendered command with no visible menu | No Esc key is sent | Esc can suppress work when it is unnecessary |
| Transcript menu prose is ignored | Put `press esc to cancel` and `select an option` in ordinary transcript output with no menu | Normal stash/exact path and zero Esc | Generic transcript text can pin menu state |
| Nearby concrete menu controls Esc | Render adjacent `↑/↓`, `Enter select`, and `Esc close` chrome that closes after the first or second Esc | Exactly one or two Esc presses respectively, within existing bounds | Menu recovery depends on generic phrases or scans the transcript |
| Post-compact Esc race is closed | Start activity during continuation recovery | No Esc or Enter occurs after the activity event; the turn reaches its normal end | Watcher can interrupt a resumed turn |
| Failed compaction stops promptly | Record `session.compaction_complete` with `success:false` | Watcher exits immediately | Failure can wait 30 minutes or inject continuation |
| Esc does not terminate the current tool | Run a bounded real shell command and send one Esc | Shell completes; autopilot selection remains | Fallback can terminate the helper itself |

Deterministic shell tests cover all state transitions, retry counts, key order,
visible-notice delivery, geometry restoration, exact one-row matching,
second-row rejection at space and mid-token boundaries, mutation-free width
preflight, concise-marker lifecycle, delayed exact and wrong rendering,
one-literal/one-Enter submission, transcript-safe concrete menu detection,
locale-scrubbed helper and watcher startup, real C/POSIX/bogus rejection,
fallback advancement, forced locale failure, event races, and event outcomes.
Live Sierra tests already cover
refresh and one-column resize restoration, Ctrl-S behavior, transient captured
right-padding after resize, Ctrl-U with single-line and multiline drafts, Esc
during a running tool, and standalone visible and hidden draft restoration.
The first complete live compact-to-continuation lifecycle exposed a long command
rendered as independent rows. The subsequent reconstruction experiment proved
useful for diagnosis but is not final acceptance because a logical newline can
produce the same capture. The supported final path instead uses the concise
`SCM:` command, preflights one-row fit, and rejects every second row. A later
live run of the reconstruction candidate advanced `summary_count` and created
its marker checkpoint, then typed visible `proceed`; later diagnosis under a real
`tmux run-shell -b` environment showed that the detached shell had no
`LANG`/`LC_ALL`. Under that macOS C locale, the awk parser returned an empty
readable input; the foreground submitter worked because it inherited the
interactive UTF-8 locale. The lifecycle failed and did not restore the test
draft. A later locale-initializing lifecycle passed and is recorded as discovery
evidence in `design/self-compact-v0.100-live-proof.md`, but executable round-1
safety changes make that receipt stale for final acceptance. The final
one-row/concise-marker candidate still requires the design's live lifecycle
rerun before landing. The multiline live
acceptance is residual detection and fail-closed submission, not whole-buffer
clearing by one Ctrl-U. Rendering corruption is tested deterministically
because a real corrupt redraw cannot be requested reliably.

## Rollback

Restore the existing fail-closed policy: if Ctrl-S state, exact rendering, or
input clearing cannot be verified, cancel the watcher and do not submit
`/compact` or `proceed`. This rollback is confined to the shared input helper
and its two callers; checkpoint and event verification remain unchanged.

The rollback is proven when every ambiguous-state test exits before command
submission and the existing normal-path tests still pass.

## Definition of Done: Ambiguous Input Recovery

- One shared input-state helper owns refresh, geometry restoration, capture,
  stabilization, verified UTF-8 initialization, Ctrl-S transition
  classification, grace timing, and forced clearing.
- Both compact submission and post-compact continuation use that helper.
- The normal readable path remains strict.
- The ambiguous path stays within the numeric key and typing bounds in the
  check contract and presses Enter only after exact command verification.
- The documented draft-loss tradeoff appears in the skill.
- Deterministic tests and the bounded live Sierra scenarios pass.
- The plugin is versioned, published, installed, and leaves no watcher running.
