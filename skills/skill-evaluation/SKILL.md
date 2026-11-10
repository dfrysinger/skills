---
name: skill-evaluation
description: Evaluate agent skills with frozen cases. Use when reproducing agent failures, improving instructions, replaying recovery triggers, comparing skills or models, testing skill selection, minimizing skills, or qualifying a release.
---

# skill-evaluation

**Reproduce, compare, then conclude.** A passing agent response is not evidence
that a skill improved it. Test the behavior the user needs, starting at the
event that should cause it.

## 1. Declare the question and trigger

Read the [evaluation playbook](references/evaluation-playbook.md) and choose
the branch for the user's decision. Search the
[task catalog](references/task-catalog.md) when a checkout exists; reuse exact
cases and prior outcomes before creating another.

For a new negative example, default to preventing the failure before the
user needed to intervene, not improving the reply to that intervention.
Measure useful autonomous work for an autonomy failure. An explicit request
to improve the response instead selects that narrower goal. If prevention
cannot be tested or achieved, follow the playbook's
[least-intervention fallback](references/evaluation-playbook.md#choose-the-trigger-and-recovery-expectation)
and propose it to the user rather than silently changing the goal.

Record the following in the existing plan or evaluator report, not another
tracking system:

| Field | Required decision |
|---|---|
| Question | Repair a reproduced failure, compare setups, check selection, preserve behavior, or minimize instructions. |
| Trigger | Exact user request, scheduled prompt, objective/artifact creation request, or ongoing work boundary. |
| Expected behavior | Prevention, recovery without corrective steering, response to user correction, or another concrete task outcome. |
| Starting state | Conversation, loaded instructions, files, objective, schedules, tools and permissions needed at that trigger. |
| Success | Observable result and horizon; distinguish a proposed action from performed work. |
| Comparison | Capture-time control for historical repair, exact proposed change, and available versus already-loaded skill contents; name no-skill arms separately. |
| Attempts | Planned repetitions, fixed model/settings, criteria, limits, first-outcome retention and stop rule. |
| Case roles | Development, maintained regression, or unused confirmation, including prior feedback exposure. |

Use the playbook's [trigger selection](references/evaluation-playbook.md#choose-the-trigger-and-recovery-expectation)
for historical failures. A scheduled wake can be an ordinary recovery
opportunity. A new hint about the error is corrective steering. Preserve a
skill name already in the original trigger; adding one for the test changes
what it measures. Explicit loading tests behavior after selection, not discovery.

**Complete when:** the trigger, starting state, outcome and comparison answer
the user's question. Keep unresolved parts of that question in the plan.

Keep one active work order: the selected question, current frontier, owner,
remaining prerequisite and next delivery. Replace superseded instructions in
the plan, charter and objective; preserve their evidence in linked history.
After disproportionate preparation or repeated internal repairs, identify the
first divergence and replace the implicated check plan before more spending.
A smaller diagnostic remains a separate result, not completion of that question.

## 2. Make the test capable of observing that behavior

Run model calls on **GitHub Actions VMs**, using the existing private corpus
repository and [Actions procedure](references/large-actions-campaign.md).
Prepare cases and inspect results locally. Local model runs or native cloud
agent tasks require explicit user choice. Reuse supported runtimes rather
than creating another runner.

Use the [case contract](references/case-contract.md) and, for historical
evidence, [capture procedure](references/historical-case-capture.md). Preserve
original words and message roles. Keep later corrections and answers hidden
unless response to that correction is the declared test.

Restore state at the same cutoff as the trigger. When artifact creation is
under test, let each arm produce its own artifact and exercise its later use.
When recovery is under test, keep the existing bad artifact. New actions
determine later observations; recorded future tool results are not valid
after a different action.

Match the runtime to the outcome:

- **Response-only:** `skill` and `view` can test a decision or proposal.
- **Performed work:** use an editable
  [repository task](references/repository-tasks.md) or the required actual app,
  service and operational state.
- **Selection or recovery without steering:** replay the ordinary trigger
  through a route without added diagnosis or forced target loading. The
  [selection procedure](references/skill-selection.md) separates attempted
  invocation, successful loading and task outcome.

Inspect the rendered prompt and actual child-process configuration before
dispatch. Prove required operations under normal permissions. A VM, successful
import, authentication, or CLI exit zero alone does not establish readiness.
Distinguish a clean replacement from an update during ongoing work using the
[skill-context policy](references/case-contract.md#native-historical-continuation).
Reloading availability does not prove a fresh invocation or removal of old text.

Keep preparation, permission readiness, actual model-context consumption and
behavioral improvement separate. Prove each when the current claim needs it.
Treat optional cache metadata as diagnostic unless its effect on the required
input or behavior is established. Reuse operational proof while the runner,
permissions and required operations remain applicable. New skill bytes or
binding hashes alone do not require another model setup run; verify those
bindings mechanically and observe instruction exposure in the candidate run.
Choose the cheapest check that exercises an infrastructure change, including
preparation and transport costs.

If needed state or tools are unavailable, record the missing prerequisite.
A narrower decision screen may answer a separate question, but does not close
the original executed-recovery requirement.

Resolve `SKILL_DIR` to this evaluation skill's directory. Freeze and verify the
case with the existing evaluator:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" freeze CORPUS --case CASE_ID
python3 "$SKILL_DIR/scripts/skill_eval.py" verify CORPUS --case CASE_ID
```

For scaffolding, commands and evidence layout, use
[direct evaluator commands](references/direct-evaluator-commands.md) and
[case contract](references/case-contract.md). Validate material criteria
against the [actual environment](references/judgment-environment-fit.md).

Before any behavioral run, including the baseline, apply the
[experimental-method rules, rubric and reviewer addendum](references/experimental-method-review.md).
Have independent Claude and GPT reviewers grade the same frozen method and
evidence. Review completion is not execution readiness: unresolved prerequisites
block the affected phase. Reuse an unchanged review; re-review material changes
to the trigger, control, intervention, runtime, criteria or stopping rule.

**Complete when:** the selected route can perform the required work, all
criteria have observable evidence, and candidate access excludes hidden answers.
Otherwise retain the concrete setup prerequisite and supported narrower scope.

## 3. Establish the unchanged baseline

For a historical repair, the primary control is the original capture-time skill
setup, not the latest release. Recover actual loaded bodies and available
collection where relevant, with source revisions or byte hashes. A current-release
control answers a different question. Missing original bytes or state remain
prerequisites; synthetic fixtures cannot replace the historical comparison.
Disclose historical model/runtime substitutions and hold them fixed across arms.

Run the exact unchanged setup first. Observe the reported bad
behavior through the trigger and outcome above, not merely a related symptom
or an answer agreeing with a correction.
A grader rejecting an unfinished fixture proves its check can fail; it is not
evidence that the unchanged agent reproduces the failure.

Classify the result before changing instructions:

| Baseline result | Next action |
|---|---|
| Reported behavior reproduced | Preserve the trace; identify the first wrong decision and a general correction to compare. |
| Valid run avoids the behavior | Finish the declared population, retain non-reproduction, then inspect a concrete fidelity difference or hypothesis. A further attempt must answer that recorded question, not reopen an unchanged wave. |
| Setup, access or grading fails | Repair that stage separately; preserve the error and reuse intact output for downstream repair. |
| Only a narrower proxy succeeds | Report that observation and keep the original failure unresolved. |

Proceed to a repair comparison only after a baseline demonstrates the target
failure or measured deficiency. If no failure reproduces, this remains a
reproduction investigation, not a proven fix. Preserve natural ambiguity;
changing a faithful task to make the desired answer easier is not skill repair.
An identical observable input can produce a different decision. Accept honest
non-reproduction rather than coaching the prompt or tightening the grader to
force the historical failure.

Regression checks, adoption comparisons and minimization need an unchanged
reference but not an invented failure. A new capability uses an explicit
baseline rather than pretending a historical failure exists.

**Complete when:** retained evidence establishes the baseline outcome and
whether repair, further diagnosis, comparison, or a no-change conclusion follows.

## 4. Change one mechanism and compare

For a reproduced repair, classify the cause: skill instructions, instruction
interaction, model variation, missing context, runtime, packet, or grading.
Inspect the whole candidate-visible instruction stack before blaming one skill.
Repair test defects outside the skill, preserving old outcomes and separating
corrected inputs.

For a surprising judgment, check its claim against the complete delivered
answer, read receipts, rubric and visible instructions before editing a skill
or repeating a candidate. If the answer contradicts the claimed omission,
repair the judgment from retained output and label it separately.

For a comparison, vary only the declared factor and hold the other conditions
fixed. An instruction repair compares one general correction with unchanged
instructions on the same frozen case, trigger, model/settings, tools, criteria
and limits. Expanded skill visibility, forced loading or changed context limits
are separate runtime interventions; success there does not establish a repair
under the original settings. Model adoption varies the model instead; follow
its selected comparison contract. Judge actual outcome movement, separately
from use of a changed instruction. Planned repetitions address variation; a lucky
before/after pair does not establish reliability.

An unchanged evaluation, such as a regression check, needs no proposed change
or winner selection. Retain its baseline result and continue to step 5.

Retain every first outcome, candidate output, raw log, actual skill/model/
runtime identity, check, judgment and measurement. Required skill loading
needs a matching successful completion; an unnecessary attempted invocation
still counts as a selection error even if loading failed.
Use [measurement](references/measurement.md) for incomplete accounting and
resumed-session totals. Report unknown cost as unknown.

Use [parallel treatment search](references/parallel-treatment-search.md) only
when choosing between mechanisms is necessary. For material experimental
scope, architecture, trust or authority changes, invoke `constraint-challenge`
before the disputed addition; only its accepted scope permits that addition.
Follow development-loop's external-action authority boundary.

**Complete when:** the declared comparison shows improvement, no improvement,
regression, or an explicit inconclusive result, or the unchanged evaluation
has its retained result. A required criterion or failed execution cannot be
replaced with instruction uptake or persuasive prose.

## 5. Confirm the supported claim

Before calling a repair successful, exercise the required outcome with the
corrected artifact and protect the declared maintained behavior. Include
genuine-stop cases when repairing unnecessary waits. A short recovery test
does not establish hours of productive autonomy.

Independent Claude and GPT judges must both PASS for material behavioral
success. Any FAIL makes the behavioral result FAIL; otherwise any UNANSWERABLE
makes it UNANSWERABLE. Keep mechanical validity, product checks and judgments
separate. Report first attempts and retry-assisted successes separately.

Choose only the additional method the claim requires:

- Shared multi-task improvements: [cumulative hill climb](references/cumulative-skill-hill-climb.md).
- No-skill advantage, release qualification or unused transfer:
  [release qualification](references/release-qualification-and-generalization.md).
- Instruction reduction: [ablation](references/ablation-campaign.md).
- Model or collection adoption: [setup comparison](references/evaluation-playbook.md#5-compare-models-or-skill-collections).

Current versus previous skill tests improvement from that revision. Removing
only the target skill tests its contribution within the remaining collection.
Removing all skills tests the collection. Run the control required by the
claim; an unrun control is **NOT RUN**, not an implied baseline.

**Complete when:** the exact artifact supports the declared claim and required
preservation checks, or the report names the failed gate and remaining evidence.
A draft, a qualified source change and a released installation are separate.

## 6. Report the answer, not the machinery

Use the [completion report](references/completion-report.md). Lead with the
question, what was actually tested, controls run and the supported conclusion.
State whether the original failure reproduced, whether work was executed,
whether the agent received corrective steering, and whether a change improved
the result. Keep run IDs and file digests in supporting evidence.

State skill size changes separately from evaluator code, cases and run files.
A smaller file is not proof of better behavior. Register safe native outcomes
and exposure in an available catalog; keep raw packets and local bindings out.

**Complete when:** the reader can distinguish reproduced failure, observed
success, measured improvement and untested claims. The original user outcome
is either satisfied or explicitly unresolved with its next prerequisite.

## Optional operational tools

Dashboard registration is not part of this procedure or a readiness gate.
Use it only when explicitly requested and its operation has been verified.
Existing command help is available through `skill_eval.py dashboard --help`.
Its availability does not prove that the dashboard works.
