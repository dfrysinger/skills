---
name: prompt-engineering
description: Engineer prompts through measured technique selection rather than prompt folklore. Use when drafting or revising a prompt, system instruction, agent rubric, evaluator prompt, or skill; diagnosing prompt sensitivity or repeated model failures; or choosing among examples, decomposition, retrieval, verification, ensembling, and answer-format constraints.
---

# prompt-engineering

Treat a prompt as an **experiment**, not a program. Start with the smallest
prompt that expresses the real task, then add one technique only when an
observed failure justifies it.

## Procedure

1. **Define the behavior contract.**
   Record:
   - the user-visible task and supported inputs;
   - the desired output, including its shape and allowed answer space;
   - facts, tools, authority, and context the model may use;
   - material failure modes and their relative cost; and
   - the examples or checks that will distinguish success from plausible prose.

   For domain-sensitive work, confirm the contract with the domain owner before
   optimizing wording. A benchmark proxy does not replace the real outcome.

   **Complete when:** every scored behavior maps to an observable input/output,
   tool action, or retained artifact, and the metric rewards the intended
   outcome rather than an easy proxy.

2. **Establish the control.**
   For a new prompt, draft the smallest baseline containing:
   - one direct task statement;
   - only relevant background;
   - explicit input boundaries;
   - the required output contract; and
   - a supported uncertainty or escalation path when the task can be
     under-specified.

   Keep instructions separate from untrusted input. Use deterministic parsing,
   schemas, permissions, and application checks for guarantees the model cannot
   enforce.

   For a revision, preserve the existing prompt unchanged as the primary
   control and score it first. A simplified prompt is a separate candidate, not
   a replacement control.

   If the target model, representative cases, or execution authority is
   unavailable, produce the control or draft plus an evaluation plan, label it
   `UNTESTED`, and continue to step 5 without claiming measured improvement.

   **Complete when:** the unchanged existing prompt or new plain baseline is
   identified as the control and can be scored without manually guessing what
   its output meant, or the unavailable execution prerequisites are recorded
   for the `UNTESTED` branch.

3. **Diagnose the earliest failure.**
   Run the baseline on representative cases. Classify the first wrong decision:
   task ambiguity, missing knowledge, poor exemplar coverage, compositional
   difficulty, tool-selection failure, output-shape failure, variance,
   unsupported confidence, or instruction/data confusion.

   Read [`references/technique-selection.md`](references/technique-selection.md)
   when selecting a response to that failure.

   If the control meets the behavior contract, retain it, complete step 5, and
   then continue to step 7 without adding a technique.

   **Complete when:** either the control pass is recorded, or one observed
   failure class and one minimal intervention are named. If evidence does not
   distinguish interventions, keep them as separate experimental variants.

4. **Apply one justified technique.**
   Change one mechanism at a time. Preserve the baseline as the control.
   Examples must be representative, correctly labeled, balanced across
   important outcomes, and free of private or answer-leaking material.

   Prefer checkable intermediate artifacts over requests for private hidden
   reasoning. A rationale, plan, citation, calculation, tool result, or
   verification checklist is useful only when the evaluator can inspect it or
   it improves the final behavior.

   **Complete when:** the candidate differs from the control by one attributable
   technique and every added token has a task or failure-class purpose.

5. **Engineer the answer with the prompt.**
   Define the answer shape, answer space, and extractor together. Use native
   structured output or deterministic validation when available. Treat a
   separate model-based extractor or judge as another stochastic component with
   its own evaluation.

   **Complete when:** valid outputs are machine-checkable where the consumer
   requires structure, and malformed or unsupported outputs fail explicitly.
   A passing control or `UNTESTED` draft continues to step 7; a changed
   candidate continues to step 6.

6. **Measure sensitivity and movement.**
   Hold the model, settings, tools, data, and scoring fixed. Compare the
   baseline and candidate on frozen representative cases. Include meaningful
   edge cases and at least one harmless wording, formatting, or ordering
   perturbation when sensitivity would matter in production.

   Record first results, regressions, cost, latency, and model/config identity.
   Do not promote a technique because it is fashionable, produces a persuasive
   explanation, or wins one cherry-picked example.

   **Complete when:** the candidate improves the declared outcome without an
   equal or worse material regression, or the experiment records that it did
   not.

7. **Package the supported result.**
   For a measured run, keep the simplest prompt that meets the contract. Remove
   failed experiments, duplicated context, accidental artifacts, unsupported
   personas, and instructions that do not change behavior.

   For the `UNTESTED` branch, return a draft and runnable evaluation plan. Keep
   the hypothesis label attached; do not describe the draft as improved,
   validated, or ready for unattended promotion.

   When the artifact is a skill, apply `writing-great-skills` to invocation,
   information hierarchy, completion criteria, and pruning. Use
   `skill-evaluation` when the behavioral claim warrants frozen model-based
   evidence.

   **Complete when:** a measured artifact contains only behavior supported by
   retained evaluation, or an untested draft is paired with its missing
   prerequisites and evaluation plan. In both branches, source, model boundary,
   and known limits are stated honestly.

## Boundaries

- Prompt instructions can mitigate prompt injection; they are not a security
  boundary. Enforce authority, data access, tool permissions, and output
  validation outside the model.
- Self-critique and model-graded evaluation can improve outputs, but agreement
  with oneself is not independent verification.
- More examples, longer prompts, explicit reasoning, and more model calls can
  each reduce quality. Their cost is justified only by measured movement.
- A technique validated on one model, dataset, or task does not automatically
  transfer to another.

## Finish

Return the behavior contract, control, selected technique and rationale when
one was needed, resulting prompt, evaluation plan, and measured result or
`UNTESTED` status.
