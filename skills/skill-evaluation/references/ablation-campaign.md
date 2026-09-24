# Skill ablation campaign

Use ablation when a skill has accumulated enough procedure that it may be
diluting its own load-bearing rules. The goal is not the fewest lines. The goal
is the smallest instruction set that produces the required behavior across a
representative frozen corpus.

## 1. Freeze the behavioral claims

Build or select cases that distinguish:

- behavior the model supplies without skill guidance;
- rules the skill must teach explicitly;
- unsafe or incorrect overcorrections;
- excessive process, scope, or proof work;
- premature completion; and
- execution variance.

Include at least one discriminating case where the full skill is suspected of
encouraging the wrong behavior. Bind every case to exact evidence and hidden
criteria before changing the skill.

Complete when the same immutable cases can run against every experiment arm.

## 2. Establish three arms

Run:

1. **Neutral**: a minimal instruction stating the outcome and basic honesty
   requirement, with no target-skill procedure.
2. **Lean**: a new skill written from first principles around the smallest
   load-bearing rules.
3. **Full**: the unchanged skill under evaluation.

Do not create the lean arm by deleting paragraphs from the full arm in place.
That preserves its information hierarchy and sediment. Start from the
behavioral claims, choose a few leading words, write only the steps every run
needs, and route specialized branches through progressive disclosure or their
own skills.

Complete when all three arms are byte-identified and differ only in their skill
instructions.

## 3. Test the discriminating case first

Run the neutral, lean, and full arms against the case most likely to reveal the
suspected dilution or over-process failure.

Interpret the comparison:

- neutral fails, lean passes: explicit guidance is necessary and the compact
  rules may be sufficient;
- neutral and lean fail: the lean arm is missing a load-bearing rule;
- lean and full both pass: use the full corpus to test whether the extra text
  adds value elsewhere;
- lean passes, full fails: competing instructions or process volume are likely
  diluting the required behavior;
- all pass: the case does not distinguish the arms.

Use the same models, limits, environment, evidence, and judge contract.

Complete when the experiment identifies whether the lean hypothesis deserves a
full-corpus run.

## 4. Grow from corpus failures

Run the lean arm against the complete valid corpus. Classify every failure
before editing:

- **missing general rule**: the lean arm omits a reusable step;
- **execution variance**: the rule exists but one run missed it;
- **packet defect**: the candidate lacked decisive authority;
- **harness defect**: the behavior was not executed or judged as specified;
- **reference coupling**: the grader requires an implementation shape that the
  claim did not require.

When the failure proves exactly one compact general rule is missing and no
competing remedy remains, add that rule and rerun the failed subset, then the
complete corpus. When multiple credible rules, rewordings, or structures could
close the failure, follow
[`parallel-treatment-search.md`](parallel-treatment-search.md): keep the lean
arm as a control and compare the alternatives in a frozen matrix.

Do not:

- copy case terminology into the skill;
- restore old machinery because deletion feels risky;
- duplicate an existing rule after one stochastic miss;
- weaken a case to make the lean arm pass; or
- count invalid packet or harness failures as skill evidence.

Complete when every retained sentence either carries a common step, routes a
real branch, or prevents a demonstrated corpus regression.

## 5. Bound stochastic retries

Use identical-byte retries only after checking that the missed behavior is
already explicit in the lean arm. Preserve every attempt. A retry-assisted pass
is evidence that the rule can work, not that behavior is deterministic.

If the same failure repeats under the bounded retry policy, treat it as a
missing or ineffective rule and generate source-backed correction hypotheses.
Apply one serially only when the evidence requires that correction and no
competitor remains; otherwise compare the hypotheses through parallel treatment
search. If different cases miss different already-explicit rules without a
stable pattern, do not respond by restating the whole skill.

Complete when each failure is labeled rule gap or variance from retained
evidence rather than intuition.

## 6. Publish only the exact gate candidate

Before replacing the installed skill:

1. freeze the lean candidate;
2. run the complete maintained corpus;
3. retain all attempts and aggregate judgments;
4. verify no older frozen case digest changed;
5. run repository validation; and
6. compare final size, runtime, pass rate, retry dependence, and output clarity
   with the neutral and full arms.

Delete obsolete inline procedure and references when the lean replacement has
absorbed their demonstrated value. Keeping unused documentation beside the lean
skill recreates the same maintenance ambiguity.

Complete when the published bytes are the bytes that passed the full gate and
the report states whether the result was deterministic or retry-assisted.
