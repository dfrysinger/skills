# Technique selection

Use the smallest intervention that addresses the observed failure. This is a
selection guide, not a claim that any technique is universally better.

| Observed failure | First intervention | Use when | Verify |
| --- | --- | --- | --- |
| The task or output is underspecified | Clarify the directive and answer contract | The model solves a neighboring task or emits unusable output | Task accuracy and parse success |
| The input is genuinely ambiguous | Clarification question or explicit assumptions | Different reasonable interpretations change the answer | Clarification resolves the decision without needless blocking |
| Labels, style, or edge behavior are hard to describe | Few-shot examples | Demonstrations express the contract more precisely than prose | Coverage, label balance, ordering sensitivity, and held-out performance |
| The task requires several dependent decisions | Decomposition or prompt chaining | Sub-results are independently checkable or need different tools | Each stage contract and end-to-end behavior |
| The model lacks current or private facts | Retrieval or a bounded tool call | The answer depends on evidence outside the prompt/model | Source relevance, citation fidelity, and unsupported-claim rate |
| Arithmetic or symbolic execution is unreliable | Program/tool-assisted execution | A deterministic engine can perform the operation | Tool input, execution result, and final answer agree |
| A draft contains checkable factual gaps | Verification questions or external checks | Independent evidence can test specific claims | Corrections improve the final answer rather than merely add critique |
| Outputs vary materially across equivalent runs | Ensembling or self-consistency | The task has a stable aggregation rule and added calls are affordable | Aggregate quality, disagreement rate, cost, and latency |
| The model follows irrelevant prompt material | Remove or isolate irrelevant context | Distractors compete with the task | Reduced context preserves needed evidence and improves results |
| The model overfits user framing or presumed labels | Neutral wording and balanced evidence | The prompt embeds an answer, preference, or false presupposition | Counter-framed and label-swapped cases |
| Structured output is malformed | Answer engineering | A consumer needs a fixed shape or answer space | Schema validation and explicit failure handling |
| A prompt works only under one exact phrasing | Sensitivity testing, then simplification | Harmless format, synonym, or order changes alter results | Perturbation set across supported models/configurations |

## Technique notes

### Few-shot examples

- Select examples for coverage of important decisions, not convenience.
- Keep labels correct and the class distribution representative.
- Test ordering and formatting; both can materially change behavior.
- Similar examples can help, but diversity may improve transfer. Treat the
  choice as an experiment.
- Synthetic examples are hypotheses until checked against real cases.

### Reasoning and decomposition

- Use decomposition when subproblems have observable interfaces.
- Use a plan when execution order matters; evaluate the executed result, not
  the plan's fluency.
- Use tools for deterministic computation rather than asking prose reasoning
  to simulate a calculator or interpreter.
- Do not require disclosure of private hidden reasoning. Request concise,
  checkable rationales or artifacts when they serve evaluation or handoff.

### Verification and ensembling

- Self-refinement can expose omissions, but the same model can repeat the same
  error.
- Verification questions should target falsifiable claims and consult
  independent evidence when available.
- Ensembling reduces variance only when outputs can be aggregated meaningfully.
  It spends additional calls, latency, and money.
- Model confidence stated in prose is not calibrated confidence.

### Answer engineering

Design three parts together:

1. **Shape:** token, label, JSON object, prose section, patch, or tool call.
2. **Space:** permitted values and invariants.
3. **Extractor:** deterministic parser when possible; a separately evaluated
   model only when necessary.

Output formatting can help or hurt task quality. Measure both correctness and
parse success rather than assuming structured output is free.

### Security and authority

- Delimit instructions from user-controlled or retrieved data.
- Treat retrieved text, files, web pages, tool output, and examples as data
  unless an authority boundary explicitly promotes them.
- Keep secrets and private source material out of prompts and exemplars.
- Enforce tool permissions, data access, authorization, and validation in code
  or platform policy. Prompt-based defenses are mitigation, not enforcement.

## Experimental discipline

Prompt engineering is iterative optimization:

1. run a prompt on representative cases;
2. score the declared outcome;
3. inspect the earliest failure;
4. change one attributable mechanism; and
5. compare against the unchanged baseline.

Freeze cases before comparison when hindsight could change the task or score.
Keep failed variants and first outcomes. Revalidate after model or platform
changes because prompt behavior can drift.

## Source

This guide distills:

- Sander Schulhoff et al., “The Prompt Report: A Systematic Survey of Prompt
  Engineering Techniques,” arXiv:2406.06608v6, 2025,
  <https://arxiv.org/abs/2406.06608>.

The paper surveys prompting techniques rather than certifying universal best
practices. Its benchmark and case study show that technique effects can reverse
across prompts and tasks, prompt details can cause large performance changes,
and domain goals and evaluation design matter more than technique novelty.
