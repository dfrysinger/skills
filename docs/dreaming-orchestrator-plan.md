# Dreaming orchestrator: M1 implementation plan

## Objective

Replace the independently scheduled skill-maintenance jobs with one effective
weekly owner that runs the existing passes in a fixed order:

1. consolidate recent sessions into skills;
2. roll durable memories into skills;
3. prune or consolidate the settled skill library.

M1 fixes scheduling, concurrency, halt, and observability. It does not add a new
curation capability.

## Lane

Systemic. The change alters shared scheduling, cross-process locking, failure
propagation, and the ownership of three background workflows.

## Non-goals

- Add the user-facing `dreaming` skill or new curation behavior.
- Make the curator mutate skills; its scheduled M1 pass remains a dry run.
- Replace the existing review and memory content ledgers.
- Add measured-improvement evaluation for generated skill edits.
- Generalize the daemon beyond the existing personal macOS launchd setup.
- Change foreground skill-management commands that are not autonomous paths.

## Reuse contract

M1 extends the existing daemon system rather than creating a second scheduler.

- Reuse `skills_run_copilot_bounded` for each headless Copilot pass.
- Reuse the existing daemon lock location and stale threshold.
- Reuse the three existing pass prompts and their content-specific ledgers.
- Reuse the current halt-switch path.
- Reuse launchd installation, self-test, and watchdog entry points.
- Add only the orchestration state needed to coordinate the existing passes.
- Extend autonomous end-of-task dispatch to participate in the same writer
  lease; scheduled ownership alone is insufficient while dispatch remains a
  second autonomous writer.

## Architecture

### Scheduled ownership

Install one scheduled `dreaming` LaunchAgent plus the existing manual self-test
and daily watchdog. Remove and boot out the legacy `sweep`, `curator`, and
`memory` agents during both install and uninstall migration paths.

The `dreaming` agent launches daily and always runs transcript consolidation.
A daemon-scoped weekly bucket gates only memory roll (including deletion of
memories safely committed into skills) and dry-run pruning, so the backstop can
review up to three sessions per day while the heavier maintenance passes run
at most once per calendar week. A sleeping laptop catches up on the next daily
tick without completion-time drift.

### Process structure

Split the current wrapper into two responsibilities:

- `daemon-pass.sh`: lock-free execution of one bounded Copilot prompt. It
  requires a pass name, prompt, and expected result sentinel and returns nonzero
  unless both the Copilot completion footer and pass sentinel indicate success.
- `dreaming-run.sh`: owns cadence, the global lock, halt checks, pass ordering,
  fail-fast behavior, reporting, and the orchestration ledger.

`daemon-run.sh` remains as a compatibility wrapper for a manually requested
single pass. It acquires the same lock, checks the global halt, and delegates to
`daemon-pass.sh`.

Autonomous end-of-task `skill-review dispatch` acquires a session lease through
the same lock helper before its first write and releases it after its guards and
ledger append. If the lease is unavailable or the global halt is active, the
dispatch records a deferred result without mutating either skill root. The
scheduled orchestrator therefore cannot overlap dispatch writes, staging,
commits, or ledger updates.

### Lock semantics

The orchestrator acquires the lock before reading or changing cadence state and
holds it until the complete report and ledger entry are written.

- A live process owner whose recorded process identity still matches is never
  displaced, regardless of lock age.
- PID reuse is detected by comparing the recorded process start identity with
  the live process before treating it as the owner.
- A dead owner younger than two hours is treated as ambiguous and fails closed.
- A dead owner at least two hours old may be reclaimed.
- An unreadable or malformed lock fails closed.
- Lock contention is a recorded healthy skip, not a successful pipeline run.

The lock supports both process owners and bounded session leases. A session
lease has a unique token and two-hour expiry because no process remains alive
between agent tool calls. Dispatch must validate its token and renew the lease
immediately before every file write, stage, commit, or ledger append. A failed
renewal or token mismatch aborts the dispatch before mutation. Release is
token-matched, so an expired owner cannot remove its successor's lock. The lock
timestamp is refreshed between passes or dispatch phases so a healthy owner is
clear to diagnostics.

### Cadence semantics

Cadence is anchored to a stable seven-day epoch bucket, not to the prior
completion time. State records the last fully successful bucket and timestamp,
not the last attempt.

- A cadence skip does not change the successful bucket or timestamp.
- A halted, locked, or failed run does not change the timestamp.
- A fully successful consolidate -> roll -> prune run commits the current bucket
  after the final pass succeeds.
