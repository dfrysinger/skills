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
benefits from separate context. Push to remote when each phase is complete,
passes its live acceptance flow, and clears review. Decide reversible questions
without waiting for user input. Freely use real model tokens within reason and
raise or drive the Copilot CLI sessions needed for live validation. Stay on this
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
- **Published baseline:** self-compact v0.99.0.
- **Implementation state:** not started.
- **Next action:** create the dedicated worktree from the committed plan, then
  implement the shared input-state helper and deterministic check contract.
- **Non-goals:** no Copilot CLI changes, general terminal parser, unrelated
  skill fallback, or relaxation of exact-command verification before Enter.
