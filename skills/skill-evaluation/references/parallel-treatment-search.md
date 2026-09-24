# Parallel treatment search

Use a parallel treatment search whenever a valid evaluator exists and more than
one credible mechanism could improve stochastic skill behavior. Do not wait for
serial revisions to plateau. The goal is not to generate many rewrites. It is
to compare a small population of independently motivated mechanisms under one
frozen evaluation contract.

Serial work is appropriate only when:

- the evaluator, packet, or harness is invalid and has one evidenced repair;
- read-only diagnosis is still establishing the behavioral claim or failure
  classes;
- one correction is independently required and no competing treatment remains;
  or
- capacity forces sequential scheduling of a matrix that was still designed
  and frozen before its first treatment ran.

Physical execution order does not change the experimental design. A
pre-registered matrix run one job at a time is still a parallel treatment
search; choosing each next treatment after reading the previous outcome is
serial hill climbing.

Diagnostic serial work may observe, classify, and build or repair the evaluator.
It must not edit skill treatments. Diagnosis ends when the behavioral claim and
failure classes are named; any candidate skill change suggested during
diagnosis enters the frozen matrix as a hypothesis arm.

## 1. Freeze the measurement contract

Before generating treatments, freeze:

- development cases and hidden criteria;
- unchanged regression cases;
- model, harness, tools, limits, timeout, platform, and source revision;
- deterministic graders and judge contract;
- first-outcome and infrastructure-recovery rules; and
- the metrics used to rank treatments.

Name the recurring product failures separately from the aggregate score. For
example, record state conflation, lost exit behavior, excessive scope, or
helper-only proof as binary observations per run. A total score says which arm
won; mechanism observations explain why.

Complete when every treatment will receive the same evaluator inputs and the
selection rule can be applied without reading treatment names.

## 2. Generate hypotheses from several sources

Search the target skill, adjacent internal skills, installed third-party
skills, public skill collections, prompt-optimization literature, and proven
repository practices using the generalized failure class rather than case
vocabulary. Useful search classes include:

- state or outcome enumeration;
- branch and exit preservation;
- production-owner or integration testing;
- red-first development;
- edit locality;
- counterexample or adversarial checks; and
- preservation tests around a changed boundary.

Use two or more independent sources when available. For every borrowed idea,
record:

- source and license;
- the exact tactic or invariant that motivated the arm;
- the generalized failure it is intended to prevent;
- what was deliberately omitted; and
- whether multiple sources independently support the same tactic.

Treat sources as hypothesis generators, not authority. Extract the smallest
general mechanism in original wording. Do not copy an entire skill, import its
unrelated process, or expose source descriptions to candidates unless that
complete skill is itself the treatment. Reject tactics that require
case-specific names, files, expected implementations, or hidden checks.

Complete when each candidate arm has a source-backed, falsifiable behavioral
hypothesis and no arm exists only because its prose sounded promising.

## 3. Build a diagnostic field

Start with controls that answer different questions:

1. **No skill:** what the model and task produce without the target procedure.
2. **Unchanged full skill:** whether the existing skill helps or harms.
3. **Lean or minimal control:** whether instruction volume or process sediment
   is the problem.
4. **Dose-matched placebo:** whether merely adding a compact, structured skill
   changes behavior.

Add single-mechanism arms. Give them the same information hierarchy, step
count, tone, and approximate instruction length. Change only the tactic under
test. Keep composite arms separate and label them confounded; use them to test
synergy, not to attribute causality.

Prefer fewer credible arms with planned repetitions over many one-shot
rewrites. A repeated trial is not a retry: its identity and budget are declared
before dispatch, and every outcome is retained. When expected treatment
differences are close to normal run-to-run variance, use at least three
repetitions per arm or reduce the arm count until replication fits the budget.

Complete when every arm has one treatment identity, one hypothesis, planned
repetitions, and a clear comparison control.

## 4. Freeze and run the matrix

Assign a stable attempt ID to every treatment, repetition, case, model, and
platform combination. Randomize or run treatments concurrently so changing
service load and model rollout timing do not systematically favor one arm.
Hold every non-treatment input fixed.

For product-heavy or native experiments, use
[`large-actions-campaign.md`](large-actions-campaign.md). Seal one immutable
campaign, dispatch the full admitted matrix with bounded concurrency, preserve
the first launched model outcome, and recover only invalid downstream stages.
Never stop weak-looking arms early based on partial results unless the campaign
declared a staged allocation rule before dispatch.

Complete when all admitted attempts were requested exactly once and every
effective result can be reconciled to its frozen identity.

## 5. Select by distribution and mechanism

Compare treatments on:

- deterministic target and regression outcomes;
- product-movement classification and earliest failure frontier;
- mechanism-specific failure recurrence;
- instruction uptake;
- judge agreement;
- runtime, tokens, and available cost proxies; and
- variation across repetitions.

Do not select the best single run. Eliminate arms that fail to beat their
control distribution, introduce an equal or earlier regression, or show no
uptake of their distinguishing tactic. Use successive halving only as a
pre-registered allocation rule: run the broad field, retain all outcomes,
then spend additional repetitions or cases on the strongest one or two arms.

Complete when finalist selection can be regenerated from the effective-result
map and the declared ranking rule.

## 6. Validate transfer before promotion

Development cases may select finalists; they must not establish
generalization. Run the top treatments and their relevant controls on held-out
cases that exercise the same generalized failure class through different
vocabulary, repository shapes, and surface forms. Also run unrelated maintained
cases as non-inferiority checks for collateral harm. Testing controls on
transfer distinguishes a real treatment effect from a generally easier or
harder case.

Promote only the exact treatment bytes that:

- improve the development distribution rather than one lucky attempt;
- preserve maintained regressions;
- beat the applicable control on held-out transfer;
- retain the intended mechanism uptake; and
- pass the complete release gate.

Complete when the winner's development, replication, transfer, and regression
evidence all bind to the same frozen treatment identity.

## 7. Report the search

Report:

- source and tactic provenance for every arm;
- controls, hypotheses, treatment identities, and planned repetitions;
- complete first outcomes, including failed and timed-out attempts;
- aggregate scores and mechanism-specific observations;
- selection and elimination rules;
- finalist replication and held-out transfer;
- runtime and cost; and
- uncertainty from sample size, model variance, or invalid observations.

The durable result is the experimental evidence and reusable tactic, not the
history of how many prompt drafts were tried.
