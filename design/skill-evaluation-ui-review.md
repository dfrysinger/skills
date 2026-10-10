# Skill Evaluation UI Design Review

**Subject:** `design/skill-evaluation-ui.md`
**Review type:** critical systemic design review
**Round 1 status:** blocked by seven material findings
**Round 2 status:** blocked by two material contract findings
**Round 3 status:** passed
**Review gate:** passed

## Round 1

Both required model families completed static review and applied the design
scope lens:

- Claude Opus 5.5: complete, 11 tool calls, 12 minutes.
- GPT-5.6 Terra: complete, 12 tool calls, 19 minutes.

## Adjudicated findings

| Finding | Source | Disposition | Resolution |
| --- | --- | --- | --- |
| Token-bearing URLs would enter session output and browser history | Opus | must-fix | `open` sends the fragment directly to the browser, returns only a token-free receipt, and the shell strips the fragment before loading data |
| Default same-user prose candidates could acquire the dashboard capability | Terra | verify | The cited runner assumption was wrong: prose candidates receive only `skill,view`, not shell or network. Browser read capabilities are memory-only; an out-of-workdir root-secret view fails audit and rotates the generation before output admission |
| Foundation could not identify a “current integrated revision” | Opus | must-fix | Foundation scorecards are grouped by exact observed skill identity; current/integrated roles remain in deferred Slice 3 |
| Writer-local sequences would report false gaps under concurrency | Opus | must-fix | Foundation removes sequence completeness; evaluator invocations have unique writers and same-session emits serialize under one generation lock |
| Credits-as-cents conflicted with evaluator-native units | Opus and Terra | must-fix | Raw AI credits and premium requests remain authoritative; one-cent display is an explicitly labeled user transform applied only to known credits |
| Slice 1 depended on Slice-2 registration and lacked its own live proof | Opus | must-fix | Slice 1 creates the immutable campaign identity and has a separate installed-plugin proof; Slice 2 adopts it and has its own proof |
| The unattended objective authorized deferred slices | Terra | must-fix | Objective, charter, schedules, and Definition of Done now stop at Foundation Slices 1 and 2 |

No adjacent or optional finding was promoted into scope.

## Material redesign trigger

The capability transport and exact prose tool boundary materially refined the
trust analysis. The focused constraint refresh returned `CONTINUE`, gate
`CLEAR`: the supported candidate has no shell or HTTP operation, the root
secret is not HTTP authority, and any audited dashboard-state read rotates the
generation before output admission.

## Round 2

Both model families completed within the fix-verification budget and applied
the design scope lens.

- GPT-5.6 Terra resolved all seven prior findings with no new finding.
- Claude Opus 5.5 resolved five findings and found two remaining material
  contract gaps.

### Adjudication

| Finding | Disposition | Resolution |
| --- | --- | --- |
| Root-secret minting and authenticated health lacked a defined transport | must-fix | Added control-only loopback health and open endpoints, explicit root-secret authentication, transient CLI-memory handling, projection-route refusal, and matching capability checks |
| Objective still promised deferred lineage, experiment, ablation, and current-revision surfaces | must-fix | Narrowed Objective and foundation questions to completed history and active local work; recorded requested follow-on outcomes as non-authorizing Deferred Slices 3-6 |

Round 3 is resolution-only for these two findings. It cannot reopen unrelated
discovery. Implementation remains blocked until both model families verify
both resolutions with no material regression in their fix delta.

## Round 3

Both model families completed within the resolution-only budget, applied the
design scope lens, verified both fixes, and reported no findings.

- The root-secret control transport is explicit, separate from browser and
  projection authorization, and covered by an observable refusal check.
- The objective and user questions authorize only completed history and live
  local foundation behavior. Requested lineage, cloud, experiment, ablation,
  and drill-down outcomes remain gated on their recorded entry conditions.

No must-fix, verification, or follow-up finding remains.
