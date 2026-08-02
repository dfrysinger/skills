# Evidence-backed learning M1 autopilot charter

## Objective

Achieve the Definition of Done in
`docs/evidence-backed-learning-plan.md` for M1, the
"M1 Definition of Done" section: artifact routing and evidence envelopes work
end to end without public mutation. Keep working through M1; finish only once
every item in the "M1 Definition of Done" section is verifiably met.

## Charter

Keep building against the plan at `docs/evidence-backed-learning-plan.md`
through M1 in the isolated `feature/evidence-backed-learning` worktree using
`/dfrysinger-skills:development-loop`, `/dfrysinger-skills:writing-great-skills`,
and `/dfrysinger-skills:dual-review`, with the development loop's live
acceptance gate for end-to-end testing. Use rubber-duck to align on paths
forward whenever stuck. Keep the plan up to date so a future agent can resume
from it. Use subagents for genuinely independent work, not duplicate passes.
Push to remote and merge only when M1 is complete, tested live, and reviewed
clean. Do not stage, revert, or include unrelated changes from the shared main
worktree. Decide every reversible question autonomously. Freely use real model
calls within reason for routing acceptance and dual review. Stay on this course
until the objective's Definition of Done, the "M1 Definition of Done" section,
is met.
