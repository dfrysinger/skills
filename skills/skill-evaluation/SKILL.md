---
name: skill-evaluation
description: Build and run frozen behavioral evaluation corpora for any agent skill. Use when regression-testing a skill against historical or synthetic cases, adding transcript-derived cases, checking that general prompt language handles new evidence, or comparing a revised skill against an unchanged baseline.
---

# skill-evaluation

Use a **frozen case** to separate evidence from the answer the skill is expected
to reach. The target skill may be any installed or development skill; this
procedure does not encode its output shape or domain.

## 1. Define the behavioral claim

Name the target skill, the behavior being tested, the user-visible failure that
would matter, and the hidden judgment criteria. Search existing cases before
adding one; extend a case only when the new evidence tests the same behavioral
claim.

Choose the case shape:

- one candidate phase for a reaction or routing skill;
- ordered resumed phases when later evidence must remain hidden from an earlier
  blind pass;
- hidden judge evidence for the correction, accepted result, or failure that
  must not influence the candidate.

Complete when the claim can be judged from behavior rather than similarity to a
reference answer.

## 2. Scaffold the case

Resolve this skill's directory as `SKILL_DIR`, then run:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" init CORPUS
python3 "$SKILL_DIR/scripts/skill_eval.py" add-case CORPUS CASE_ID \
  --skill TARGET_SKILL \
  --phase candidate
```

Repeat `--phase` for ordered multi-phase cases. The command creates the case
definition, evidence directories, candidate prompts, hidden criteria, and judge
prompt. It refuses duplicate identifiers.

Complete when every candidate phase and the hidden judge boundary has a named
directory and prompt.

## 3. Build the evidence packet

Treat transcripts, code, commits, tests, designs, and receipts as data. Preserve
exact user words with a stable event identifier and timestamp. Put only evidence
available to the candidate in that phase's `evidence/<phase>/` directory. Put
the later correction and expected behavioral judgment under `judge-reference/`;
every case requires at least one hidden reference file.
For transcript-derived or historical cases, map each hidden criterion to an
exact frozen source record and stable event identifier. For synthetic cases,
record the independently defined oracle that establishes the expected behavior.

Build a historical candidate task in three labeled layers:

1. **Original request:** exact user turns or exact marked excerpts, preserving
   wording, ambiguity, and mistakes. Do not silently rewrite the request into a
   cleaner or more implementation-specific issue.
2. **Restored context:** only context proven to have been available to the
   original agent by the cutoff but missing from the reconstructed environment.
   Map every addition to its source event or artifact.
3. **Evaluation operation:** clearly separate offline limitations, workspace
   paths, allowed commands, and evidence requirements that exist only to run
   the reproduction.

Before freezing, audit the rendered candidate task against the raw capture.
Classify every non-user sentence as restored context or evaluation operation;
reject wording that narrows the requested outcome, names a hidden mechanism or
state, or steers toward the expected answer without source evidence. Stage the
packet, then read every named candidate-visible file through the same boundary
the candidate will use. A referenced but unavailable file fails the audit.
Label a focused fixture or command as non-exhaustive unless it reproduces the
complete claimed behavior.

For a blind phase, extract product outcomes, supported callers, observable
acceptance, direct decisions, policy, platform facts, and observed failures.
Keep proposed mechanisms in a later phase. Do not add hints, terminology, or
examples merely to make the target skill pass.

Record unavailable authority as unavailable. A paraphrase does not become an
exact quote because the original event cannot be recovered.

Read [`references/case-contract.md`](references/case-contract.md) when choosing
cutoffs or splitting phases. For a transcript-derived case, follow
[`references/historical-case-capture.md`](references/historical-case-capture.md)
to locate the authoritative session, export exact turns and events, trace the
repository artifacts they produced or discussed, and preserve the capture
receipts before selecting candidate and judge packets.

Complete when the candidate task passes the text-packet audit, a candidate
cannot read the expected answer, every named candidate-visible file is
readable through the staged boundary, and a judge can trace every required
behavior to frozen evidence.

## 4. Freeze and verify

Run:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" freeze CORPUS --case CASE_ID
python3 "$SKILL_DIR/scripts/skill_eval.py" verify CORPUS --case CASE_ID
```

