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
- an editable `repository-task` for a coding task with independent executable
  target and regression checks; follow
  [`references/repository-tasks.md`](references/repository-tasks.md);
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

Complete when a candidate cannot read the expected answer and a judge can trace
every required behavior to frozen evidence.

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

Repository tasks require successful `validate-case` admission and caller-supplied
`COPILOT_GITHUB_TOKEN`. They always use an isolated Docker candidate and
isolated judge homes. `--arm baseline` exposes no target plugin; `--arm skill`
invokes the unchanged skill. Their executable score, behavioral verdict, and
first-attempt suite success are reported separately. Candidate timeouts are
scored failures; retries do not improve pass@1.

Every attempt records owned usage observations and full wall time, including
failed invocations, judgments and cleanup. Missing credits remain unknown.
For repository tasks, `--quality-review` adds paid, independent source-only
shipping assessments without changing correctness or retry policy.

Read local results with:

```sh
python3 "$SKILL_DIR/scripts/skill_eval.py" history CORPUS --format markdown
python3 "$SKILL_DIR/scripts/skill_eval.py" history CORPUS --format json
```

See [`references/measurement.md`](references/measurement.md) for accounting
coverage, resumed-session totals, quality evidence and matched history
populations. Do not interpret a partial subtotal as a final bill or compare
different task revisions as the same experiment.

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

Classify a failure before editing:

- **Skill defect:** general instructions omit or misstate a reusable reasoning
  step.
- **Execution variance:** the skill already requires the missed behavior.
- **Packet defect:** decisive evidence is missing, leaked, or assigned to the
  wrong phase.
- **Harness defect:** the candidate or judge did not receive the frozen inputs
  named by the receipt.

Repair skill defects with general language. Repair packet and harness defects
outside the target skill. Rerun the unchanged case after any repair and retain
the prior run.

Complete when the result is labeled `PASS`, `FAIL`, or `UNANSWERABLE`, with the
reason and any generalized skill defect stated separately.

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