- A partial failure retries on the next daily tick. Existing content ledgers
  make already completed consolidate and roll work idempotent.
- Installation seeds the current bucket from the latest legacy successful state
  so migration does not trigger an unexpected immediate run.

The orchestrator cadence is daemon-scoped. Existing foreground/manual cadence
state does not consume or delay the orchestrated weekly run.

### Ordered failure behavior

Each pass emits a uniform machine-readable result:

```text
DREAM_PASS_RESULT: ok <summary>
DREAM_PASS_RESULT: aborted <reason>
```

The bounded process footer proves that Copilot stopped. The pass result proves
that the requested work succeeded. Both are required.

The pipeline is fail-fast:

- consolidate failure prevents roll and prune;
- roll failure prevents prune;
- prune failure prevents cadence advancement;
- an explicit no-work result is `ok`, not `aborted`.

All daemon prompts use one daemon-session marker so transcript consolidation
excludes every pass from future learning.

The consolidate pass snapshots the public repository's pre-run status and
proves it is unchanged afterward. Pre-existing human work is allowed because
consolidate writes only to the local skill root. Passes that may write the
public repository retain their scoped staging and cleanliness requirements.

### Halt semantics

The shared halt switch is checked:

- before cadence evaluation;
- before launching every pass;
- inside every autonomous pass before its first mutation;
- immediately before autonomous memory deletion or live archive application.

A halt observed between passes stops the pipeline and leaves cadence unchanged.
M1 does not attempt to terminate a Copilot process already in flight.

### Reports and ledgers

One atomically replaced cadence document is authoritative only for the
successful bucket and its committing run id. Every tick writes an atomically
created per-run result under a unique run id; these immutable run records are
the terminal authority for successful, skipped, contended, and aborted ticks.
Lock contenders never replace cadence state.

Every daily tick commits one orchestration result containing:

- run id and timestamps;
- overall status: `ok`, `skipped`, or `aborted`;
- skip or failure reason;
- ordered per-pass status, duration, and log path;
- cadence state before and after the attempt.

For a successful due run, atomically write its per-run result, atomically commit
cadence referencing that run id, then mark the per-run result committed.
Reports and the JSONL ledger are derived from per-run results. On startup,
repair an unmarked result referenced by cadence and any missing report or ledger
record before evaluating cadence. A success result not referenced by cadence is
an interrupted uncommitted attempt and does not suppress retry. Run ids make
repair and append deduplication idempotent. Existing review and memory ledgers
remain authoritative for content idempotency.

Cadence skips, active halt switches, and lock contention are explicit healthy
skip states. The watchdog evaluates pass engagement only when a pipeline was
actually due and started. It still surfaces a halt advisory and alerts when the
last successful cadence is more than two weekly buckets old, regardless of
fresh daily skip records.

## Migration

1. Activate the shared halt switch.
2. Confirm no legacy daemon process owns the lock.
3. Back up every installed legacy plist to a timestamped migration directory.
4. Install the new scripts and rendered `dreaming` LaunchAgent.
5. Boot out and remove legacy `sweep`, `curator`, and `memory` LaunchAgents and
   their installed plist files.
6. Run the updated self-test under launchd.
7. Run deterministic orchestration tests.
8. Kickstart a non-destructive launchd canary while cadence is not due and
   verify the recorded cadence-skip result.
9. Exercise a forced-due canary with fake pass commands outside the live skill
   and memory stores.
10. Remove the halt switch only after all checks pass.

Rollback boots out `dreaming`, restores the exact archived legacy plist files,
and bootstraps them under launchd. It does not assume every legacy plist existed
in git. State and reports are additive; rollback does not delete them.

## Deterministic check contract

### Lock tests

- **Live owner:** create a lock with a live PID older than two hours. The
  orchestrator skips or aborts without replacing it.
- **Reused PID:** create a lock whose PID is live but whose process start
  identity differs. The lock is not treated as a live owner.
- **Young dead owner:** create a lock with a dead PID younger than two hours.
  The orchestrator fails closed.
- **Stale dead owner:** create a lock with a dead PID older than two hours. The
  orchestrator reclaims it and proceeds.
- **Malformed lock:** omit or corrupt PID/start fields. The orchestrator fails
  closed.
- **Dispatch overlap:** hold the orchestrator lock and attempt autonomous
  dispatch; dispatch records deferral and performs no write, stage, commit, or
  ledger append.
- **Active dispatch lease:** hold an unexpired dispatch lease and start the
  orchestrator; it records lock contention and launches no pass.