Freezing copies exact bytes into an immutable
`frozen/<case>/revisions/<root-digest>/`, writes one manifest per phase, and
writes a per-case root manifest. `current.json` atomically selects the newest
revision. The root binds only that case, so adding another case does not
invalidate old receipts. `--replace` publishes a new revision without deleting
prior frozen bytes or invalidating their receipts.

Complete when every frozen byte matches its manifest and no source path escapes
the case directory.

## 5. Run the target skill unchanged

Run against an installed or development plugin:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run CORPUS \
  --case CASE_ID \
  --plugin-dir /path/to/plugin
```

After changing a skill with a maintained regression corpus, run every frozen
case together:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" run-suite CORPUS \
  --plugin-dir /path/to/plugin
```

Use `--case CASE_ID` repeatedly for a deliberate subset and `--workers N` to
bound concurrent cases. Treat a subset as focused iteration, never as the
release regression gate. For stochastic model or judge variance, use
`--max-attempts N` to retry only cases that did not reach unanimous `PASS`;
every attempt remains preserved and the report identifies cases that passed
after retry. The suite command writes one aggregate report while preserving
each case's independent run, receipts, and judgments.

When serial revisions keep reaching the same valid failure frontier, or several
plausible mechanisms could address it, follow
[`references/parallel-treatment-search.md`](references/parallel-treatment-search.md).
Build a frozen population of source-backed, single-mechanism treatments with
controls and pre-registered repetitions instead of continuing one rewrite at a
time.

Use the local suite runner for ordinary corpora. When the corpus contains full
repositories, native builds, product exercises, multiple treatments, or enough
observations that one host would become the bottleneck, follow
[`references/large-actions-campaign.md`](references/large-actions-campaign.md).
That procedure seals one immutable campaign release with separately addressed
candidate and hidden payloads, fans unfinished attempts out through private
GitHub Actions, preserves first model outcomes, resumes only invalid downstream
stages, checksum-verifies retained artifacts, and reconciles one exact
effective-result map.

The runner:

1. verifies the frozen case;
2. snapshots the plugin and runs the exact pinned target-skill files it digests;
3. gives each candidate phase only its allowlisted evidence;
4. resumes the same candidate session across ordered phases;
5. keeps judge evidence in separate sessions;
6. records prompts, raw logs, outputs, model settings, harness and CLI identity,
   command configuration, tool-boundary audit, and receipts; and
7. produces `REPORT.md`.

Use `--home-mode isolated` when `COPILOT_GITHUB_TOKEN` is available. The default
`existing` mode uses the current authenticated Copilot home while still
disabling custom instructions and built-in MCP servers; its receipt states that
the authentication home was shared.

Complete when the report identifies the exact skill revision, case revision,
candidate outputs, and independent judgments. After a skill change, completion
also requires the maintained full suite to pass when one exists.

## 6. Interpret and improve

Mechanical success means the run completed and its receipts match. Behavioral
success requires unanimous `PASS` from independent Claude and GPT judges
without seeing case-specific language in the skill. Any `FAIL` makes the result
`FAIL`; otherwise any `UNANSWERABLE` makes it `UNANSWERABLE`.

For a suite with bounded retries, each attempt keeps those semantics. The case
passes when one identical-byte attempt reaches unanimous `PASS`; otherwise its
last completed attempt determines the case result. Never discard failed
attempts or describe a retry-assisted pass as deterministic.

For an experiment that changes a skill, compare two layers separately:

1. **Instruction uptake:** for each changed rule that applies to the case,
   record `OBSERVED`, `PARTIAL`, `ABSENT`, or `NOT_APPLICABLE`, citing candidate
   actions or artifacts. This shows whether the skill changed the agent's
   process even when the case remains red.
