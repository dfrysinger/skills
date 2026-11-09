# Evaluation playbook

Choose the method by the user's decision, then choose an environment that can
produce the evidence needed for that decision. Reuse the evaluator and detailed
procedures linked here; this playbook does not define another runner.

## 1. Route the request

| User's decision | Comparison | Procedure |
| --- | --- | --- |
| Build a corpus or add a historical or synthetic case | Source evidence and behavioral criteria versus the frozen candidate and judge packets | [Build and freeze a case](../SKILL.md#2-make-the-test-capable-of-observing-that-behavior) |
| Prevent a historical mistake that required user steering | Capture-time instructions versus a general correction on the same task | [Repair a steering event](#4-repair-a-steering-event) |
| Evaluate or improve a skill revision | Revised instructions versus the unchanged skill on the same frozen cases | [Establish the baseline](../SKILL.md#3-establish-the-unchanged-baseline), then [compare](../SKILL.md#4-change-one-mechanism-and-compare) |
| Make a skill activate at the right times | Unchanged versus revised description, with the body and surrounding collection fixed | [Test skill selection](skill-selection.md) |
| Adopt a new model or skill collection | Current setup versus the proposed setup on representative tasks | [Compare setups](#5-compare-models-or-skill-collections) |
| Simplify a working skill | Working instructions versus reduced instructions on preserved behavior | [Minimize a skill](#6-minimize-a-working-skill) |
| Check that existing behavior still works | One exact revision against its maintained cases | [Run a regression suite](direct-evaluator-commands.md) |
| Qualify a release, no-skill advantage or transfer claim | The exact artifact, matched controls and applicable unused transfer cases | [Qualify release and generalization](release-qualification-and-generalization.md) |
| Repair the evaluation system | Retained artifacts and the cheapest fixture exercising the changed boundary | [Prove the execution route](large-actions-campaign.md#3-prove-one-route-before-fan-out) |

Use the decision record in [SKILL.md](../SKILL.md#1-declare-the-question-and-trigger).
State the requested result, evidence boundary, comparator, case roles, planned
attempts, selection rule and stop rule. A setup check, an exploratory comparison
and final confirmation answer different questions.

For requests outside the table, use that decision record and the applicable
existing skill section; preserve the requested outcome rather than forcing it
into the nearest row. For requests spanning routes, choose the primary decision
and apply every gate needed for the claims made. A regression-only result does
not qualify a no-skill advantage or generalization claim.

**Complete when:** one route and its allowed conclusion are recorded. An
adoption comparison does not silently become skill tuning or minimization.

## 2. Choose the measurement environment

Model-based evaluations run on [GitHub Actions](large-actions-campaign.md) by
default. Actions supplies the machines and jobs; the task type defines the work
being evaluated. A [task runtime](distributed-campaign-tooling.md) prepares the
environment, invokes the evaluator and captures results. These are layers of
one pipeline, not competing evaluation systems.

Choose the task type, then confirm that its runtime supplies these capabilities:

| Evaluation type | Required capabilities | Evidence and limits |
| --- | --- | --- |
| Response-only | Prose cases with `skill` and `view`, optionally resumed across phases | Tests the actual response to supplied evidence, not executed investigation, edits or recovery. |
| [Repository editing](repository-tasks.md) | Editable source, working commands, captured changes and independent executable checks | Tests performed work after the image, task and supported permissions are confirmed runnable. A code snapshot alone does not restore conversation or session state. |
| Application or continuing workflow | The actual app, browser or service, required tools and relevant session state | Tests the exercised flow after the runtime demonstrates those capabilities. A generic VM or repository fixture does not supply them automatically. |
| [Skill selection](skill-selection.md) | Ordinary requests, available descriptions and recorded unforced choices | Tests discovery separately. Forced loading is not selection evidence; the standard first-phase prose route requires loading and does not qualify as-is. |
| Infrastructure checks | Deterministic tests, tiny fixtures and retained-output replay; local preparation checks need no model call | Tests the evaluator boundary, not a skill's behavioral advantage. |

For historical steering events, prefer a faithful executable continuation.
Choose the cutoff by the [decision being tested](#choose-the-replay-starting-point),
not by a fixed number of turns. Restore prior messages in their conversation
roles, relevant observed tool results, instructions and workspace or application
state at the same cutoff. Apply the chosen question's evidence boundary and
let new actions determine subsequent observations. Use a repository-only reconstruction when
that state is sufficient; otherwise identify the missing restoration capability.
An adapted test supports only its narrower claim. Running on Actions does not
by itself restore a session.

Inspect the rendered prompt and actual child-process command before dispatch.
The prose runner announces an evaluation and restricts work to reading. The
repository runner requires one non-resumed candidate phase; its candidate has
network access and does not enforce remote-history isolation. Neither mode
alone proves an uncoached, complete historical replay.
Both standard modes disable custom instructions and built-in MCPs. If that
removes relevant original context or tools, the trial is an adapted environment,
not an exact continuation.

For description optimization, follow [skill selection](skill-selection.md)
before dispatch. It separates selection, successful loading and task outcome;
documenting that procedure does not establish runtime readiness.

Establish that required operations work under supported permission controls
before spending on candidates. The existing repository invocation uses blanket
tool and path approvals; do not dispatch that invocation unchanged as a
permission-faithful trial. Resolve the approval route within an explicitly
scoped runner repair first. A container boundary does not by itself establish
permission fidelity.

For an execution claim, verify the resulting files, tests, service state or
other required outcome. Read the trajectory to assess unnecessary human
handoffs, unsupported claims and preserved boundaries. A promise to work is
not evidence that work occurred. Check necessary behavior and outcomes without
requiring one exact tool sequence or reference implementation.

For sustained autonomy, exercise the relevant continuation, interruption,
resume and scheduling conditions. A short decision test is not an overnight
autonomy test. Shortened waits establish only the transitions they preserve.

**Complete when:** every candidate-owned action has a runnable path and every
success criterion has observable evidence. Assign genuine human-owned steps
separately. If a required path is missing, report the setup gap and narrower
available measurement; retain the user's original goal.

## 3. Assign historical cases a role

Search existing task metadata and frozen cases by skill, failure class and
incident lineage before capturing another case. Follow
[historical capture](historical-case-capture.md) for source evidence and the
[case contract](case-contract.md) for freezing. An index entry locates a case;
it does not supply its private packet, current environment or execution proof.
Use catalog commands only when the selected installation exposes them.

Assign roles for the candidate and decision being evaluated:

| Role | Permitted use | Evidence limit |
| --- | --- | --- |
| Development | Inspect traces, choose changes, compare hypotheses and remove instructions | Cannot establish independent transfer for a revision it helped choose. |
| Selection validation | Rank candidates or decide when to stop using a broader representative set | Selecting the winner with these scores uses the set; it is not untouched final confirmation. If traces guide edits, record development use too. |
| Maintained regression | Check that required earlier behavior survives | Historical familiarity does not invalidate regression value, but does not make it held-out. |
| Reserved confirmation or transfer | Evaluate a frozen candidate on cases not used to write or select it | Once feedback guides a revision, further search or a changed selection rule, that case is development evidence for the successor. Reserve fresh confirmation. |

Regression can overlap with development or selection. An exposed case can
still protect required behavior; it cannot become unused evidence again.

The shared catalog's initial historical imports are development-exposed, not
fresh holdouts. Check exposure records before any stronger claim. Unknown
exposure is not evidence of independence. A hidden answer is not the same as
an unused case.

Keep related turns, variants and copied tasks from the same incident together
when reserving cases. Separate files or session IDs do not prove independent
incidents. Select representative ordinary successes, past mistakes and cases
where the learned behavior should not apply, rather than only familiar traps.
For long-context failures, preserve relevant context length and compaction
conditions; a clean short prompt may remove the cause.

Private captures, hidden answers, transcripts and local bindings remain at
their authorized source. Shared metadata is not permission to publish packets.

**Complete when:** selected cases have exact revisions, recorded roles and
exposure limits. Missing independent cases narrow the claim rather than being
silently replaced by familiar cases.

### Size the set and stage the search

Choose coverage before percentages. Include independent incidents across the
relevant behaviors, ordinary successes and appropriate non-use or stopping.
Twenty to fifty real-failure tasks is practitioner starting guidance, not a
training minimum or a universal split. Short activation queries and complete
agent tasks have different costs and coverage. Here development changes
instructions, not model weights.

Choose development, selection and confirmation allocations for the decision
and available independent cases. A frozen two-setup comparison does not need
a training partition unless tuning is part of the question. Repetitions
measure variation on the same task; they do not supply missing incident
coverage. If the set is too small for a useful independent estimate, report
the uncertainty rather than inventing confidence from a split ratio.

Before search, name the maintained suite whose behavior must survive, its
preservation rule, the screening coverage, expansion checkpoints and budget:

| Stage | Case scope and decision |
| --- | --- |
| Explore a change | The actual failure plus a few sensitive preservation cases; reject unsupported changes cheaply. |
| Select candidates | Expand survivors to representative cases and rotate background coverage; use fixed comparisons and planned repetitions. |
| Integrate | Check combined bytes and periodically run the full maintained suite to expose missed effects. |
| Qualify | Run the exact finalist on the full declared maintained suite; use unused confirmation cases for independent transfer claims. |

Use the full small suite when that is simpler than staging. A large catalog
is not automatically the maintained suite. Declare relevant coverage before
scores arrive; narrow screens do not replace final regression qualification.
Keep reserved confirmation out of routine search. If its feedback drives a
revision or new search, record the exposure and obtain fresh confirmation for
the successor's independent claim.

Reduce screening cost with fewer complete tasks or candidates, not by turning
performed work into response-only proposals or shortening away required
long-running behavior. Include controls, repetitions, grading and setup in
the budget. The paper-backed pattern is staged allocation; exact batch sizes
and split fractions remain experiment choices.

## 4. Repair a steering event

The question is whether a general instruction change prevents the need for the
same user intervention, not whether an agent can agree with the correction.

1. **Trace the causal mistake.** Resolve the original session, exact
   request, available instructions, tool results and later correction through
   [historical capture](historical-case-capture.md). Classify whether the cause
   is instructions, their interaction, model variance, tools, missing authority
   or the evaluation itself. An observed mistake does not automatically imply
   a missing skill sentence.
2. **Restore the decision boundary.** Use the
   [starting-point procedure](#choose-the-replay-starting-point) to select the
   prevention cutoff with the conversation-visible context and relevant
   environment. Keep the correction,
   successful recovery and grading criteria hidden. Give the ordinary request
   without coaching the candidate about the mistake. Let its new actions
   determine subsequent observations; historical replies cannot be assumed
   valid after the candidate takes a different path. For a session-continuation
   claim, restore prior messages in their conversation roles through a
   supported restore path. Supplying them only as a file is a different task;
   label that adaptation rather than calling it the original session.
   Restore the conversation representation the original model received,
   including its captured compaction boundary; a full raw transcript is not
   equivalent to compacted context. Deliver the exact captured human or
   scheduled event in its original role. Keep evaluation announcements,
   diagnoses and forced skill loads outside that continuation unless they
   were in the original event. Inspect the actual delivered input, not only
   the importer receipt, and label unavailable original input precisely.
   Recover the skills through the [Git restoration recipe](#restore-historical-skills-from-git).
3. **Prove the case, then reproduce with the current setup.** Check that the task is
   achievable and the required behavior is observable. Prefer a faithful
   executable continuation for action-dependent failures. Record unavailable
   historical state and every fixture substitution. Apply the main skill's
   [baseline gate](../SKILL.md#3-establish-the-unchanged-baseline) before
   proposing a repair. If only a response test is possible, keep it a separate
   decision screen with the original executed-recovery requirement unresolved.
4. **Investigate independent hypotheses in parallel when useful.** Use isolated
   copies of the same draft and unchanged control. Each alternative should
   change a distinct general mechanism. Follow
   [parallel treatment search](parallel-treatment-search.md) when selecting
   among alternatives; one well-supported correction can use a focused pair.
5. **Integrate supported changes into one draft.** Use the
   [cumulative hill climb](cumulative-skill-hill-climb.md). Judge actual
   progress and preserved behavior before crediting instruction uptake.
   Independent task wins do not become a score for untested combined bytes.
6. **Minimize where justified.** Use
   [delta ablation](cumulative-skill-hill-climb.md#4-minimize-the-new-increment)
   when additions are substantial, conflict, create unnecessary work or need
   a minimality claim. A small supported correction need not wait for a whole
   skill rebuild. Without ablation, report size rather than minimality.
7. **Confirm the exact final draft.** Compare with the relevant unchanged
   setup, protect maintained behavior and use fresh transfer evidence for a
   transfer claim. Include genuine-stop cases so preventing unnecessary waits
   does not teach the agent to ignore real permission or information needs.
   Apply [release qualification](release-qualification-and-generalization.md)
   only at the requested delivery boundary.

If the declared baseline avoids the specific mistake, retain non-reproduction
and inspect concrete fidelity differences before another attempt. A Negative
for a different omission does not reproduce this incident. Keep the selected
incident unresolved rather than substituting an easier task; further runs
need a recorded changed fidelity or hypothesis question. Record what worked
under the measured conditions without inventing a skill advantage.

**Complete when:** the exact candidate has the required behavioral evidence,
or the report identifies no supported change, an inconclusive comparison or a
specific prerequisite. Preserve the observed historical mistake in every case.

### Restore historical skills from Git

Recover the repository snapshot before declaring historical skills unavailable.
Use the chosen replay cutoff, not merely the session's creation date: a long
session can load updated skills before the failure.

1. **Find the source revision.** Start with captured repository identities,
   commit IDs, plugin versions and successful skill-load records. Prefer a
   recorded revision; otherwise use the cutoff's UTC timestamp to locate a
   candidate on the repository's canonical branch or release ancestry:

   ```sh
   COMMIT=$(git -C "$SKILLS_REPO" rev-list --first-parent -1 \
     --before="$CUTOFF_UTC" "$CANONICAL_REF")
   ```

   Set `SKILLS_REPO` to the source checkout, `CANONICAL_REF` to the relevant
   canonical branch or release, and `CUTOFF_UTC` to the selected event time.
   If history is shallow or the revision is absent, retrieve the needed
   history from that repository before concluding it cannot be recovered.
   Commit dates locate candidates; they do not prove publication or installation.
2. **Check against actual loads.** Compare version metadata and recorded skill
   bodies or content hashes with the candidate revision. Account for documented
   loader transformations, such as omitted front matter. If they disagree,
   trace intervening updates, local edits or another source rather than silently
   substituting the date-selected commit. One matching body does not establish
   every installed file. Keep prior loaded text separate from the collection
   available for future calls under the chosen
   [context policy](case-contract.md#native-historical-continuation).
3. **Freeze the full repository.** Preserve manifests, the surrounding skills,
   references and helpers, not only the target's `SKILL.md`. First apply the
   [sensitive-content boundary](historical-case-capture.md#1-define-the-event-boundary)
   to the selected tree. If it contains protected content, capture permitted
   files with labeled omissions instead of retaining an unredacted archive;
   record the resulting reconstruction limits. Otherwise set `ARCHIVE` to a
   new absolute file path in the evaluation's isolated input storage, then:

   ```sh
   test -n "$COMMIT" && test ! -e "$ARCHIVE" &&
     git -C "$SKILLS_REPO" archive --format=tar --output="$ARCHIVE" "$COMMIT"
   ```

   Record the remote, cutoff, commit/tree IDs, version, archive SHA-256 and
   source-load matches in the existing capture receipt or artifact ledger.
   Verify required files against Git; account for export attributes and
   submodules rather than assuming an archive includes them. Stage the verified
   files through the existing evaluator's skill/catalog binding, without
   changing the live installation.
4. **Separate recovery from comparison.** Diff the actual declared skill
   package, including references and helpers, against the proposed candidate.
   If the bytes are identical, there is no changed-skill comparison to run.
   Keep the recovered baseline, reproduce under its normal admission gates,
   then design a justified change if needed. A version bump or changes elsewhere
   in the collection do not establish a change to this package. An older
   session-start version is a different starting point, not a way to manufacture
   an old/new difference at the failure cutoff.

Record personal overrides, uncommitted inputs and missing task/runtime state
separately. Recoverable repository files need not wait for those investigations;
a repository snapshot alone does not establish a complete historical machine.

**Complete when:** required repository-backed skills are recovered and bound to
source evidence, any installation uncertainty is explicit, and the proposed
comparison has either a verified package delta or a baseline-only next step.
This preparation is not proof that the failure reproduces or that a change helps.

### Choose the trigger and recovery expectation

Identify both the event that gives the agent an opportunity to act and the
earlier decision that may have caused the failure. They are not always the
same event. Record the exact trigger, then-current state, expected transition,
observable progress and observation horizon before choosing skill changes.

For autonomy failures, a real user follow-up after the agent has stalled tests
response to human intervention, not prevention of the stall. For a prevention
claim, start from the real earlier event before the first unsupported stop or
before the agent produced the plan, objective or schedule that caused it.
Withhold the later intervention. A scheduled wake in the bad state may test
autonomous recovery, not initial prevention.

| Suspected source or opportunity | Replay starting point | Required observation |
|---|---|---|
| An ordinary scheduled prompt should recover a stalled run | Bad state intact, immediately before the original scheduled prompt | The prompt reaches the intended skills; the agent recognizes the problem, changes the relevant state and resumes permitted work. |
| A schedule or objective was authored incorrectly | Before the request that produced it, with that request's context | Each arm creates its own artifact; later faithful wake prompts exercise that artifact and demonstrate the downstream result. |
| An agent-produced design, plan or other source misdirects later work | Before its production trigger | Each arm produces its own source material, then the dependent work consumes it. A supplied corrected document would bypass the behavior under test. |
| The response to a user request was wrong | Immediately before that exact request, retaining its original context | The agent performs the requested work correctly. If the request corrects an earlier mistake, label the result guided recovery. |
| Drift develops during continuing work | The preceding supported work trigger, with relevant accumulated context | Exercise enough actions, context growth, interruption or compaction to observe the drift and its recovery or prevention. |

These are not mutually exclusive categories. A bad design can produce a bad
objective that later wake prompts reinforce. First isolate the supported
causal decision; then confirm the changed artifact works in its downstream
path. A long session describes the needed context and horizon, not a separate
kind of fix. Use it when the failure depends on that journey; a short replay
cannot support that longer claim.

**Recovery without corrective steering** retains the mistake and gives the
agent only the evidence and ordinary opportunity it would normally receive.
A scheduled prompt may supply that opportunity. Preserve its exact wording.
If it originally names a skill, successful invocation is part of that scheduled
path, not unforced skill discovery.

Adding a diagnosis, a corrected objective, or a new instruction to load the
intended skill is a different intervention. It can test guided recovery or a
proposed schedule change, but cannot establish recovery under the old trigger.
For unforced selection, measure the original request before target loading.
For proposed schedule changes, compare old and new schedules explicitly and
exercise the resulting behavior rather than crediting the skill alone.

Manually deliver a scheduled prompt only through a supported isolated test
route, with its source and delivery adaptation recorded. This tests that wake
path, not the scheduler's timing or delivery reliability. A claim about the
scheduler needs the scheduler itself. Never inject test prompts into live
unrelated sessions.

If existing skill text is already in restored context, use the
[skill-context policy](case-contract.md#native-historical-continuation).
Choose between clean replacement before exposure and an update during ongoing
work with identical historical text in both arms. Reloading availability alone
proves neither fresh invocation nor removal of prior instructions. An in-place
update can test recovery after an update, not prevention by a never-seen skill.

**Complete when:** the case distinguishes original versus proposed triggers,
recovery versus steering, artifact production versus downstream use, and
focused versus sustained outcomes. Unavailable state remains a prerequisite.

### Choose the replay starting point

The starting point determines the question. For steering prevention, default to
the latest restorable request boundary before the earliest supported causal
mistake, not the last visible symptom or the first unrelated error. This keeps
focused iteration short without fixing the decision the candidate must make.

| Question | Starting state | What a pass establishes |
| --- | --- | --- |
| Prevent the mistake | Before the agent makes the causal decision; later mistake and correction hidden | Avoidance under the restored conditions, not recovery from an existing mistake |
| Recover without steering | Mistaken plan, prior attempts and available evidence retained; before user correction | Recovery from that state without receiving the diagnosis or correction |
| Recover after steering | The mistake and exact user correction retained or delivered in a later phase | Ability to act on correction, not prevention or unaided recovery |
| Complete the larger task without steering | An earlier boundary before the relevant plan, objective or handoff was created | Success over the newly exercised path; a short local pass alone cannot establish this |

Use the existing capture trace ledger and evaluation decision record:

1. **Locate the cause with evidence.** Trace the observed failure backward
   through decisions and artifacts. Name the earliest supported contributor
   that the proposed change must prevent. Distinguish it from harmless errors
   and later consequences. Record competing explanations when attribution is
   uncertain; a trace diagnosis is a hypothesis, not proof of causation.
2. **Choose a supported request boundary.** Name the last included event,
   first excluded event and original request or wake trigger. If the decision
   occurs inside an assistant turn, restart from that turn's original trigger
   or an earlier supported boundary. Do not invent a request to reconsider the
   known error. A later recovery case needs a real or explicitly adapted
   continuation trigger; a new warning about being stuck supplies steering.
3. **Check instruction exposure.** For a clean skill comparison, move back
   before the target instructions first entered the relevant context, even
   when that predates the causal mistake. Audit summaries, memory and
   artifacts that carry those instructions forward. Use the
   [skill-context policy](case-contract.md#native-historical-continuation);
   if clean restoration is unavailable, retain recorded context and narrow the
   claim rather than silently deleting or replacing old text. Reload does
   not remove it. Model-only comparisons can hold recorded instructions fixed.
4. **Restore matching state and regenerate consequences.** Files, plans,
   objectives, schedules, tool state and permissions must agree with the
   chosen cutoff. If objective creation is under test, each arm must write its
   own objective from the original request; do not supply a corrected objective
   or preserve the old one as an authoritative instruction. Keep an existing
   bad objective when testing recovery from it. Let each branch's actions
   produce later observations; replaying recorded future tool results or
   dependent human replies after a different action changes the task.
5. **Choose the observation horizon and expansion rule.** During development,
   begin with the focused causal decision and enough executed work to see its
   consequences. Declare the required progress or outcome, limits and stopping
   rule before execution. Add an earlier task-level confirmation when the
   focused case fixes an artifact the proposed improvement must generate,
   omits relevant context buildup or compaction, or the claim covers the
   larger workflow. Missing restoration or continuation capabilities remain
   prerequisites; an earlier timestamp alone does not supply them.

**Illustrative example:** an agent writes an objective that incorrectly makes
deployment a human prerequisite, then repeatedly waits. Prevention starts before
objective creation and checks both the resulting objective and permitted work.
Unaided recovery starts with the bad objective intact and checks whether the
agent revises it and proceeds on its own. Guided recovery includes the user's
correction. Judge actual progress and preserve genuine human-only gates in all
three; a promise to continue is not success.

A short test can establish a corrected objective or an observed escape from a
loop. It cannot establish that the agent stays productive for many hours.
Retain relevant context length, compaction, real wake/resume behavior and timing
for claims that depend on them; shortened waits prove only the transitions they
preserve. An earlier cutoff does not recreate missing original model or runtime
inputs. Report restoration fidelity separately.

Freeze cutoff, skill exposure, state substitutions, horizon and claim before
comparing candidates. Use the same start for both arms. Different cutoffs are
separate cases or revisions, not extra repetitions or independent holdouts;
keep the incident lineage together. An exploratory cutoff change preserves
prior outcomes and records its reason, not just a newly favorable score.

This is the playbook's operational rule, not a published universal optimum.
[AgentRx](https://arxiv.org/html/2602.02475v2) supports distinguishing causal
failure steps from cascading symptoms through trajectory diagnosis.
[AgentDebugX](https://arxiv.org/html/2607.18754) connects diagnosis to checkpoint
reruns, but its diagnosis-guided repairs do not establish blind prevention.
Neither establishes a fixed rewind distance. Use
[Anthropic's agent-evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
for realistic task state, outcome checks, trajectory inspection and repetitions.

**Complete when:** the case record explains why its starting point tests the
named decision, audits relevant instruction exposure and state, and names the
observable horizon and allowed claim. Prevention, unaided recovery and guided
recovery results remain separate.

## 5. Compare models or skill collections

The question is which setup to use, not which setup can win one selected case.
Freeze the current setup before trying the proposed one.

| Change under consideration | Hold fixed | Interpretation |
| --- | --- | --- |
| Model only | Skills, task inputs, tools, agent runtime and grading | Difference between models under the recorded budgets and supported settings. |
| Skill collection only | Model, task inputs, tools, runtime and grading | Difference between complete collections, including reached references, helpers and discovery behavior. |
| Model and collection together | Task population, outcome criteria and permitted capabilities | Difference between whole setups. Use crossed model/collection comparisons only when attribution matters. |

Choose a representative task mix before looking at candidate scores. Include
ordinary work, historical mistakes, long-context or tool-heavy work where
relevant, and protected behavior that must not regress. Preserve case roles
from section 3; catalog familiarity alone cannot establish broad superiority.

Run a small matched comparison first, then expand promising setups to the
declared task population. Run independent ready attempts concurrently using
the [Actions execution procedure](large-actions-campaign.md). Keep the judging
models and rubric fixed when comparing candidate models.

Record model-specific effort settings, context limits, tool support and
budgets. The same setting name does not prove equal compute. A fixed-setup
comparison answers a different question from separately tuning each setup;
include tuning cost and new confirmation if tuning is part of adoption.

Assess product outcomes, material regressions, first-attempt success,
variation, latency and total cost. State the adoption rule in advance: which
behaviors must be preserved and what quality or efficiency gain is worth the
switch. Do not infer universal superiority from an aggregate score that hides
an unacceptable regression. A tie can favor the current setup, or a cheaper
setup when preservation is supported and efficiency is the stated objective.

For an external collection, inspect provenance, compatibility, instructions
and executable helpers before running it. Describe required tool or permission
changes as part of the setup, not an unexplained skill gain. Discovery tests
use natural invocation; forced entry-skill comparisons measure performance
after selection.

A no-target-skill comparison is optional unless needed for the claim. Preserve
other skills when isolating one skill's contribution. The repository
`--arm baseline` removes the entire plugin, so it cannot isolate one member of
a collection. See [matched controls](release-qualification-and-generalization.md#2-freeze-the-released-artifact-and-controls).

**Complete when:** the report recommends adopt, retain or inconclusive under
the declared workload and tradeoff, identifies untested compatibility and
migration cost, and separates the recommendation from installation authority.

## 6. Minimize a working skill

Fix the model and required behavior first. If simplification is intended for a
new model, establish that model's comparison separately; behavior retained on
one model does not establish retention on others.

Choose the scope:

- **New increment:** use
  [delta ablation](cumulative-skill-hill-climb.md#4-minimize-the-new-increment)
  after a supported repair. Freeze the parent and minimize only the declared
  change, preserving all other rules and earlier retained increments.
- **Whole skill:** use the
  [ablation campaign](ablation-campaign.md) as a separate failure-driven
  rebuild. Keep the unchanged full skill as the comparison. Start with no
  target procedure, observe missing behavior, and add one compact general
  rule at a time only when matched evidence supports it. An interface stub
  is not identical to removing the skill entirely.

Follow the staged scope above for both routes. The ablation campaign owns
whole-skill controls, add-back decisions and interaction checks; a whole
rebuild is not a prerequisite for releasing a minimized increment. Normal
permissions and non-target instructions remain unchanged in every arm.

Compare exact final bytes with full instructions for behavior, size, runtime
and resource use. If no target skill performs equally well under a valid
comparison, removal is an option, not proof it is unnecessary in untested
workloads. Call a result the smallest tested candidate that preserves measured
behavior, not a proven global minimum.

**Complete when:** one reduced revision meets the predeclared preservation
rule, or the full revision is retained with the unsupported reductions and
remaining uncertainty reported.

## 7. Apply common evidence and stopping rules

Use the detailed [measurement](measurement.md),
[comparison](parallel-treatment-search.md) and
[completion-report](completion-report.md) contracts rather than creating new
result schemas.

- **Outcomes before eloquence.** Prefer executable state checks for performed
  work. Use calibrated model or human review for behavior and quality that
  those checks cannot determine. Preserve real task ambiguity and accept
  alternative correct solutions.
- **Blindness is specific.** Keep later answers out of candidate context.
  When supported, give comparison judges neutral A/B labels without version
  identity or a preferred winner. Inspect actual prompts and access paths;
  hidden criteria, an evaluation-aware candidate and a blinded judge are
  separate properties. Disclose unsupported blindness rather than claiming it.
- **Repetitions are planned evidence.** Keep all original outcomes and count
  the requested, launched, completed, valid and judged attempts separately.
  Predeclare repetition and retry rules. A lucky best run or retry-assisted
  success does not measure first-attempt reliability or prove determinism.
- **Spend to resolve uncertainty.** Use cheap valid screens for development;
  confirm behavioral claims at their actual boundary. Include packaging,
  upload/download, runner startup, builds, candidate calls, judges and feedback
  time in cost coverage. Missing amounts remain unknown.
- **Repair the first invalid stage.** Diagnose task, environment and grading
  problems separately from skill behavior. Reuse intact retained output when
  repairing downstream grading. Preserve original judgments and separately
  identify corrected ones; do not rerun candidates merely to repair a report.
- **Stop without inventing a winner.** End the declared batch when it answers
  the question or yields no useful movement. Another batch needs a distinct
  hypothesis or discriminating measurement. Do not enlarge thresholds, retries
  or scope just to obtain a positive result.
- **Use clear reporting labels.** A completed comparison has a Positive,
  Negative or Inconclusive conclusion relative to its stated objective.
  Failed execution is separate. Preserve native `PASS`, `FAIL`, `INVALID`
  and `UNANSWERABLE` fields unchanged and explain them in the report.
- **Separate delivery stages.** A drafted rule, an experimental winner, a
  regression-qualified candidate and a released installation are different
  states. Preserve existing review, publication and installation gates.

**Complete when:** the report gives the supported decision, evidence scope,
remaining uncertainty and exact delivery state. Updating this playbook alone
does not validate its effect on future agents.

## Method sources

These sources support method choices, not claims about local runner readiness:

- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents):
  realistic isolated environments, outcome checks, transcript review,
  repeated trials and capability versus regression testing.
- [Anthropic: Improving skill-creator](https://claude.com/resources/articles/improving-skill-creator-test-measure-and-refine-agent-skills):
  matched skill comparisons, independent contexts, blind comparison and
  separate activation testing.
- [Anthropic skill-creator source](https://github.com/anthropics/skills/tree/main/skills/skill-creator):
  task execution, grading and feedback-driven revision. Its automated
  description optimizer concerns activation, not full historical restoration.
- [OpenAI: Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices):
  representative workload tests, human calibration and pairwise judging with
  attention to position and verbosity bias. This is methodological guidance,
  not a requirement to adopt its hosted evaluation service.
- [GEPA, original paper](https://arxiv.org/html/2507.19457v1):
  trace-based prompt changes, small-batch screening, broader validation and
  separate final testing.
- [MIPROv2 procedure](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/MIPROv2.md)
  and [ProTeGi](https://arxiv.org/html/2305.03495v2):
  minibatch evaluation, periodic full validation and adaptive candidate
  selection. These LM-program and prompt-search methods inform allocation,
  not a proven universal agent-skill ablation recipe.
- [Cawley and Talbot: selection bias](https://jmlr.org/papers/v11/cawley10a.html):
  finite selection sets can themselves be overfit; selection scores are not
  untouched estimates of the selected winner.