- **Expired dispatch lease:** present an expired lease and start the
  orchestrator; it reclaims the lease and proceeds.
- **Reclaimed dispatch resume:** reclaim an expired dispatch lease, then resume
  the old dispatch; token validation prevents every subsequent file write,
  stage, commit, release, and ledger append.

### Cadence tests

- A not-due tick records `skipped: cadence-not-due`, runs no pass, and preserves
  the successful bucket and timestamp.
- Simulated daily ticks across several weeks run once in each stable weekly
  bucket without accumulating completion-time drift.
- A fully successful due run advances the successful bucket once.
- A failed due run preserves the prior successful bucket and retries when run
  again in the same bucket.

### Ordering and failure tests

- Three successful fake passes run exactly once in consolidate -> roll -> prune
  order.
- Consolidate failure prevents both later passes.
- Roll failure prevents prune.
- A halt inserted between passes prevents the next pass.
- Every prompt contains the common daemon-session marker and uniform result
  contract.
- Pre-existing public-repository changes remain byte-for-byte unchanged and do
  not prevent consolidate, roll, or prune from reaching their own gates.

### Reporting tests

- Every terminal state writes a parseable result document.
- Every terminal state appends exactly one parseable ledger record.
- The report names only passes that actually started and marks unstarted
  downstream passes explicitly.
- A torn or partial ledger line is not produced when a pass fails.
- Concurrent owner and contention ticks retain both per-run records without a
  lost cadence update.
- Fault injection after per-run result creation, cadence commit, report write,
  and ledger append is repaired idempotently on the next startup without losing
  or double-advancing cadence.

### Installation and watchdog tests

- Install renders and loads `dreaming`, `selftest`, and `watchdog`.
- Install and uninstall remove all known legacy labels and plist files,
  including independently provisioned `memory`.
- Self-test validates all prompts, result sentinels, lock behavior, repository
  boundaries, and headless Copilot authentication.
- Watchdog treats cadence, halt, and lock skips as healthy fresh ticks and
  alerts on stale ticks, aborted due runs, missing reports, and permission
  failures.
- Watchdog retains a halt-switch advisory and alerts when no successful
  pipeline has completed for more than two weekly buckets.
- Rollback restores the exact independently provisioned legacy plist set from
  the migration backup.

## Implementation sequence

1. Add the daemon-scoped state and lock helpers with deterministic tests.
2. Extract `daemon-pass.sh` and retain `daemon-run.sh` compatibility.
3. Add `dreaming-run.sh`, reports, ledger writes, and fake-runner test seams.
4. Normalize all prompts to the common daemon marker and pass result contract.
5. Update launchd templates, installer migration, self-test, and watchdog.
6. Remove duplicate daemon cadence gates while preserving foreground behavior.
7. Update README and directly affected skill documentation.
8. Run deterministic tests and launchd self-test.
9. Run the non-destructive launchd canary.
10. Run dual review, resolve material findings, and repeat affected checks.
11. Commit with scoped staging, install the reviewed version, remove the halt
    switch, verify clean state, and push the public repository.

## M1 Definition of Done

- [x] One scheduled owner replaces the legacy sweep, memory, and curator jobs.
- [x] The owner holds one fail-closed lock across the entire ordered pipeline.
- [x] Autonomous end-of-task dispatch participates in the same writer lease.
- [x] Consolidate, roll, and prune run only in that order.
- [x] A failed or halted pass prevents every downstream pass.
- [x] Cadence advances only after all three passes succeed.
- [x] Weekly cadence is bucket-anchored and does not drift with pass duration.
- [x] Every pass uses the common daemon marker and result-sentinel contract.
- [x] Every tick produces one parseable report and one orchestration ledger
      record, including healthy skips.
- [x] The watchdog distinguishes healthy weekly cadence skips from failures.
- [x] The watchdog alerts on an over-age successful cadence and retains halt
      advisories.
- [x] Installer migration removes all legacy labels and plist files.
- [x] Rollback restores the exact backed-up legacy LaunchAgents.
- [x] Authoritative state, reports, and ledger records recover consistently
      after interrupted persistence.
- [x] Concurrent owner and contention ticks cannot overwrite each other's
      records or cadence state.
- [x] Deterministic lock, cadence, ordering, failure, reporting, installer, and
      watchdog checks pass.
- [x] The launchd self-test and non-destructive live canary pass on the reviewed
      tree.
- [x] Directly affected skills validate successfully.
- [x] Dual review has no verified in-scope material finding.
- [x] Public and local repositories are clean; the public commit is pushed.
