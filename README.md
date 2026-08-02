# skills

My agent skills for [GitHub Copilot CLI](https://docs.github.com/copilot/concepts/agents/copilot-cli) and other coding agents. Small, composable, and easy to adapt.

Inspired by [mattpocock/skills](https://github.com/mattpocock/skills).

## How to install

### Copilot CLI

```sh
copilot plugin install dfrysinger/skills
```

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

Skills register as `dfrysinger-skills` and become available to invoke from your agent session. Direct local installs from a path on disk are deprecated in Copilot CLI; installing from this GitHub repo is the supported path.

### Optional: install the autonomous self-learning daemon (macOS)

The daemon runs three per-user LaunchAgents under your login session:

- `com.${USER}.skills.dreaming` (daily 09:15) — one ordered owner for daily transcript consolidation, followed by memory roll and dry-run pruning when the weekly bucket is due.
- `com.${USER}.skills.selftest` (manual) — preflight check.
- `com.${USER}.skills.watchdog` (daily 12:15) — freshness, failure, halt, and overdue-success alerts.

Install + verify:

```sh
~/code/skills/skills/skill-review/scripts/daemon-install.sh install
~/code/skills/skills/skill-review/scripts/daemon-install.sh selftest
~/code/skills/skills/skill-review/scripts/daemon-install.sh enable
```

Other commands: `status`, `uninstall`, `rollback`. Install backs up and removes
the legacy `sweep`, `curator`, and independently provisioned `memory` agents,
then leaves the shared halt switch active until self-test succeeds. Any file at
`~/.copilot/skill-state/skill-review/disable-daemon` makes autonomous
maintenance no-op.

The daemon writes only to `~/.copilot/skills/` (local, no remote) and the state dir `~/.copilot/skill-state/`. It never modifies this public repo, even on disk — `verify-repo-unchanged.sh` is the post-run guard.

## Reference

### Self-learning skill system — a port of [Hermes Agent](https://github.com/NousResearch/hermes-agent) to Copilot CLI

A port of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)'s autonomous self-learning machinery (MIT). Agents create skills from real work without being asked, and the library is routinely consolidated or pruned. Because Copilot CLI has no code-enforced post-turn fork like Hermes, the autonomous-creation trigger is reimplemented as an end-of-task subagent dispatch plus the daily consolidation pass of one dreaming job. Weekly memory roll and pruning remain later passes of that same owner. Both paths share a writer lease and durable ledger. The [two-root layout](#layout) provides the containment Hermes gets from forking. Full attribution and the verbatim-vs-adapted breakdown: [skills/skill-review/references/NOTICE.md](./skills/skill-review/references/NOTICE.md).

- **[skill-review](./skills/skill-review/SKILL.md)** : Autonomous per-session reflection that creates/patches skills WITHOUT asking — a port of Hermes's `background_review.py` (`_SKILL_REVIEW_PROMPT` lifted verbatim, wrapped in a binding Copilot execution contract). Writes only to the LOCAL root.
- **[skill-curator](./skills/skill-curator/SKILL.md)** : Periodic curator (Hermes `curator.py`) that consolidates narrow sibling skills into umbrellas and archives unused ones on a 7-day cadence; agent-created skills are autonomous, hand-made skills are recommend-only.
- **[skill-create](./skills/skill-create/SKILL.md)** / **[skill-manage](./skills/skill-manage/SKILL.md)** : Copilot-native re-expression of Hermes's skill-management tool surface — create, patch, archive, restore, pin, promote, or extend a skill with enforced authoring standards and a validator.

To trigger an autonomous skill-creation pass on demand instead of waiting for
the dreaming backstop, drop a scoped prompt like this into a fresh Copilot CLI
session:

> Dispatch skill-review subagent to scan my last 30 days of sessions for any procedure I had to explain to an agent more than twice that isn't already covered by a skill in `~/code/skills/skills/` or `~/.copilot/skills/`.

The subagent runs the same prompt the daemon does, scoped to whatever pattern you describe. Phrase the ask in terms of *recurring teaching patterns* rather than specific error messages — the reviewer is tuned to dismiss one-off failures as noise, so framing like "find this bug class" tends to come back empty even when the pattern is real. Output lands in `~/.copilot/skills/` with a `.agent-created` marker and a ledger entry; the public repo stays pristine.

### Code Review

- **[review](./skills/review/SKILL.md)** : Run latest Claude Opus and latest non-mini/non-codex GPT independently, then verify and risk-triage their findings. Only material defects introduced by the current change block landing; adjacent, hypothetical, and medium suggestions become follow-ups. After the bounded discovery rounds, finding-scoped autonomous closure fixes or removes remaining blockers before escalating only at explicit effort or authority limits.

### Browsing

- **[authenticated-browse](./skills/authenticated-browse/SKILL.md)** : Open a headed Playwright Chromium window so you can complete SSO/MFA/device-trust login manually, then let the agent reuse that persistent profile headlessly to fetch text/HTML/links, screenshot pages, or evaluate JS on internal sites it otherwise can't reach. Per-profile lock; cookies stay on your machine.

### Workflow

- **[develop](./skills/develop/SKILL.md)** : Size development process to the actual risk: bounded bug fixes use focused regression tests and a short review path; systemic and critical changes add durable design, architecture guards, and final live proof. Uses [`review`](./skills/review/SKILL.md)'s material-risk gate rather than requiring literal zero comments.
- **[git-history-recovery](./skills/git-history-recovery/SKILL.md)** : Recover lost or displaced Git work after an accidental reset/checkout/rebase/stash using reflog, dangling commits, and path-scoped restore.
- **[explain](./skills/explain/SKILL.md)** : Explain technical work in plain language scoped to the user's actual context — context before the point, no unexplained jargon, no assumed codebase knowledge.
- **[github-api-integration](./skills/github-api-integration/SKILL.md)** : Class-level playbook for integrating against the GitHub REST + GraphQL APIs — query-complexity limits, OAuth-App vs GitHub-App scope behavior, SAML-SSO null-node redaction, pagination, rate limits, and turning raw API errors into actionable UX.
- **[autonomous-github-actions](./skills/autonomous-github-actions/SKILL.md)** : Guardrails for agent-initiated, externally-visible GitHub writes — filing issues, opening PRs, posting comments, pushing to repos the user does not own.
- **[secret-hygiene](./skills/secret-hygiene/SKILL.md)** : Preventive playbook for keeping tokens / API keys / PATs / passwords / private keys out of both the chat transcript (which is sent to the cloud and persisted) and git. Covers the "never ask, never echo, never paste" rule for conversations, plus the layered defenses — gitignore, `.env.example` only, gitleaks pre-commit, GitHub push protection, pre-first-push visibility check — that stop credentials from reaching GitHub. Rotate-first if anything leaks.
- **[mailbox](./skills/mailbox/SKILL.md)** : Hand off a file or message from one Copilot CLI session to another running in a different tmux pane, addressed by tmux session name. Durable file queue under `~/.copilot/mailbox/<recipient>/`, best-effort `tmux send-keys` wakeup with verification poll, macOS notification fallback, and a resume-hook for the user's `ca` script. Pairs with `handoff` for cross-session continuation. Requires macOS + tmux + the [`ca` agent-naming convention from remote-agent-stack](https://github.com/dfrysinger/remote-agent-stack).
- **[macos-background-app-control](./skills/macos-background-app-control/SKILL.md)** : Drive a macOS app for verification without stealing focus or moving the cursor — background window screenshots via `CGWindowListCreateImage`, native-chrome control via Accessibility (AX), keystrokes/clicks via `CGEventPostToPid`. Use when verifying a GUI end-to-end while the user is actively working on the same Mac.

### Productivity (vendored from [mattpocock/skills](https://github.com/mattpocock/skills), MIT)

See [skills/NOTICE.md](./skills/NOTICE.md) for attribution.

- **[caveman](./skills/caveman/SKILL.md)** : Ultra-compressed communication mode. Cuts token usage ~75% by dropping filler, articles, and pleasantries while keeping full technical accuracy. Triggers on "caveman mode", "be brief", etc.
- **[grill](./skills/grill/SKILL.md)** : Get relentlessly interviewed about a plan or design until every branch of the decision tree is resolved, with a recommended answer for each question.
- **[handoff](./skills/handoff/SKILL.md)** : Compact the current conversation into a handoff document (written to OS temp dir) so another agent can pick up the work; includes a "suggested skills" section. **Wired to [`mailbox`](./skills/mailbox/SKILL.md)**: when the user names a recipient session (e.g. "hand off to juliett"), the doc is auto-delivered via the mailbox queue with a tmux-wakeup so the recipient picks it up on their next turn.
- **[rotate-session](./skills/rotate-session/SKILL.md)** : Retire a session that has grown too large to reload and start a fresh one seeded to rebuild context from the old session's plan, checkpoints, todos, and transcript on disk. Nothing is deleted; the old session stays resumable. The manual equivalent of the size-based rotation offer in [`ca`](https://github.com/dfrysinger/remote-agent-stack).

Three skills are **user-invoked** — they carry no model-facing trigger, so they
cost nothing until you type their name: `caveman`, `grill`, and
`writing-great-skills`.

## Layout

This system uses two skill roots with different authority:

- **PUBLIC plugin repo** (this repo, installed at `~/code/skills/`) — curated, shareable skills loaded via `.claude-plugin/plugin.json` `.skills[]`. The autonomous self-learning daemon never writes here; promotion of a local skill into this repo is a deliberate user action via `skill-manage/scripts/promote-skill.sh`.
- **LOCAL native root** `~/.copilot/skills/<name>/` — agent-managed, mutable. Loaded directly by Copilot CLI without a plugin entry. It is a local git repo with **no remote** (each daemon write is a reversible commit, but nothing is ever pushed). This is where the daemon-created and personal-only skills live.

Daemon dedup state (ledger + tombstones) lives outside both repos at `~/.copilot/skill-state/skill-review/` so it never leaks into the published plugin.

Public repo on-disk layout:

```
.claude-plugin/
  plugin.json           # explicit allowlist of skill directories
skills/
  <name>/
    SKILL.md            # the skill's prompt / protocol
    scripts/            # optional: deterministic helpers
    references/         # optional: long-form notes / docs
    templates/          # optional: starter files
  NOTICE.md             # attribution for vendored skills
```

Adding a new skill via this repo: drop a `SKILL.md` under `skills/<name>/`, list its directory in `.claude-plugin/plugin.json` `.skills[]`, commit. Re-run `copilot plugin update dfrysinger-skills` on any machine to pull the change.

For a personal-only skill that should NOT be published, drop the directory under `~/.copilot/skills/<name>/` instead and run `/skills reload`. Promote later if you decide to share it.

## Forking and portability

Most of this system is hardcoded to my paths/identity by default but parametrized via env vars. To run it under a different user / repo / Copilot identity:

| Override | Default | Effect |
| -- | -- | -- |
| `SKILLS_REPO_ROOT` | `~/code/skills` | Public/curated plugin repo path |
| `SKILLS_LOCAL_ROOT` | `~/.copilot/skills` | Local agent-managed skills root (must be a local-only git repo with no remote) |
| `SKILLS_STATE_DIR` | `~/.copilot/skill-state/skill-review` | Daemon ledger + tombstones location |
| `SKILLS_LAUNCHD_PREFIX` | `com.${USER}.skills` | LaunchAgent label prefix; rendered into `__LABEL__` in `skills/skill-review/assets/launchd/*.plist.tpl` at install time |
| `SKILLS_COAUTHOR_TRAILER` | `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` | Trailer appended to commits made by archive/restore/promote scripts. Override for Codex / Claude Code / etc. |

Plus two manual edits a forker should make:

- `.claude-plugin/plugin.json` `name` field — the published plugin slug. Mine is `dfrysinger-skills`; rename it to `<your-handle>-skills` if you republish.
- `~/.copilot/copilot-instructions.md` — the trigger prose currently names me; reword to your preferences.

The launchd daemon is **macOS-only** (`launchctl`, `security`, `osascript`). Linux porters would need a systemd-user wrapper around `skill-review/scripts/daemon-run.sh` — out of scope here, but the script itself is portable.

## License

MIT. See [LICENSE](./LICENSE).
