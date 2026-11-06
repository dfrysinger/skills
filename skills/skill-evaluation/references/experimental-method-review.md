# Experimental-method review

Review the method before spending on baseline or treatment behavior. Use the
existing plan, evidence and `dual-review`; no new runner, dashboard or service
is needed. This gate reviews whether the experiment answers the user's actual
question, not merely whether its own narrower fixture can run.

## Five rules and grading rubric

For every rule, both reviewers cite plan/evidence locations and assign:
**2** = evidenced for the requested execution phase; **1** = a named unresolved
prerequisite with an explicit blocking gate; **0** = missing, contradicted or
substituted. A later phase's pending result is not a defect in a baseline-only
method. Use the rule's stated branch rather than inventing a historical
failure for adoption, regression or a new capability.

| Rule | Evidence required for score 2 |
|---|---|
| R1. Replay a real trigger | For historical work, the exact source event, timestamp/ID, conversation cutoff, prompt bytes and restored state. Preserve original ambiguity, skill names and message roles. Audit every added sentence as sourced restoration or necessary execution setup. Use the [trigger branches](evaluation-playbook.md#choose-the-trigger-and-recovery-expectation); artifact-creation arms produce and exercise their own artifacts. An invented wake, diagnosis or corrected input is a different intervention, not an authentic replay. Synthetic tasks remain separately labeled. |
| R2. Freeze the right control | For historical repair, recover capture-time skills and competing instructions, distinguishing loaded bodies from the available collection. Bind exact bytes/provenance, state and [context policy](case-contract.md#native-historical-continuation). Missing originals block that historical claim. For other comparisons, identify the appropriate unchanged baseline explicitly. Latest-release, no-target and no-skills controls answer different questions. |
| R3. Reproduce before repairing | For repair, baseline execution must demonstrate the specific bad agent behavior before the treatment phase opens. Declare bounded attempts and non-reproduction, setup-error and stop paths first. A failing fixture or a synthetic proxy is not agent reproduction. An unresolved baseline permits investigation, not a claimed fix. Unchanged checks or new capabilities use their declared reference instead. |
| R4. Isolate the intervention | Name exactly what changes and hold all other relevant factors fixed. For skill repair, match trigger, case/state, model/settings, tools/permissions, runtime, criteria, limits and scoring. Model adoption varies the model instead; a whole-setup comparison names that setup as the comparison unit, not an isolated skill effect. Disclose unavoidable historical substitutions. Distinguish clean replacement from an update with identical old history in both arms. Freeze any skill-set delta; attribute only to that set, not individual rules without isolation. Preserve first outcomes, planned repetitions and instruction exposure. Changing a schedule or artifact is legitimate only when its production is the declared intervention. |
| R5. Observe the requested outcome | Required actions work under normal permissions; checks and independent judgments observe actual outcomes, preserved behavior and the declared horizon. Missing operational state blocks executed-recovery claims. Declare development exposure, accounting coverage, decision/stop rules and allowed conclusions. A proposal, skill load or narrower synthetic success does not close the original task. |

## Phase gates

Each reviewer returns a grade for every rule and a verdict for each proposed
phase: **READY** only when all five score 2 and no material finding remains;
**BLOCKED** when an explicit prerequisite prevents readiness; **REVISE** for
a score 0 or a verified material design defect. Scores are not averaged.
Complete static review of a conditional plan can be valid while execution
remains BLOCKED. Reviewers must not fabricate runtime proof to make it READY.

Review the baseline method before its first candidate call. A treatment also
requires the qualifying baseline result and exact changed bytes covered by the
review. A predeclared conditional treatment may reuse that review only when
its intervention and all conditions were already reviewed and subsequently
verified; otherwise submit the material delta to both reviewers first.
No-result and setup failures retain their original records.

Use `dual-review`'s independent families, scope lens for a method/work order,
evidence requirements, bounded rounds and finding disposition. Both families
must complete on the same method/rubric/prompt revision. Keep a receipt binding
their outputs to those bytes, phase verdicts, adjudication and unresolved
prerequisites. A phase opens only when both families independently return READY
for it. Either family's score below 2 keeps it closed until that reviewer
reassesses the same or corrected frozen evidence and both return READY.
Finding disposition cannot override an unresolved BLOCKED or REVISE grade.
Material method/evidence changes invalidate affected approvals until reviewed.
Unchanged repetitions within the reviewed attempt set need no new review.

When checking a rubric against a known malformed plan, give both reviewers
the original user outcome and that plan's actual inputs, not merely its
author's narrowed goal. Record this as static calibration, not evidence that
future agents will follow the skill or that a historical repair works.

## Reviewer addendum

Append this to the filled `dual-review` reviewer prompt for each family;
supply the full method, this rubric and the frozen supporting evidence.
Keep this instruction outside candidate-visible experiment inputs.

```text
This is a pre-run experimental-method review. Judge whether this method
answers the supplied user outcome. Apply R1-R5 in the supplied rubric; do not
grade only the author's substitute goal. Independently inspect provenance,
control identity, exposure, causal contrast, runtime observability and gates.
Return a complete static review even when the method correctly records missing
execution prerequisites. If a claimed fact cannot be assessed from supplied
evidence, mark that fact unresolved; do not treat it as proved.
Keep dual-review's finding schema, evidence, scope, budgets and disposition.
Add "method_assessment": {"phases": [{"phase": "...", "verdict":
"READY|BLOCKED|REVISE", "rules": [{"id": "R1", "score": 0,
"evidence": "path:lines and reason", "prerequisite": null}]}]}.
Include all five rule IDs once per phase. Grade independently; no minimum
finding count or desired verdict is required. Report a material rubric/prompt
loophole as a finding rather than silently repairing the rules while grading.
If a malformed-method calibration is supplied, assess it separately under the
same user outcome and rubric; do not let its scores change the proposed
method's grades. Do not execute experiments or invent missing observations.
```
