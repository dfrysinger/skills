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

Final reviewed runtime and real tmux lifecycle are complete. Both reviewer
families confirmed the closure fixes with no remaining findings. The exact
installed runtime from candidate `df7ea88` passed the complete draft-bearing
Scenario A lifecycle. Landing, installed-copy verification from `main`, and
publication remain.

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

- Candidate: `df7ea887fc34fe4c03e0e9e04412e08f16c424c3`.
- Deep-review artifacts:
  `/Users/dfrysinger/.copilot/session-state/dc8dcc47-cbbc-5f0e-87fd-043acec5e7ae/files/dcr-self-compact-v102/`.
- Implemented remediation: bounded authorization parsing, semantic root-event
  handling, request-to-completion conflict checks, ownership and handoff
  revalidation, detached failure reporting, continuation cleanup, portable
  helper invocation, and the expanded fail-closed regression matrix.
- Final runtime hashes:
  - submit helper:
    `8e17fe855b5c4b356853f0e4e93965e3b80111b1a510fc8fdea01ff92e12f622`
  - detached verifier:
    `70a9313adf7f2159365025e1e1832817adc98830e617652106a2005ec0abe06d`
- The repository and installed runtime hashes match, and the installed plugin
  reports version `0.103.0`.
- Terra and Opus both confirmed the final finding-scoped closure with no
  remaining findings.
- Next action: commit this final receipt, merge to local `main`, reinstall from
  the landed commit, verify the installed hashes and clean runtime state, push
  `origin/main`, and stop schedule 9.

## Live-proof receipt

```text
LIVE_PROOF
candidate: df7ea887fc34fe4c03e0e9e04412e08f16c424c3
running: installed runtime hashes match the candidate; plugin version 0.103.0
scenario: tmux-hosted Copilot CLI, 8,000 disposable lines, draft inserted during the marked delay, deferred brief authorization, compact, continuation, and draft restoration
status: PASS
excluded_outputs: session evidence files

| checkpoint | expected | observed | evidence | result |
|---|---|---|---|---|
| delayed draft | private draft remains unsubmitted | `V103_FINAL_PRIVATE_DRAFT_DO_NOT_SUBMIT` stayed in the editor and never became a user message | tmux pane `%84`, zero matching event records | PASS |
| structural authorization | one exact portable helper call binds to the persisted brief | `call_fCOljMNWJ0J9qzxjhpnxMNWY` used the exact `$HOME` command and completed before one compact | session `63281e8d-b7ed-4c60-8406-2a6112b5994e`, events.jsonl | PASS |
| compact identity | one successful token-bearing compact advances the checkpoint | token `6c5195ef`, `summary_count: 1`, one checkpoint | workspace, events.jsonl, checkpoint 001 | PASS |
| continuation | one fixed continuation resumes the retained task | exactly one `Compaction done; resume, do not compact.` user message | events.jsonl | PASS |
| retained meaning | all three identifiers survive compaction | `V103EMBEROTTER V103COBALTLOON V103JADEBADGER V103_FINAL_LIVE_RESUMED` exactly once | events.jsonl and tmux pane `%84` | PASS |
| restored draft | original draft returns unchanged | `V103_FINAL_PRIVATE_DRAFT_DO_NOT_SUBMIT` visible after resume | tmux pane `%84` | PASS |
| teardown | no lock, watcher, or transient marker remains | no lock, ready, armed, cancelled, or handoff artifact and no watcher process | session files directory and process table | PASS |
| forbidden errors | no duplicate compact, continuation, or unknown-text submission | one compact start, one compact completion, one continuation | events.jsonl | PASS |

first_divergence: none
unverified: none
covered_deltas: none
```
