# Judgment environment fit

Use this procedure before freezing a material evaluation and whenever a result
looks wrong because the candidate could not observe or exercise what the judge
required.

The **observability boundary** is the line between evidence the candidate can
produce in its declared environment and facts that only a later operator,
service, deployment, or production run can establish. A frozen case tests the
former and the quality of the handoff to the latter.

A **material case** is one whose verdict can justify a skill edit, release
decision, or expensive treatment search, or whose criteria cross a handoff,
live-service, infrastructure, authentication, or production boundary.

## 1. Freeze the methodology before the answer

Record:

- the supported caller and user-visible outcome;
- the candidate's available source, tools, credentials, network, compute, and
  runtime;
- unavailable operations such as attended login, cloud capacity queries,
  deployment, production traffic, or long-running workloads;
- what a successful candidate produces locally; and
- what a later operator or qualification stage must still observe.

Do this before reading the accepted implementation as a design to copy. An
accepted patch proves one viable answer. It is behavioral authority only for
outcomes independently supported by the user, platform, policy, compatibility
promise, or observed failure.

Complete when a stranger can tell what the candidate can prove, what it can
only prepare, and what is outside this evaluation.

## 2. Build the criteria ledger

Give every hard criterion one row:

| Field | Required content |
|---|---|
| Outcome | The user-visible behavior or preserved boundary |
| Authority | Exact user event, platform rule, policy, compatibility promise, or observed failure |
| Evidence class | `candidate`, `handoff`, or `post-environment` |
| Observable evidence | Patch, local test, receipt, response, or handoff statement that establishes it |
| Permitted equivalents | Mechanisms that satisfy the same outcome |
| Failure | Concrete supported input or state that makes the candidate wrong |

Store the frozen ledger at
`judge-reference/judgment-environment-fit.md`. Keep constraint-challenge and
review authoring receipts under `capture/criteria-review.md`; `capture/` remains
outside the candidate and judge packet unless evidence is deliberately copied
into a frozen boundary.

Use the evidence classes as follows:

- **candidate:** locally observable and eligible for behavioral pass/fail;
- **handoff:** the candidate passes by naming the unresolved fact, its owner,
  the exact operator check, and the blocked action; the fact itself is not
  required to be true in the evaluator;
- **post-environment:** measured only after deployment or in another declared
  qualification stage and excluded from this verdict.

An unavailable fact is not `UNANSWERABLE` when a complete handoff is the
intended result. `UNANSWERABLE` is for missing evidence needed to judge the
declared offline result.

Complete when every hard criterion has independent authority, an evidence
class, and a concrete failure.

## 3. Challenge mechanisms and exactness

Apply `constraint-challenge` before freezing when any hard criterion requires:

- an exact component, version, date, identifier, file path, token, topology,
  executor count, worker SKU, dashboard, or implementation structure;
- a fact outside the observability boundary;
- a mechanism copied from the accepted patch;
- a reviewer recommendation promoted to behavioral correctness; or
- additional proof machinery created because the evaluator cannot exercise the
  real environment.

Keep the independently supported outcome and remove the unsupported mechanism.
An exact value remains mandatory only when its authority requires that value,
not because the accepted patch, grader, or current implementation used it.

Use `dual-review`'s design branch after the challenge for a systemic, critical,
or multi-boundary criteria packet. Give both reviewers the methodology,
criteria ledger, candidate capability boundary, accepted result, grader
partition, and challenge decision. Review architecture and scope before grader
code. A bounded case with no exact or post-environment criterion may use one
direct criteria audit instead.

Complete when the challenge is `CONTINUE` or `NARROW`, both required review
families have no material criteria finding when dual review applies, and every
remaining mechanism is independently necessary.

## 4. Design semantic graders

Executable checks should recognize outcomes rather than one source shape:

- calculate durations instead of matching historical dates;
- accept equivalent bounded allocation modes;
- inspect parsed configuration rather than filenames;
- verify metric meaning rather than local variable names;
- find focused tests by behavior rather than titles or paths; and
- accept any maintained integration that supplies the authorized observable
  result.

Separate:

1. target behavior introduced by the task;
2. preserved regressions;
3. behavioral judgment; and
4. source-quality findings.

Reference admission proves base/reference discrimination and grader health. It
does not prove semantic completeness. Add at least one alternative valid
fixture when the criterion permits more than one mechanism; the grader must
accept it. Add one near-miss fixture for each load-bearing boundary; the grader
must reject it for the intended reason.

Complete when base, reference, alternative-valid, regression, and near-miss
controls behave as declared.

## 5. Keep quality and correctness separate

Source-quality reviewers report shipping risks; they do not silently expand
the hidden behavioral contract. Adjudicate a finding before using it as a
failure:

- verify its cited source and reachable trigger;
- map it to a hard criterion and independent authority;
- distinguish a run-blocking static defect from an operational risk that the
  handoff already owns; and
- keep unavailable runtime evidence as a requested qualification check, not a
  guessed defect.

A candidate may behaviorally pass while quality remains `needs_revision`.
Conversely, favorable quality prose cannot override a violated behavioral
boundary.

Complete when the report presents executable, behavioral, quality, and later
qualification results separately.

## 6. Repair a bad judgment contract without rewriting history

When a frozen criterion is over-specific, unobservable, or unauthorized:

1. classify it as a grading, judging, packet, or methodology defect;
2. preserve the original case revision, run, and verdict;
3. publish a corrected immutable revision with the changed authority and
   criterion ledger;
4. rerun admission, including alternative-valid and near-miss controls; and
5. regrade or rejudge the retained candidate patch under the corrected
   downstream contract when safe patch correspondence exists.

Launch a new candidate only when candidate-visible evidence, tools, model,
skill bytes, or requested behavior changed. A downstream criteria repair alone
does not justify paying for another stochastic implementation attempt.

Complete when old and corrected results are both addressable, the report names
which contract produced each verdict, and no corrected claim is backdated onto
the old receipt.
