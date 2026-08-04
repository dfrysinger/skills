# Self-Compact Brief Protocol Autopilot Charter

## Objective

Implement, prove, review, publish, and install the critical protocol defined in
`design/self-compact-brief-protocol.md`.

## Authoritative plan

- Worktree: `/Users/dfrysinger/code/skills`
- Branch: `dfrysinger/self-compact-brief-protocol`
- Plan: `design/self-compact-brief-protocol.md`
- Definition of Done:
  `Definition of Done: Self-Compact Brief Protocol`
- Push policy: local commits are allowed; do not push unless the user asks in
  a later turn.

## Required process skills

- **Governing:** `/dfrysinger-skills:development-loop`
  - Owns implementation order, live-proof gating, review, final validation,
    landing, and completion.
- **Execution:** `/dfrysinger-skills:dual-review`
  - Reviews the complete implementation only after the current-tree live proof
    passes.
- **Execution:** `/dfrysinger-skills:behavior-validation`
  - Use only if the final implementation's critical runtime surface requires
    evidence beyond the explicit Sierra live contract.
- **Context:** `/dfrysinger-skills:self-compact`
  - Owns later phase-boundary compaction after this charter reminder is live.

Do not re-invoke `unattended-run`; this file and its one schedule are already
the active unattended-run state.

## Autonomy mandate

Continue autonomously through the complete Definition of Done. Resolve
implementation details from the reviewed design and existing repository
patterns. Do not ask for routine decisions. Stop only for a genuine credential,
permission, destructive-action, or user-only visual-confirmation blocker.

## Current phase

The first implementation review found four material defects: the current-turn
gate scanned the complete event history, malformed foreground-lock metadata
could be reclaimed, the ambiguous-render wait accepted values outside its
20-30 second safety bound, and two caller templates violated the parser's
same-line requirement. The bounded repair set and finding-specific regression
coverage are in progress.

## Phase order

1. Implement protocol scripts, callers, documentation, and manifest version.
2. Run targeted deterministic validation needed for a runnable candidate.
3. Write the live-proof receipt and pass the complete real Sierra scenario on
   that exact candidate.
4. Run remaining proportional deterministic validation.
5. Run implementation dual review and close material findings.
6. Rerun the final live lifecycle on the reviewed tree.
7. Commit locally, install the plugin from that commit, confirm clean state and
   no watcher, stop the schedule, and finish.

Do not start implementation review before the live-proof receipt is PASS. Do
not shorten compaction meaning, restore caller-selected continuation, weaken
draft isolation, or treat deterministic shell tests as the real-model proof.

## Current baton

- Design complete and reviewed.
- Branch created from `6fe47d4`.
- Candidate version is v0.101.0; the installed plugin remains v0.100.0.
- SQL todos `brief-protocol-code` through `brief-protocol-land` track the
  remaining phases.
- The pre-review deterministic suite and Tango lifecycle passed.
- Round 1 implementation review produced four verified material findings.
- The next action is to validate the bounded fixes, run round 2 closure, and
  rerun the final reviewed Tango lifecycle.
