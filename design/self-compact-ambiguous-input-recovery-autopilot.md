# Self-Compact Ambiguous Input Recovery Run

## Objective

Achieve the Definition of Done in
`design/self-compact-ambiguous-input-recovery.md`, the "Definition of Done:
Ambiguous Input Recovery" section: self-compaction recovers from corrupted TUI
input rendering without submitting unknown user text. Keep working through the
plan; finish only once every item in that section is verifiably met.

## Charter

Keep building against the plan at
`design/self-compact-ambiguous-input-recovery.md` in the dedicated
`dfrysinger/self-compact-ambiguous-input-recovery` worktree. Follow the required
process skills below. Use rubber-duck to align on a path whenever progress gets
stuck. Keep this baton current so a compacted session can recover the exact
phase, candidate, and remaining checks. Use subagents when independent work
benefits from separate context. Do not commit or push during this implementation
run. Decide reversible questions without waiting for user input. Freely use real
model tokens within reason and raise or drive the Copilot CLI sessions needed
for live validation when the worktree-only restriction permits it. Stay on this
course until the objective's "Definition of Done: Ambiguous Input Recovery"
section is met.

### Required process skills

- **Governing:** `/dfrysinger-skills:development-loop` owns phase order, live
  proof, review, final validation, and completion. Invoke it after compaction
  when it is no longer active.
- **Execution:** `None`.
- **Context:** `/dfrysinger-skills:self-compact` owns compaction at governing
  workflow compaction points or when context becomes noisy. Persist the complete
  baton and invoke it as the final action. Do not compact because the reminder
  fired or while live proof is active.

## Current baton

- **Lane:** critical.
- **Plan:** `design/self-compact-ambiguous-input-recovery.md`.
- **Definition of Done:** "Definition of Done: Ambiguous Input Recovery".
- **Published version:** self-compact v0.100.0 on `main` at merge commit
  `d5b2c05`; the installed personal plugin is v0.100.0.
- **Live proof:** `design/self-compact-v0.100-live-proof.md` records the final
  one-row `SCM:6a71d3cc-03dca` compact, checkpoint, continuation, restored
  draft, and watcher teardown, plus the earlier hidden-draft, locale-scrubbed,
  geometry, Ctrl-U, and Esc observations. Copilot Ctrl-U is line-local;
  multiline residual remains nonempty and fails closed.
- **Implementation state:** the submitter now uses the concise fixed command
  `/compact <steer> Keep SCM:<8-hex-epoch>-<5-hex-pid>`. Before workspace
  resolution, run-file creation, watcher launch, Ctrl-S, or typing, it requires
  printable ASCII and preflights both the complete marked command and
  continuation against `pane_width - 4`; the watcher rechecks continuation
  width before post-compact mutation. At 68 columns the exact steer maximum is
  31. Capture preserves prompt rows structurally after removing only prompt
  syntax and right-padding. Exact ownership, Enter, and cleanup require exactly
  one captured prompt row byte-equal to the expected command; every second row
  or logical newline is non-exact and no boundary reconstruction remains.
  Every literal typing now gets a bounded read-only stable-capture window (5
  seconds live, configurable in tests), with activity checks before each
  capture and sleep.
  Normal compact, continuation, fallback typings, and final caller-side Enter
  rechecks share it. Recovery begins only after expiry. Helper initialization
  tries an explicit `SELF_COMPACT_LOCALE`, then a small UTF-8 fallback order,
  accepting only an active UTF-8 `locale charmap` plus a real awk prompt and
  multi-glyph divider parse. It exports `LC_ALL` and `LANG`, passes the verified
  locale into the detached watcher, and both callers fail closed if
  initialization fails. Menu detection examines only four lines adjacent to the
  editor and requires `↑/↓`, `Enter select`, and
  `Esc close/cancel/dismiss`; transcript prose cannot authorize Esc. Explicit
  multiline residual remains nonempty. Deterministic coverage includes exact
  compact/continuation, second-row rejection at expected-space and mid-token
  boundaries, mutation-free long-input failure, non-ASCII failure, concise
  marker lifecycle, delayed rendering, locale-scrubbed watcher startup, real
  C/POSIX/bogus rejection with fallback advancement, concrete first/second Esc
  menus, transcript false-positive rejection, and the existing key/type/event
  bounds.
- **Validation:** `bash -n`, the full targeted test, real C/POSIX/bogus locale
  rejection with fallback to `C.UTF-8`, plugin manifest consistency,
  `git diff --check`, and test scratch/watcher residue checks pass on the
  round-1 candidate.
- **Review:** both round-2 reviewer families closed all three round-1 material
  findings with no remaining findings.
- **Completion:** deterministic validation passed twice, the final Sierra live
  lifecycle passed, main was published, and the personal plugin was updated.
- **Next action:** none. Stop the unattended schedule.
- **Non-goals:** no Copilot CLI changes, general terminal parser, unrelated
  skill fallback, or relaxation of exact-command verification before Enter.
