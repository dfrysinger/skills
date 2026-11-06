# Skill evaluation findings

Lead with the user's question and the supported answer. Use ordinary language
for the decision; put run IDs, file hashes and workflow details afterward.
Use this format for unchanged evaluations as well as skill-change experiments.

## 1. Bottom line

State what was observed and what it establishes. Choose the supported claim:

- **Observed success:** this setup produced the expected result.
- **Measured improvement:** a matched comparison improved the declared outcome.
- **No measured advantage:** the comparison found no supported improvement.
- **Failure not reproduced:** the valid baseline did not exhibit the reported
  problem; its repair remains unproven.
- **Inconclusive or blocked:** name the missing observation or prerequisite.

Qualification and release are separate delivery states. A judge's HIGH
confidence is confidence in that assessment, not an estimate of reliability.

## 2. What question and behavior were tested?

Describe the original user-visible problem and the exact behavior under test.
Name the trigger and starting state. State whether the agent was expected to
prevent a mistake, recover without correction, or respond to user steering.
Explain whether it proposed actions or performed them, whether target loading
was original or added, and how long the observation lasted.

If the test is narrower than the user's original goal, name the unresolved
goal here rather than only in a technical appendix.

## 3. What changed and what was compared?

Explain the general instruction change, or say no skill change was made.
Identify exact skill/setup versions in supporting evidence.

| Condition | Run or NOT RUN | Valid results | What it can establish |
|---|---|---|---|
| Unchanged setup | | | Baseline behavior |
| Proposed revision | | | Difference from the unchanged setup |
| Target skill removed, other skills retained | | | Target contribution within that collection |
| All skills removed | | | Collection advantage over no skills |

Use the controls required by the claim; this table does not require every arm
for every evaluation. Mark missing comparisons **NOT RUN**. An old historical
failure with a different model, task or runtime is not a matched baseline.
Never infer skill benefit from the current-setup row alone.

## 4. What actually happened?

Give each condition's requested, launched, valid completed and judged attempts.
Report first-attempt outcomes separately from retry-assisted success.
Preserve setup errors, boundary violations, changed-input attempts and
disagreements rather than replacing them with later passes.

For repair, state whether the baseline reproduced the target failure and
whether the changed arm removed or reduced it under matched conditions.
Separate instruction use from actual product movement. For selection, report
attempted invocation, successful loading and task outcome separately.
One passing invocation is not a production activation rate.

State preserved behavior and maintained/unused-case coverage. Known
development feedback is not independent confirmation.

## 5. What can we conclude and what happens next?

Connect the result to the original question. Name untested claims and exact
missing prerequisites. A successful response proposal does not close an
unexecuted recovery requirement. A small fixed pass rule does not establish
reliability or transfer.

State the decision: retain, revise, reject, qualify, or continue diagnosis.
Name the smallest next comparison only when needed. Report observed usage,
elapsed coverage and known cost; keep incomplete totals unknown.
State whether source is a draft, reviewed, published, released or installed.

## Supporting evidence

Keep exact case, skill, model, tools, runtime, trigger, criteria, attempt and
retention identities available without making them the main explanation.
Measure size on the exact baseline and candidate using the same method:

| Artifact | Bytes before | Bytes after | Delta | Lines before | Lines after | Delta |
|---|---:|---:|---:|---:|---:|---:|

Separate skill instructions/references, evaluator code, frozen cases and run
artifacts. Size alone proves neither simpler behavior nor improved results.
For a small evaluation, use a short answer and a compact comparison table;
omit only inapplicable detail, not missing controls or important uncertainty.