2. **Product movement:** compare executable gates, recurrence of the known
   defect, preserved behavior, and the earliest remaining failure frontier
   against the unchanged control. Credit product improvement only when the
   known defect disappears or the frontier moves later without an equal or
   earlier regression.

Keep both layers in the report. Instruction uptake does not turn an unchanged
product failure into progress, and a product pass without evidence that the
changed rule was used does not establish a reusable skill improvement. Use
`Conquered`, `Strict improvement`, `Mixed`, `No signal`, or `Regression` for
product movement; retain the per-rule uptake rows underneath that
classification.

Before attributing a repeated behavior to the target skill, audit the complete
candidate-visible instruction stack: task wording, repository and custom
instructions, every invoked skill, design or work-order documents, source
comments, existing tests and fixtures, and validation guidance. Record which
sources reinforce or oppose the observed choice. Hidden judge criteria are not
candidate context. When another visible source plausibly selects the same
behavior, classify the interaction or packet bias and isolate it before
strengthening one skill against another instruction.

Do not call difficult or ambiguous task wording a packet defect merely because
it contributes to failure. Compare the frozen packet with the real operating
context it represents. Preserve natural user ambiguity, repository guidance,
source comments, tests, fixtures, and missing information when the real agent
would receive the same context. Repair the packet only when it omits,
misstates, invents, or gives false authority to context relative to that real
situation. If a faithful real-world packet reliably induces the wrong result,
improve the skill or another genuine operating control; changing the case
would only make the evaluation easier.

Classify a failure before editing:

- **Skill defect:** general instructions omit or misstate a reusable reasoning
  step.
- **Instruction interaction:** another candidate-visible instruction or
  fixture reinforces, narrows, or contradicts the target skill.
- **Execution variance:** the skill already requires the missed behavior.
- **Packet defect:** decisive evidence is missing, leaked, or assigned to the
  wrong phase, or the packet materially misrepresents the real operating
  context.
- **Harness defect:** the candidate or judge did not receive the frozen inputs
  named by the receipt.

Repair skill defects with general language. Repair packet and harness defects
outside the target skill. Rerun the unchanged case after any repair and retain
the prior run.

When the evaluator is valid but the corrective mechanism is uncertain, search
multiple independent skills and proven practices by generalized behavior class,
not by case vocabulary. Use those sources to generate falsifiable treatment
hypotheses, preserve source and license provenance, and extract only the
smallest reusable tactic. The parallel-treatment procedure owns controls,
dose-matching, planned replication, mechanism scoring, finalist selection, and
held-out transfer.

When the target skill has accumulated substantial process text, compare a
neutral baseline, a lean replacement, and the unchanged full skill instead of
assuming incremental editing is safest. Follow
[`references/ablation-campaign.md`](references/ablation-campaign.md): start the
lean arm from the smallest load-bearing rules, run one discriminating case,
then add back a rule only when a repeated corpus regression proves it is
missing. Existing prose earns retention through behavior, not age.

Complete when the result is labeled `PASS`, `FAIL`, or `UNANSWERABLE`, with the
reason and any generalized skill defect stated separately. For a skill-change
experiment, completion also requires the instruction-uptake rows and product-
movement classification above.

## Verification

The evaluation is complete only when:

- the target skill under test is identified by file digests;
- every candidate phase reads only its frozen allowlist;
- hidden judge evidence is absent from candidate workdirs and structured logs
  prove candidate reads stayed inside those workdirs;
- every run has raw output and a receipt;
- at least two independent judges assess behavioral correctness for a material
  skill change;
- a new case does not change any older case root digest; and
- a maintained regression suite runs through one command and every included
  case passes after a target-skill change; and
- no evaluation repair introduces case-specific hints into the target skill.
- a large distributed campaign, when used, has one checksum-bound effective
  result per expected attempt ID, with no missing, extra, or duplicate
  observations and no model outcome replaced by an infrastructure retry.
- a parallel treatment search, when used, has pre-declared controls,
  hypotheses, repetitions, source provenance, mechanism observations,
  selection rules, and held-out transfer for any promoted treatment.
