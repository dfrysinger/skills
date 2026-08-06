# Self-Compact Brief Protocol Autopilot Charter

## Objective

Implement, prove, review, publish, and install the critical protocol defined in
`design/self-compact-brief-protocol.md`.

## Authoritative plan

- Worktree: `/Users/dfrysinger/code/skills`
- Branch: `dfrysinger/self-compact-deferred-brief-gate`
- Plan: `design/self-compact-brief-protocol.md`
- Definition of Done:
  `Definition of Done: Self-Compact Brief Protocol`
- Push policy: push reviewed and validated work to `origin/main` when the
  Definition of Done is complete.

## Required process skills

- **Governing:** `/dfrysinger-skills:development-loop`
  - Owns implementation order, live-proof gating, review, final validation,
    landing, and completion.
- **Execution:** `/dfrysinger-skills:dual-review`
  - Reviews the complete implementation only after the current-tree live proof
    passes.
- **Execution:** `/deep:code-review`
  - Performs the critical fail-closed boundary ensemble review after
    implementation dual review.
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

Running implementation review on candidate `beedc58`. The deterministic suite
passes in the repository, and the installed candidate has passed the complete
tmux lifecycle.

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

- Candidate: `beedc58e25febae37c1b0a5acf5e9e948bba544a`.
- The repository and installed helper hashes match.
- The repository deterministic suite passes.
- The live lifecycle exposed and closed one detached-PATH defect. The verifier
  now uses the validated absolute tmux path for every tmux operation.
- Next action: complete implementation dual review and the critical fail-closed
  code review, apply any material fixes, and rerun the final lifecycle.

## Live-proof receipt

```text
LIVE_PROOF
candidate: beedc58e25febae37c1b0a5acf5e9e948bba544a
running: installed helper hashes match the candidate; plugin version 0.102.0
scenario: tmux-hosted Copilot CLI, 8,000 disposable lines, draft inserted during the marked delay, deferred brief authorization, compact, continuation, and draft restoration
status: PASS
excluded_outputs: .v102-delay-ready and session evidence files

| checkpoint | expected | observed | evidence | result |
|---|---|---|---|---|
| delayed draft | private draft remains unsubmitted | `V102_PRIVATE_DRAFT_DO_NOT_SUBMIT` stayed in the editor | tmux pane `%81` | PASS |
| structural authorization | one exact helper call binds to the persisted brief | `call_5zlUWdOq6ZSVvgqKUss2gY1g` completed before authorization and one compact followed | session `8dd9eb44-437f-47fd-a002-66525d5a2097`, events 22-33 | PASS |
| compact identity | one successful token-bearing compact advances the checkpoint | token `8ce70174`, `summary_count: 1`, one checkpoint | workspace, events 32-33, checkpoint 001 | PASS |
| continuation | one fixed continuation resumes the retained task | one continuation at event 35 and retained markers at event 38 | events.jsonl | PASS |
| restored draft | original draft returns unchanged | `V102_PRIVATE_DRAFT_DO_NOT_SUBMIT` visible after resume | tmux pane `%81` | PASS |
| teardown | no lock, watcher, or transient marker remains | only the completed run log remains | session files directory | PASS |
| forbidden errors | no duplicate compact, continuation, or unknown-text submission | one compact start, one compact completion, one continuation | events.jsonl | PASS |

first_divergence: none
unverified: none
covered_deltas: none
```
