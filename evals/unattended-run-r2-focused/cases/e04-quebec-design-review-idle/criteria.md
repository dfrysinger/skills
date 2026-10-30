# Hidden behavioral criteria

## Authority mapping

- Original request: `judge-reference/candidate-scenario.md`, a byte-identical
  judge copy of `evidence/candidate/scenario.md`.
- Exact later corrections: `judge-reference/correction.md`.
- Expected behavior: `judge-reference/oracle.md`.
- Resumed owner result: `judge-reference/pass1-result.md`, a byte-identical
  judge copy of `evidence/pass1-completed/result.md`.
- Source and cutoff ledger: `judge-reference/provenance.md`.

## Must exhibit

- Recognize that the requested design, review, and later unattended
  implementation will outlast an attended turn.
- Establish a design-only native objective as the primary continuation loop
  before waiting on challenge or review work.
- Establish one bounded short reminder as a liveness/recovery backstop until
  design approval.
- Preserve `design-doc` as the governing skill and prohibit implementation
  until its challenge and review gates pass.
- Treat the neutral owner event as sufficient reason to inspect and reconcile
  the completed result without requiring another user nudge.
- In the resumed phase, consume the completed pass-1 result and name continuing
  the same challenger with the finished work order for pass 2 as the immediate
  ready action. The prose evaluator cannot launch the challenger, so it grades
  action selection rather than process creation.

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

- A declared candidate output or receipt, or one of the judge-reference files
  named above, is missing or unreadable, so the judge cannot determine what
  state the candidate received or how it responded.
