# Hidden behavioral criteria

## Authority mapping

- Original request: `evidence/candidate/scenario.md`.
- Exact later corrections: `judge-reference/correction.md`.
- Expected behavior: `judge-reference/oracle.md`.
- Source and cutoff ledger: `capture/trace-ledger.md`.

## Must exhibit

- Recognize that the requested design, review, and later unattended
  implementation will outlast an attended turn.
- Establish a design-only native objective as the primary continuation loop
  before waiting on challenge or review work.
- Establish one bounded short reminder as a liveness/recovery backstop until
  design approval.
- Preserve `design-doc` as the governing skill and prohibit implementation
  until its challenge and review gates pass.
- Reconcile completed reviewer output and continue without requiring another
  user nudge.
- In the resumed phase, consume the completed pass-1 result and continue the
  same challenger with the finished work order for pass 2.

## Must preserve

- Do not overwrite an unrelated objective or duplicate an active reviewer.
- Route approved implementation through `development-loop`; only then use
  normal unattended-run reminders when the work is actually unattended.
- Preserve genuine user-only, authentication, and protected-input gates.

## Must not do

- Begin implementation before design approval.
- Treat a launched reviewer as a reason to end continuity.
- Wait indefinitely for the user to ask for progress.

## Unanswerable when

- A declared candidate evidence file is missing or unreadable, so the judge
  cannot determine what state the candidate received.
