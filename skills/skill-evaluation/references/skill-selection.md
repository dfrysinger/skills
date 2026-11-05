# Skill selection and description optimization

Use this workflow when a skill is missed, activates unnecessarily, or overlaps
with another skill. Selection asks which skill the agent chooses. Execution
asks what it does after loading. End-to-end testing checks both on ordinary
work. Keep these claims separate.

Reuse the existing evaluator's isolation, records and accounting. This
procedure does not add a runner or establish that a selection runtime is ready.

## 1. Define the selection cases

Use ordinary requests without naming the desired skill or telling the agent
which skill to load. Keep expected choices hidden. Cover relevant requests,
irrelevant requests, near misses with similar wording, overlapping skills and
realistic combinations of tasks.

Label cases before seeing scores:

| Expectation | Interpretation |
| --- | --- |
| Required | The target should be selected under its declared scope and normal invocation policy. |
| Avoid | The target is inappropriate for this request, even if some vocabulary matches. |
| Optional | Either choice is acceptable; report separately rather than turning a reasonable choice into an error. |

For multi-skill tasks, state acceptable combinations; several skills may be
appropriate. Preserve originating-incident groups and the development,
selection and unused-confirmation roles from the
[playbook](evaluation-playbook.md#3-assign-historical-cases-a-role).

Complete when cases have frozen requests, hidden expectations and a declared
observation boundary long enough to reach the relevant selection decision.

## 2. Freeze the description-only comparison

Keep the unchanged description as control. Change only the target description;
hold its name, body, reached references, helpers, model, tools, normal
background instructions and surrounding skill collection fixed. Record the
descriptions actually exposed to the candidate, including competing skills.
An isolated target-only test cannot establish collection-level routing.

The description must accurately describe supported behavior. Fixing body
content or collection membership is a different comparison, not a
description-only gain. Explicit user invocation and a parent skill's directed
invocation are separate cases, not proof the child description was discovered.

Complete when both candidate identities and the effective selection context
are recorded, with only the intended description difference.

## 3. Admit an unforced-selection runtime

Before evaluating description candidates, prove that the selected Actions runtime:

- exposes the intended descriptions and normal selection instructions;
- lets a fresh candidate choose under normal policy, without test-specific
  requirements or bans on the target;
- records actual attempted invocations and successful loads separately; and
- retains completed no-invocation outcomes as valid selection evidence.

The standard prose route requires the entry skill to load in its initial
phase; a miss becomes a run error. It therefore does not meet this contract
unchanged. Its parser's ability to accept unrequired loading in resumed phases
does not establish fresh discovery. Standard modes also disable custom
instructions and built-in MCPs; restore relevant context through a supported
route or label the tested context as adapted.

Reuse a supported selection route when available. Otherwise identify the
smallest scoped evaluator change and prove it before dispatch. Preserve normal
permissions; a description workflow does not authorize broader access. Until
admission is proven, retain the cases and report the runtime prerequisite,
not an activation score or a new runner.

Complete when receipts demonstrate both invocation and valid non-invocation
through the intended fresh-session path with the recorded context.

## 4. Measure choices, not promises

Use tool records, not answers about which skill the agent would use. Distinguish:

- a missed required selection;
- an unnecessary selection on an avoid case;
- an appropriate selection;
- a selected skill that failed to load; and
- incomplete or unavailable observation.

Judge the choice from the attempted invocation. A denied load is not
automatically a missed selection; an inappropriate attempt still counts even
if loading fails. Retain the successful-load outcome separately. Separate
direct choices from explicit user or parent-directed calls.

Report miss and unnecessary-selection rates with their own denominators,
planned repetitions, valid/incomplete counts and total cost. A combined
accuracy score can hide frequent misses or overuse. A completed answer without
invocation is evidence; a timeout before the selection opportunity is not a
confident negative.

Complete when each observed choice has its case expectation, invocation
evidence, loading result and interpretation, with unknown outcomes preserved.

## 5. Optimize and confirm

Inspect development failures, propose a small description change and compare
it with the unchanged control. Use parallel alternatives only when distinct
hypotheses warrant them. Keep the body fixed and follow the playbook's staged
allocation, planned repetitions and stopping rules.

Choose a candidate using selection evidence, freeze it, then use fresh requests
for independent confirmation. A repeatedly consulted set is selection data,
regardless of its name. Anthropic's
[description optimizer](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/run_loop.py)
selects its winning iteration using its nominal test score; that partition is
not untouched final confirmation under this contract.

On the frozen description, run representative end-to-end tasks, including
nearby tasks that should remain unaffected. Correct activation alone does not
prove useful execution. Retain first outcomes, regressions, cost and uncertainty;
small samples establish only the measured scope.

Complete when the report supports keep, reject or inconclusive under the
predeclared selection and preservation rules. Separate a description-selection
gain, body effectiveness and end-to-end success. Preserve existing review,
release and installation gates.
