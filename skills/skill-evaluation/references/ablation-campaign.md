# Whole-skill ablation campaign

Use this separate process when whole-skill minimization is requested or
accumulated procedure may dilute the required behavior. Rebuild from observed
needs rather than shortening each old paragraph. The goal is the smallest
tested instruction set that preserves required behavior, not the fewest lines.

For a new repair, minimize only its declared increment against the fixed parent
through the [cumulative hill climb](cumulative-skill-hill-climb.md#4-minimize-the-new-increment).
Keep earlier rules outside that change fixed. A whole rebuild is not an
incremental release prerequisite, and a neutral arm is not a replacement for
the working comparison.

## 1. Freeze the behavioral claims

Build or select cases that distinguish:

- behavior the model supplies without skill guidance;
- rules the skill must teach explicitly;
- unsafe or incorrect overcorrections;
- excessive process, scope, or proof work;
- premature completion; and
- execution variance.

Declare the maintained behaviors across the supported workload, not just the
latest mistake. When investigating harmful procedure, include the suspected
failure; simplification alone does not require the full skill to fail.
Bind cases to exact evidence and hidden criteria. Fix the model, other
instructions, tools, environment, preservation rule, repetitions and budget.
Follow the [case roles and staged search](evaluation-playbook.md#3-assign-historical-cases-a-role);
reserve confirmation evidence before search when the claim needs it.

Complete when the same immutable cases can run against every arm and the plan
identifies preserved behavior, development coverage and final qualification.

## 2. Establish three arms

Identify:

1. **Neutral**: the ordinary task with no target-skill procedure. If the runner
   requires a skill file, use a minimal valid interface stub and record what
   remains; this differs from literal absence.
2. **Lean**: begin at the neutral instruction boundary. Add no workflow rules
   until observed failures justify them through section 4.
3. **Full**: the unchanged skill under evaluation.

Retain normal permission controls, task requirements and non-target context in
every arm. Remove only the target guidance, not its entire plugin or unrelated
skills. Identify retained interface scaffolding and helper capabilities.
Inspect reached references, task documents and other instructions so the
neutral arm does not silently inherit the full procedure through another path.

Keep the full skill as the control, not the template for the lean document.
Its old sections are sources for focused repair hypotheses, not a retention
checklist. Initially neutral and lean can be identical; reuse completed
attempts only when their exact candidate and execution identities match.

Complete when the arms have exact identities, the retained scaffolding and
effective guidance are known, and all non-target conditions are held fixed.

## 3. Test the discriminating case first

Compare neutral and full on a case sensitive to the behavior under review.
Where a lean revision exists, include it under the same contract. Start with a
suspected dilution case when relevant, otherwise representative required work.

Interpret the comparison:

- neutral fails, full passes: investigate the missing behavior and the full
  trace before proposing a compact rule;
- neutral and full pass: expand coverage before adding guidance;
- neutral and full fail: diagnose the shared failure before blaming missing
  lean instructions;
- lean improves on neutral: repeat the comparison before crediting its rule;
- neutral or lean passes where full fails: investigate possible interference,
  not an assumed instruction-dilution cause.

These patterns generate hypotheses; one stochastic result does not establish
necessity or causality. Preserve the same limits, evidence and judge contract.

Complete when the retained comparison supports a specific add-back hypothesis,
wider testing without additions, or diagnosis outside the target skill.

## 4. Add back one demonstrated rule at a time

Inspect the lean arm's first wrong decision. Classify it before editing:

- **missing general rule**: the lean arm omits a reusable step;
- **instruction interaction**: another visible instruction reinforces or
  conflicts with the behavior;
- **execution variance**: the rule exists but one run missed it;
- **packet defect**: the packet misrepresents context relative to the real task;
- **harness defect**: the behavior was not executed or judged as specified;
- **reference coupling**: the grader requires an implementation shape that the
  claim did not require.

For a supported rule gap, record in the existing plan:

1. The observed failure and behavior that should replace it.
2. The general principle and relevant source section, if the full skill has it.
3. One compact behavioral statement to add.
4. The matched unchanged-lean comparison and evidence for keeping the addition.

Summarize only the needed principle from the working skill. Keep case answers
and terminology out of the rule. One independently testable mechanism is the
unit, not punctuation: when interacting steps need a small bundle, label that
hypothesis and test the interaction rather than hiding several rules in one
sentence. If the model already supplies the behavior, add nothing.

Compare the proposed add-back with the unchanged lean parent on the failure
and sensitive preservation cases. Keep it only when the planned evidence
supports improvement without an unacceptable regression. Broaden promising
candidates to representative subsets and periodically check the full
maintained suite. A small corpus may make a full run simpler; a large corpus
does not require a full run after every sentence.

Use [parallel treatment search](parallel-treatment-search.md) for competing
hypotheses from the same lean parent. Freeze controls and planned comparisons.
Retest combined additions and later removals: individually useful rules can
interact, and a later rule can make an earlier one redundant. Repair invalid
packets, harnesses and grading separately, retaining the original outcomes.

Complete when every procedural add-back has an observed gap, general rule,
matched result and keep/reject/inconclusive decision, and the next coverage
expansion or final gate is named.

## 5. Bound stochastic retries

Plan matched repetitions for every arm before execution; these differ from
retrying a failed attempt until it passes.
Use identical-byte retries only after checking that the missed behavior is
already explicit in the lean arm. Preserve every attempt. A retry-assisted pass
is evidence that the rule can work, not that behavior is deterministic.

If the same failure repeats under the bounded retry policy, investigate a
missing or ineffective rule, interaction or model limit.
Test a supported correction against the unchanged lean arm, or compare
competing hypotheses through a declared parallel treatment search when needed.
If different cases miss different already-explicit rules without a
stable pattern, do not respond by restating the whole skill.

Complete when each failure is labeled rule gap or variance from retained
evidence rather than intuition.

## 6. Publish only the exact gate candidate

Before replacing the installed skill:

1. freeze the lean candidate;
2. compare it with the unchanged full skill on the complete maintained corpus
   under the predeclared preservation rule;
3. retain all attempts and aggregate judgments;
4. verify no older frozen case digest changed;
5. run repository validation; and
6. compare final size, runtime, pass rate, retry dependence, and output clarity
   with the neutral and full arms, adding fresh confirmation for any independent
   transfer claim.

Delete obsolete inline procedure and references when the lean replacement has
absorbed their demonstrated value. Count retained references and helpers in
the delivered artifact rather than hiding its instruction cost. If the lean
candidate cannot meet preservation within the budget, keep the full skill.

Complete when the published bytes are the bytes that passed the full gate and
the report states first-attempt success, repeated outcomes and retry dependence.
Report the smallest tested candidate that preserved measured behavior, not a
global minimum. A finite set of successful runs does not establish determinism.
