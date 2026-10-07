# skills

Reusable agent skills for [GitHub Copilot CLI](https://docs.github.com/copilot/concepts/agents/copilot-cli), Claude Code, and Codex CLI.

These skills help agents plan work, keep long tasks moving, review changes with independent models, verify real behavior, preserve context, and coordinate with other agent sessions.

Inspired by [mattpocock/skills](https://github.com/mattpocock/skills).

## Install

### GitHub Copilot CLI

```sh
copilot plugin install dfrysinger/skills
```

The bundled SDK extension currently requires Copilot CLI experimental mode.
Enable it with `/experimental on` (or start Copilot with `--experimental`);
the CLI restarts after the setting changes.

### Claude Code

```sh
claude plugin marketplace add dfrysinger/skills --scope user
claude plugin install --scope user dfrysinger-skills@dfrysinger-skills
```

### Codex CLI

```sh
codex plugin marketplace add dfrysinger/skills
codex plugin add dfrysinger-skills@dfrysinger-skills
```

The plugin is registered as `dfrysinger-skills`. Installing from this GitHub repository is the supported Copilot CLI path; direct local plugin installs are deprecated.

The Copilot plugin also packages the recipient-local
[`session-control`](./extensions/session-control/) SDK extension and a portable
[`mailbox-watcher`](./extensions/mailbox-watcher/) extension. Session-control is a runtime
dependency of `mailbox`, `rotate-session`, `unattended-run`, and `self-compact`. The extension
performs the final immediate `session.send()` or native compaction from inside
the recipient session; filesystem requests and receipts provide durable
machine-local IPC. macOS rotation separately replaces the verified tmux pane
process after the authorizing turn ends. Neither mechanism submits work to the
CLI FIFO.
Mailbox watcher polls a named recipient's durable mailbox and bridges synced
envelopes into that local request queue. The mailbox root may live in OneDrive,
but session-control heartbeats, locks, and receipts remain local. Sender-side
delivery and the recipient watcher share a short local notification claim so
they cannot both submit the same envelope during the pre-marker window.
Notification cleanup retains markers for every pending envelope, including
mail whose synced attachments are still stabilizing. A newly installed or
updated extension becomes active when
the recipient Copilot session starts or reloads its plugins. Run
`node extensions/session-control/reload-all.mjs` to reload every fresh local
Copilot session, or append session names to reload only those sessions. The
script verifies that each session publishes a new heartbeat with the installed
plugin version. An older request extension receives a one-time immediate
prompt to invoke its own reload action; subsequent updates reload directly
without model involvement. Sessions with a stale or missing heartbeat, or which do
not publish the replacement heartbeat, are collected in a final
`Restart required:` summary so the calling agent can report exactly which
Copilot CLIs need `/restart`. Claude and Codex mailbox recipients retain their
guarded terminal fallback.

When one logical agent name is reused across computers, mailbox addresses use
`name@machine` (for example, `hotel@surface-pro`) for one-computer delivery.
Set the stable machine label explicitly with `COPILOT_AGENT_MACHINE`; there is
no hostname fallback. Unqualified addresses such as `hotel` are local-only;
there is no implicit broadcast. Mutable mail lives under
`MAILBOX_LOCAL_ROOT` (default `~/.copilot/mailbox`). Qualified messages are
staged locally and use `MAILBOX_REMOTE_ROOT` only for immutable cross-computer
envelopes, attachments, and acknowledgement receipts. Run
`node skills/mailbox/scripts/mailbox.mjs configure --machine <name>
--remote-root <path>` once to persist the machine route across direct Copilot
restarts that do not inherit shell exports.

Session-control uses `COPILOT_SESSION_CONTROL_DIR` when set. The deprecated
`COPILOT_SESSION_INBOX_DIR` alias remains supported. Without an explicit
setting, an existing deprecated `~/.copilot/session-inbox` root remains
authoritative; otherwise session-control uses `~/.copilot/session-control`.
Selection never copies or merges roots. Deprecated selections emit a
diagnostic.

Session-control diagnostics are written as newline-delimited JSON under the
selected root's `logs/` directory. Extension logs are named by session and
generation; request-side events share a daily log. They record lifecycle, targeting, native request submission, SDK delivery
classification, recovery, and errors without deliberately recording prompt,
compaction-instruction, or continuation content. Files are mode `0600` and
entries older than 14 days are removed when a logger starts.

## Start here

| When you want to... | Use |
| --- | --- |
| Explore how a project should solve a problem | [`scout`](./skills/scout/SKILL.md) |
| Design a systemic or high-risk change | [`design-doc`](./skills/design-doc/SKILL.md) |
| Challenge whether a design's premises still justify its scope | [`constraint-challenge`](./skills/constraint-challenge/SKILL.md) |
| Build, fix, and ship a change | [`development-loop`](./skills/development-loop/SKILL.md) |
| Review a change with two independent model families | [`dual-review`](./skills/dual-review/SKILL.md) |
| Prove a user-visible change works in the real product | [`visual-proof`](./skills/visual-proof/SKILL.md) |
| Add a video walkthrough of new UX to a pull request | [`walkthrough-video`](./skills/walkthrough-video/SKILL.md) |
| Run a long task without losing the plan | [`unattended-run`](./skills/unattended-run/SKILL.md) |
| Pass work to another named agent | [`handoff`](./skills/handoff/SKILL.md) + [`mailbox`](./skills/mailbox/SKILL.md) |
| Turn a reusable procedure into a skill | [`skill-create`](./skills/skill-create/SKILL.md) |
| Regression-test an agent skill against frozen cases | [`skill-evaluation`](./skills/skill-evaluation/SKILL.md) |

## How the development flow fits together

The default path is:

1. [`scout`](./skills/scout/SKILL.md) finds what already exists and recommends whether to reuse, extend, or create.
2. [`grill-me`](./skills/grill-me/SKILL.md) resolves the user need, scope, and decisions before a systemic or critical design is fixed.
3. [`design-doc`](./skills/design-doc/SKILL.md) defines the durable work order and runs [`constraint-challenge`](./skills/constraint-challenge/SKILL.md) before and after selecting its architecture.
4. [`prototype`](./skills/prototype/SKILL.md) sketches major UI changes in disposable HTML before implementation.
5. [`development-loop`](./skills/development-loop/SKILL.md) owns implementation, targeted checks, live proof, review, and landing.
6. [`guardrails`](./skills/guardrails/SKILL.md) turns important architecture rules into deterministic checks.
7. [`visual-proof`](./skills/visual-proof/SKILL.md) captures precise still-image evidence for behavior that must be seen.
8. [`walkthrough-video`](./skills/walkthrough-video/SKILL.md) records and attaches the real journey for pull requests that add new UX.
9. [`dual-review`](./skills/dual-review/SKILL.md) uses independent model families to find and verify material defects.

The process scales with risk. A bounded fix should stay bounded. A systemic change earns a design, deterministic architecture checks, and stronger live proof.

<img width="5056" height="8704" alt="Development flow from exploration through implementation, proof, and review" src="https://github.com/user-attachments/assets/ad75e933-cd7b-48a3-ba59-aa418dc4f481" />

## Evaluate and hill-climb skills

[`skill-evaluation`](./skills/skill-evaluation/SKILL.md) tests what an agent
actually does with a skill, then helps improve that skill through controlled
experiments. Use it for any skill, not just the skills in this repository.
A **hill climb** is a repeated cycle of measuring failures, testing competing
improvements, and carrying supported gains into one shared revision.

The plugin includes the evaluator scripts, experiment procedures, and an
Actions workflow template. It does not include a task corpus, hidden answers,
model access, or hosted runners. You supply the tasks and acceptance criteria.
Candidate and judge model calls consume your model allowance; native builds
and Actions runs can add runner and storage costs.

### Start with one task

Install the plugin above, then ask your agent:

```text
Use skill-evaluation to evaluate my development-loop skill against a task
in this repository. Define observable acceptance criteria, keep reference
answers hidden from the candidate, and freeze the case before running.
Compare the unchanged skill with proposed improvements under the same
model and limits. Agree on the attempt budget before paid execution.
```

Use a historical failure with its original request and available context, or a
synthetic task with independently defined acceptance criteria. For coding
tasks, use the [repository-task guide](./skills/skill-evaluation/references/repository-tasks.md)
to supply an editable checkout, executable target checks, and regression checks.
Do not put the expected fix into the candidate's prompt or the skill.

For direct script use, you need Python 3, Git, and an authenticated Copilot CLI.
The local evaluator runs candidates and judges through Copilot CLI even if
another agent host helps prepare the experiment. Repository tasks also require
Docker, successful `validate-case` admission, and `COPILOT_GITHUB_TOKEN`.
Point `PLUGIN_DIR` at a complete installed plugin or a clone of this repository:

```sh
PLUGIN_DIR=/path/to/skills
EVAL="$PLUGIN_DIR/skills/skill-evaluation/scripts/skill_eval.py"
CORPUS="$PWD/my-skill-corpus"

python3 "$EVAL" init "$CORPUS"
python3 "$EVAL" add-case "$CORPUS" first-task \
  --skill development-loop --phase candidate
```

Fill the generated case definition, candidate prompt, candidate-visible
evidence, hidden criteria, and judge reference files. The scaffold is not a
ready-to-run task. Then freeze and run it:

```sh
python3 "$EVAL" freeze "$CORPUS" --case first-task
python3 "$EVAL" verify "$CORPUS" --case first-task
python3 "$EVAL" run "$CORPUS" --case first-task \
  --plugin-dir "$PLUGIN_DIR"
python3 "$EVAL" history "$CORPUS" --format markdown
```

When `COPILOT_GITHUB_TOKEN` is available, add `--home-mode isolated` to workflow
runs to avoid sharing your authentication home. See the
[case contract](./skills/skill-evaluation/references/case-contract.md) for
evidence boundaries and the [skill protocol](./skills/skill-evaluation/SKILL.md)
for repository-task admission and treatment comparisons.

### How evaluation works

The evaluator freezes and checksums each case, snapshots the exact plugin
bytes, and gives the candidate only the evidence available for its task or
phase. Hidden references go to separate judge sessions. It retains candidate
outputs, logs, model settings, receipts, and a `REPORT.md`.

Independent Claude and GPT judges must unanimously return `PASS`. Repository
tasks also have executable product and regression results, reported separately
from behavioral judgments. A completed command or green Actions workflow is
not proof that the skill solved the task. Failed attempts remain in history;
a pass obtained after retries is not a first-attempt pass.

### Improve the skill across a corpus

Ask your agent to use the
[cumulative hill climb](./skills/skill-evaluation/references/cumulative-skill-hill-climb.md)
and [parallel treatment search](./skills/skill-evaluation/references/parallel-treatment-search.md):

```text
Use skill-evaluation to improve this skill across my frozen corpus.
Start from the published skill and preserve its existing wins. Test distinct
general hypotheses against an unchanged control, with a fixed attempt budget,
repetitions, and a selection rule declared before execution. Integrate
supported changes into one shared candidate, verify its combined behavior,
then ablate it toward the smallest version that preserves the gains.
Keep held-out tasks for transfer testing and report all failed attempts.
```

Each experiment changes a general instruction, not a task-specific answer.
Hold the task, model, tools, grading, and limits fixed when comparing variants.
Independent ideas can run in parallel up to actual capacity. Check whether
the agent followed the new rule separately from whether product behavior
improved. When progress stalls, inspect task achievability and the earliest
wrong decision before generating more wording.

Combine compatible improvements and retest the exact combined revision.
Passing different tasks with different variants does not prove that one skill
passes the corpus. Only after the declared task set works, run **ablations**:
remove instructions and retest the exact shortened combination. Qualify
release candidates against maintained tasks and held-out transfer evidence;
report the minimum among tested variants, not a universal optimum.

Run the maintained local corpus with bounded parallelism:

```sh
python3 "$EVAL" run-suite "$CORPUS" \
  --plugin-dir "$PLUGIN_DIR" --workers 2
```

### Scale execution and measure cost

Start locally. For full repositories, native builds, or large experiment
matrices, use the [large Actions campaign guide](./skills/skill-evaluation/references/large-actions-campaign.md)
and [distributed tooling guide](./skills/skill-evaluation/references/distributed-campaign-tooling.md).
These require a configured private evaluation repository, packaged task
runtime, dependencies, model token, and suitable runners. The workflow is a
template, not a one-command hosted evaluation service.

The distributed tooling provides candidate-safe and hidden payloads,
checksum-verified artifacts, downstream-stage recovery, optional parallel
package hashing, and early retained-evidence validation before grading setup.
The [run observer](./skills/skill-evaluation/references/run-observation.md)
batches read-only Actions metadata for exact known attempts; it does not grade
results or grant dispatch capacity.

Measure the full feedback cycle: packaging, upload, queue, build, candidate and
judge calls, download, and result consumption. Batching or parallel hashing
can help some workloads and slow others. Use the
[measurement guide](./skills/skill-evaluation/references/measurement.md) to
compare like-for-like runs, preserve missing costs as unknown, and avoid
counting reused evidence as a new model attempt. Use
[`unattended-run`](./skills/unattended-run/SKILL.md) when a campaign needs durable
ownership, progress reminders, and a verifiable stopping condition.

## Skill catalog

### Development and delivery

- **[`scout`](./skills/scout/SKILL.md):** Research how to solve a problem before code is written, using evidence from the project, active work, the organization, and the wider ecosystem.
- **[`design-doc`](./skills/design-doc/SKILL.md):** Write and review a durable work order for a systemic or critical change.
- **[`prototype`](./skills/prototype/SKILL.md):** Prototype a new or substantially changed screen in throwaway HTML before building it.
- **[`development-loop`](./skills/development-loop/SKILL.md):** Develop and ship a non-trivial change through a process sized to its actual risk.
- **[`guardrails`](./skills/guardrails/SKILL.md):** Compile prose architecture rules into deterministic checks that catch structural and behavioral drift.
- **[`visual-proof`](./skills/visual-proof/SKILL.md):** Capture and inspect visual evidence for a running UI candidate.
- **[`walkthrough-video`](./skills/walkthrough-video/SKILL.md):** Record, validate, inspect, and attach a candidate-bound walkthrough for pull requests that add new UX.
- **[`unattended-run`](./skills/unattended-run/SKILL.md):** Keep a long Copilot CLI run anchored to its plan, operating rules, and completion gates.

### Review and independent judgment

- **[`constraint-challenge`](./skills/constraint-challenge/SKILL.md):** Independently challenge the load-bearing product, architecture, and security premises of systemic or critical work before design review and as implementation evolves.
- **[`dual-review`](./skills/dual-review/SKILL.md):** Run independent reviews with current Claude and GPT model families, verify disputed findings, and block only on material defects introduced by the change.
- **[`rubber-duck`](./skills/rubber-duck/SKILL.md):** Ask a different model family for one bounded, read-only second opinion. Copilot CLI uses its built-in rubber-duck agent, so this plugin copy is exposed only on hosts that need it.

<img width="700" alt="Independent review and finding verification flow" src="https://github.com/user-attachments/assets/cc58660a-3f0f-472a-9f8b-bb0abd878da6" />

### Agent communication and continuity

These skills form a small communication stack for long-lived, named agent sessions:

- **[`handoff`](./skills/handoff/SKILL.md):** Write a compact, durable continuation document for another agent or a fresh instance of the same agent.
- **[`mailbox`](./skills/mailbox/SKILL.md):** Deliver messages and files between named Copilot CLI sessions, including through a shared OneDrive mailbox, with a macOS tmux compatibility path for Claude Code and Codex CLI. Delivery is durable even when the receiving session or computer is offline.
- **[`self-compact`](./skills/self-compact/SKILL.md):** Compact a Copilot CLI conversation while preserving the durable baton, session-bound state, and one exact next action.
- **[`rotate-session`](./skills/rotate-session/SKILL.md):** Move a long-lived Copilot CLI session into a fresh conversation that rebuilds context from the retired session's files and history.
- **[`unattended-run`](./skills/unattended-run/SKILL.md):** Keep a long-running agent moving with an hourly progress nudge and a four-hour charter check, without repeating full reviews on a timer.

Two companion tools complete the workflow without pretending to be skills:

- **[Agent Stack](https://github.com/dfrysinger/agent-stack)** hosts named agent sessions on macOS and provides the optional `request_help` MCP tool. A blocked agent can ask its user for help through one bounded iMessage and a temporary Screen Sharing link.
- **Windows named sessions** use `copilot-agent <name>` after placing
  `scripts/copilot-agent.cmd` on `PATH`, or
  `scripts/copilot-agent.ps1 <name>` directly. The shorthand automatically
  creates or resumes the exact session, enables `--allow-all-tools`, and runs
  one initialization turn so its mailbox watcher is active. Explicit
  `new|resume|open <name>` modes remain available. The launcher maps each
  canonical lowercase `(COPILOT_AGENT_MACHINE, name)` pair to one deterministic
  Copilot session UUID, creates it with native `--name`, and resumes it by
  exact `--session-id`. Historical duplicate display names therefore do not
  make resume ambiguous, and no second terminal host or session registry is
  added.
- **Agent Preflight** coordinates agents working in different checkouts of the same repository. It checks active path claims, missing landed changes, overlapping pull requests, and recently pushed branches before work starts. It remains a separate GitHub CLI extension because it manages repository-wide coordination rather than model behavior. Its public packaging is still being prepared.

`handoff` records what another agent needs to know. `mailbox` delivers it. Agent Help reaches the user when no agent can proceed. Agent Preflight helps agents avoid starting conflicting work in the first place.

### Research, GitHub, and safety

- **[`authenticated-browse`](./skills/authenticated-browse/SKILL.md):** Let the user complete SSO or MFA in a headed browser, then reuse that local browser profile for bounded authenticated reading.
- **[`github-api-integration`](./skills/github-api-integration/SKILL.md):** Handle GitHub REST and GraphQL integration details including scopes, SAML redaction, pagination, rate limits, and actionable errors.
- **[`autonomous-github-actions`](./skills/autonomous-github-actions/SKILL.md):** Apply guardrails before an agent creates externally visible GitHub writes.
- **[`secret-hygiene`](./skills/secret-hygiene/SKILL.md):** Keep credentials out of conversations, source control, and published history.
- **[`git-history-recovery`](./skills/git-history-recovery/SKILL.md):** Recover lost or displaced Git work without rewriting unrelated history.
- **[`explain`](./skills/explain/SKILL.md):** Explain technical work in plain language without assuming the reader knows the source tree or its internal terminology.

### Skill authoring

- **[`skill-create`](./skills/skill-create/SKILL.md):** Create and validate a reusable skill without requiring the full Dreaming lifecycle.
- **[`skill-evaluation`](./skills/skill-evaluation/SKILL.md):** Build phase-isolated behavioral regression cases, compare neutral, lean, and full skill variants, and run checksum-reconciled large corpora through local workers or massively parallel private GitHub Actions.
- **[`writing-great-skills`](./skills/writing-great-skills/SKILL.md):** Structure skills so agents invoke them predictably and can follow them without excess context.

`writing-great-skills` is user-invoked and carries no automatic model-facing
trigger.

### macOS utilities

- **[`macos-background-app-control`](./skills/macos-background-app-control/SKILL.md):** Inspect and control a background macOS app without stealing focus or moving the pointer.
- **[`macos-photos-library`](./skills/macos-photos-library/SKILL.md):** Query Photos metadata and import app-test screenshots into an iCloud Photos album.

### Focused utilities

- **[`grill-me`](./skills/grill-me/SKILL.md):** Interview the user through every unresolved branch of a plan or design; `design-doc` invokes it before fixing scope.

## Why these skills exist

The collection is built around three practical limits:

1. **An agent should not be the only reviewer of its own work.** Independent model families find different defects, and disputed findings need verification rather than voting.
2. **Long tasks need durable state outside the conversation.** Plans, designs, proof receipts, handoffs, and scheduled re-briefs keep work from drifting after compaction or session rotation.
3. **Tests are necessary but cannot prove every user-facing claim.** Agents also need to drive the real application, observe the result, and preserve evidence tied to the exact candidate they tested.

## Larger companion projects

Some systems are intentionally separate because they need more than a skill prompt:

| Project | Role | Why it is separate |
| --- | --- | --- |
| [Agent Stack](https://github.com/dfrysinger/agent-stack) | Named remote agent sessions, tmux integration, mailbox wakeups, and Agent Help | Installs host services, CLI wrappers, and an MCP server |
| [Dreaming](https://github.com/dfrysinger/dreaming) | Autonomous skill learning, memory curation, and skill-library maintenance | Runs scheduled services and owns lifecycle state |
| Agent Preflight | Advisory coordination across checkouts and machines | Ships as a GitHub CLI extension with a shared repository ledger |
| Deep Review | Multi-reviewer ensemble with deduplication, opposing advocates, and an independent judge | Ships custom agents and model-intensive orchestration as its own plugin |

Deep Review is not folded into this repository. Its orchestration is large enough to remain a separate plugin, and its private mirror contains reproduced third-party review prompts with different licensing terms. A public release should first remove or replace material that cannot be redistributed under this repository's MIT license, preserve the verified attribution for the remaining components, and fix the known portability defaults.

## Repository layout

This repository contains curated, shareable skills loaded through host manifests. Personal or machine-specific skills should live outside this public plugin.

```text
plugin.json                 # Copilot CLI skill allowlist
.claude-plugin/plugin.json  # Claude Code skill allowlist
.codex-plugin/plugin.json   # Codex plugin manifest
skills/
  <name>/
    SKILL.md                # Skill prompt and protocol
    scripts/                # Optional deterministic helpers
    references/             # Optional long-form documentation
    templates/              # Optional starter files
  _lib/                     # Shared shell helpers used by skills
  NOTICE.md                 # Attribution for vendored skills
```

To add a public skill:

1. Add `skills/<name>/SKILL.md` and any support files.
2. Add the skill directory to each host manifest that should expose it.
3. Run the repository validation.
4. Commit the skill and manifest changes together.

The Copilot and Claude manifests can omit a skill when the host already provides a native equivalent. The Codex manifest exposes the skills directory as a whole.

Personal-only skills can live under `~/.copilot/skills/<name>/` and be reloaded with `/skills reload`.

## Update

### GitHub Copilot CLI

```sh
copilot plugin update dfrysinger-skills
```

### Claude Code

```sh
claude plugin marketplace update dfrysinger-skills
claude plugin update --scope user dfrysinger-skills@dfrysinger-skills
```

Then run `/reload-plugins` in the active Claude Code session.

### Codex CLI

Codex does not currently provide an in-place plugin update command:

```sh
codex plugin marketplace upgrade dfrysinger-skills
codex plugin remove dfrysinger-skills@dfrysinger-skills
codex plugin add dfrysinger-skills@dfrysinger-skills
```

## Forking

If you republish this collection:

1. Change the `name` field in `plugin.json`, `.claude-plugin/plugin.json`, and `.codex-plugin/plugin.json`.
2. Review every host-specific path, personal default, companion-project link, and platform requirement.
3. Keep the attribution in [`skills/NOTICE.md`](./skills/NOTICE.md) for vendored material.

## License

MIT. See [LICENSE](./LICENSE) and [skills/NOTICE.md](./skills/NOTICE.md).
