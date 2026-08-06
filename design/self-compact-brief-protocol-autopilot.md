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

Closing two material findings from the two-family review of the live-proven
candidate. Both reviewers found that the authorization byte cap was
incorrectly reused for post-Enter lifecycle evidence; Terra also found that a
root completion-only interleaving did not cancel authorization. Scoped runtime
fixes and deterministic regressions are active. The exact installed runtime
from candidate `0eedd64` remains the latest complete tmux lifecycle PASS.

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

- Candidate: `0eedd64601cebb2c2688b1527be1fe86b30d1472`.
- Deep-review artifacts:
  `/Users/dfrysinger/.copilot/session-state/dc8dcc47-cbbc-5f0e-87fd-043acec5e7ae/files/dcr-self-compact-v102/`.
- Implemented remediation: bounded authorization parsing, semantic root-event
  handling, request-to-completion conflict checks, ownership and handoff
  revalidation, detached failure reporting, continuation cleanup, portable
  helper invocation, and the expanded fail-closed regression matrix.
- The repository and installed runtime script hashes match, and the installed
  plugin reports version `0.103.0`.
- Closure findings: make post-Enter event observation forward-progressing and
  independent of `AUTH_SCAN_BYTES`; reject root completion-only conflict
  events; explicitly propagate the validated start-grace value.
- Next action: finish the scoped fix and full deterministic run, perform a
  finding-scoped two-family closure check, then install the resulting commit
  and rerun the complete live lifecycle before landing.

## Live-proof receipt

```text
LIVE_PROOF
candidate: 0eedd64601cebb2c2688b1527be1fe86b30d1472
running: installed runtime hashes match the candidate; plugin version 0.103.0
scenario: tmux-hosted Copilot CLI, 8,000 disposable lines, draft inserted during the marked delay, deferred brief authorization, compact, continuation, and draft restoration
status: PASS
excluded_outputs: session evidence files

| checkpoint | expected | observed | evidence | result |
|---|---|---|---|---|
| delayed draft | private draft remains unsubmitted | `V103_PRIVATE_DRAFT_DO_NOT_SUBMIT` stayed in the editor and never became a user message | tmux pane `%83`, event count | PASS |
| structural authorization | one exact portable helper call binds to the persisted brief | `call_r6lmzQwSsIyL45K5nBAvrVKq` used the exact `$HOME` command and completed before one compact | session `bda6a159-7e76-4455-b8d4-a1d3e8969f37`, events 32-41 | PASS |
| compact identity | one successful token-bearing compact advances the checkpoint | token `b1071aed`, `summary_count: 1`, one checkpoint | workspace, events 40-41, checkpoint 001 | PASS |
| continuation | one fixed continuation resumes the retained task | exactly one fixed continuation at event 43 | events.jsonl | PASS |
| retained meaning | all three identifiers survive compaction | `V103EMBEROTTER V103COBALTLOON V103JADEBADGER V103_LIVE_RESUMED` at event 45 | events.jsonl and tmux pane `%83` | PASS |
| restored draft | original draft returns unchanged | `V103_PRIVATE_DRAFT_DO_NOT_SUBMIT` visible after resume | tmux pane `%83` | PASS |
| teardown | no lock, watcher, or transient marker remains | only the completed run log remains | session files directory | PASS |
| forbidden errors | no duplicate compact, continuation, or unknown-text submission | one compact start, one compact completion, one continuation | events.jsonl | PASS |

first_divergence: none
unverified: none
covered_deltas: none
```
