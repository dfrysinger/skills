# Release qualification and generalization

Use this branch when the intended conclusion is stronger than “the skill arm
passed this case.” It qualifies three claims:

- the exact released skill helps compared with no target skill;
- an improvement transfers beyond the task that produced it; or
- the packaged skill, references, and scripts remain general rather than
  encoding one accepted implementation.

Ordinary iteration continues to compare a draft with the published skill. A
no-skill arm is an attribution control, not the default parent for every hill
climb.

## 1. Name the claim before running

Choose the narrowest claim the campaign needs:

| Claim | Required evidence |
|---|---|
| **Case pass** | One identified skill revision passes one frozen case. |
| **Skill improvement** | The candidate moves the product frontier beyond the unchanged published skill under the same contract. |
| **No-skill advantage** | The exact release outperforms a matched arm that receives the same task and candidate-visible context without the target skill. |
| **Transfer** | The applicable improvement succeeds on a frozen task that did not guide its mechanism, wording, or selection. |
| **Qualified release** | The reviewed, packaged, published, and installed bytes correspond and pass their maintained regression and applicable transfer gates. |

Do not use one claim as shorthand for another. A case pass does not prove
advantage, improvement over the prior skill does not prove advantage over no
skill, and deterministic script tests do not prove that agents use the script
well.

Freeze the selected candidate and confirmation inputs before observing their
reportable results. Keep the success rule fixed. Feedback-driven changes to
the candidate, selection, or success rule return that evidence to development;
identify a new confirmation rather than continuing until the old set passes.
This does not require a new service or an independently administered dataset.

Complete when the reportable claim, cases, controls, repetitions, success rule,
and allowed scope are fixed before candidate execution.

## 2. Freeze the released artifact and controls

Evaluate the complete distributable artifact:

- target `SKILL.md`;
- every reached reference and script;
- package metadata that controls discovery or invocation;
- file modes and directory membership; and
- any adapter or wrapper loaded by the supported installation path.

Bind reviewed, packaged, published, installed, and evaluated identities. A
source-tree match is insufficient when installation changes membership,
permissions, paths, or versions.

For a no-skill comparison, keep model, effort, task, evidence, repository,
tools, timeout, harness, and candidate-visible instructions identical except
for the target skill. Remove only that skill from the candidate-visible
environment. When its plugin bundles other skills, preserve their exact bytes,
registration, and visibility rather than removing the whole plugin. Record
other visible skills and instructions so a shared behavior is not
misattributed to the target skill.

The repository-task evaluator's legacy `--arm baseline` omits the whole plugin.
Use that arm for this claim only when the plugin is the standalone target
artifact. For a multi-skill plugin, use a harness that preserves the non-target
inventory or report no-skill advantage as unknown.

For a bundled tool, ask for the user-visible outcome rather than commanding the
candidate to invoke the tool. Grade the resulting decisions and artifacts.
Separately retain deterministic tests for the tool itself.

Complete when each arm differs only by its declared intervention and every
attempt receipt names the exact artifact identity.

## 3. Build a generalization set

Keep the source task as regression evidence. It cannot become held-out again
after influencing skill wording, treatment selection, or removal decisions.

Hidden criteria and aggregate-only results protect content, not independence
from tuning. Aggregate feedback can still influence the next candidate.
Record that use in the existing plan/report, reserve unused transfer cases
when available, and narrow the claim when fresh confirmation is unavailable.

Add frozen tasks that exercise the generalized behavior through different
surface details. Include, where applicable:

- alternate repository layouts, names, versions, and serialization forms;
- different data shapes or implementation mechanisms;
- an **abstention** case where the learned tactic does not apply;
- one valid unusual configuration and one genuinely invalid configuration for
  a bundled checker;
- an offline case that assigns live facts to operator handoff rather than
  candidate invention; and
- a task whose success can be judged without source-task vocabulary.

Hidden criteria judge behavior, not use of source-task terms or reproduction of
one reference patch. Apply the judgment environment-fit ledger before freezing
each material case.

Complete when development, regression, and genuinely unexposed transfer cases
are labeled separately and every hard criterion is observable in its assigned
environment.

## 4. Run a cost-aware matched campaign

Use the cheapest valid sequence:

1. run a non-reportable canary to prove packet, grader, and harness delivery;
2. run one matched baseline/skill pair to expose contract defects;
3. repair only packet, harness, or grading defects;
4. freeze the reportable contract and predeclare repetitions; and
5. run the exact arms and preserve every original outcome.

The canary and setup pair validate execution; they do not count toward the
reported advantage. Choose local execution for an ordinary bounded corpus.
Use the large Actions campaign only when repositories, native builds,
treatments, or repetitions make one host the measured bottleneck.

Measure pass distribution, pass-at-first-attempt, earliest failure frontier,
instruction uptake, wall time, AI credits, and judge agreement. A cheaper skill
that preserves behavior and a more expensive skill that materially improves it
are different product outcomes; report both.

Complete when one checksum-bound result exists for every predeclared attempt
and no failed or inconvenient outcome has been replaced or discarded.

## 5. Run the overfitting review

After product evidence exists and before promotion, run `dual-review` against
the complete distributable artifact. Give both reviewer families the same
packet:

- source task and accepted-outcome authority;
- held-out cases and environment-fit ledgers;
- exact artifact diff and file inventory;
- claimed scope and non-goals;
- deterministic tool tests and behavioral results; and
- complete candidate-visible instruction-stack attribution.

The reviewers inspect for material task leakage:

- source-task names, dates, constants, paths, identities, schemas, or worker
  shapes presented as universal;
- one repository layout, runtime version, serialization style, or accepted
  mechanism turned into an admission rule;
- live infrastructure facts assigned to an offline candidate;
- a tactic stated unconditionally when supported workloads need an
  applicability test;
- authorization or ownership copied from the development environment;
- hidden-criterion wording or answer-shaped examples in candidate-visible
  content; and
- scripts whose formatting assumptions or defaults accept the source fixture
  while rejecting supported alternatives.

Resemblance alone is not a finding. Require a concrete supported task that
reaches the leaked assumption and a material consequence. Fix verified
must-fix findings, rerun affected deterministic and behavioral cases, then use
the bounded dual-review closure round.

Complete when both families finish, every material finding has evidence and
causality, and no `must-fix` overfitting finding remains.

## 6. Interpret and publish

Use the main skill’s instruction-uptake and product-movement classifications.
Then apply the selected claim gate:

- **No-skill advantage:** the exact release improves the predeclared matched
  population without an equal or earlier regression.
- **Transfer:** the improvement succeeds on independently reserved cases and
  the applicable new rule is observed.
- **Qualified release:** exact released and installed bytes pass the maintained
  suite, applicable transfer cases, applicable outcome-led bundled-tool cases,
  deterministic tool checks, and overfitting review.

Report ties and narrow wins honestly. “No signal” on the source task can coexist
with strict improvement on an independently held-out failure class. That
supports the held-out claim, not universal superiority.

Complete when the report states case pass, skill improvement, no-skill
advantage, transfer, and release qualification separately, marking unsupported
claims as unknown rather than collapsing them into one success label.
