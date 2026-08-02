# Evidence-backed learning all-phases autopilot charter

## Objective

Achieve the Definition of Done in
`docs/evidence-backed-learning-plan.md`, the "All phases Definition of Done"
section: evaluation, dependency protection, rollback, and the hot-context
decision are complete after the shipped M1 foundation. Keep working milestone
by milestone; finish only once every item in the "All phases Definition of
Done" section is verifiably met.

## Charter

Keep building against the plan at `docs/evidence-backed-learning-plan.md`
through M2, M3, and M4 in the isolated `feature/evidence-backed-learning`
worktree using
`/dfrysinger-skills:development-loop`, `/dfrysinger-skills:writing-great-skills`,
and `/dfrysinger-skills:dual-review`, with the development loop's live
acceptance gate for end-to-end testing. Use rubber-duck to align on paths
forward whenever stuck. Keep the plan up to date so a future agent can resume
from it. Use subagents for genuinely independent work, not duplicate passes.
Push each milestone to remote main only when that milestone is complete, tested
live, and reviewed clean. Do not stage, revert, or include unrelated changes
from the shared main worktree. Decide every reversible question autonomously.
Freely use real model calls within reason for evaluation acceptance and dual
review. Stay on this course until the objective's Definition of Done, the "All
phases Definition of Done" section, is met.
