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

## Reference

### Code Review

- **[dual-review](./skills/dual-review/SKILL.md)** : Run latest Claude Opus and latest non-mini/non-codex GPT independently, then verify and risk-triage their findings. Only material defects introduced by the current change block landing; adjacent, hypothetical, and medium suggestions become follow-ups. After the bounded discovery rounds, finding-scoped autonomous closure fixes or removes remaining blockers before escalating only at explicit effort or authority limits.

### Browsing

- **[authenticated-browse](./skills/authenticated-browse/SKILL.md)** : Open a headed Playwright Chromium window so you can complete SSO/MFA/device-trust login manually, then let the agent reuse that persistent profile headlessly to fetch text/HTML/links, screenshot pages, or evaluate JS on internal sites it otherwise can't reach. Per-profile lock; cookies stay on your machine.

### Workflow

- **[development-loop](./skills/development-loop/SKILL.md)** : Size development process to the actual risk: bounded bug fixes use focused regression tests and a short review path; systemic and critical changes add durable design, architecture guards, and final live proof. Uses [`dual-review`](./skills/dual-review/SKILL.md)'s material-risk gate rather than requiring literal zero comments.
- **[git-history-recovery](./skills/git-history-recovery/SKILL.md)** : Recover lost or displaced Git work after an accidental reset/checkout/rebase/stash using reflog, dangling commits, and path-scoped restore.
- **[explain](./skills/explain/SKILL.md)** : Explain technical work in plain language scoped to the user's actual context — context before the point, no unexplained jargon, no assumed codebase knowledge.
- **[github-api-integration](./skills/github-api-integration/SKILL.md)** : Class-level playbook for integrating against the GitHub REST + GraphQL APIs — query-complexity limits, OAuth-App vs GitHub-App scope behavior, SAML-SSO null-node redaction, pagination, rate limits, and turning raw API errors into actionable UX.
- **[autonomous-github-actions](./skills/autonomous-github-actions/SKILL.md)** : Guardrails for agent-initiated, externally-visible GitHub writes — filing issues, opening PRs, posting comments, pushing to repos the user does not own.
- **[secret-hygiene](./skills/secret-hygiene/SKILL.md)** : Preventive playbook for keeping tokens / API keys / PATs / passwords / private keys out of both the chat transcript (which is sent to the cloud and persisted) and git. Covers the "never ask, never echo, never paste" rule for conversations, plus the layered defenses — gitignore, `.env.example` only, gitleaks pre-commit, GitHub push protection, pre-first-push visibility check — that stop credentials from reaching GitHub. Rotate-first if anything leaks.
- **[mailbox](./skills/mailbox/SKILL.md)** : Hand off a file or message from one Copilot CLI session to another running in a different tmux pane, addressed by tmux session name. Durable file queue under `~/.copilot/mailbox/<recipient>/`, best-effort `tmux send-keys` wakeup with verification poll, macOS notification fallback, and a resume-hook for the user's `ca` script. Pairs with `handoff` for cross-session continuation. Requires macOS + tmux + the [`ca` agent-naming convention from remote-agent-stack](https://github.com/dfrysinger/remote-agent-stack).
- **[macos-background-app-control](./skills/macos-background-app-control/SKILL.md)** : Drive a macOS app for verification without stealing focus or moving the cursor — background window screenshots via `CGWindowListCreateImage`, native-chrome control via Accessibility (AX), keystrokes/clicks via `CGEventPostToPid`. Use when verifying a GUI end-to-end while the user is actively working on the same Mac.

### Productivity (vendored from [mattpocock/skills](https://github.com/mattpocock/skills), MIT)

See [skills/NOTICE.md](./skills/NOTICE.md) for attribution.

- **[grill-me](./skills/grill-me/SKILL.md)** : Get relentlessly interviewed about a plan or design until every branch of the decision tree is resolved, with a recommended answer for each question.
- **[handoff](./skills/handoff/SKILL.md)** : Compact the current conversation into a handoff document (written to OS temp dir) so another agent can pick up the work; includes a "suggested skills" section. **Wired to [`mailbox`](./skills/mailbox/SKILL.md)**: when the user names a recipient session (e.g. "hand off to juliett"), the doc is auto-delivered via the mailbox queue with a tmux-wakeup so the recipient picks it up on their next turn.
- **[rotate-session](./skills/rotate-session/SKILL.md)** : Retire a session that has grown too large to reload and start a fresh one seeded to rebuild context from the old session's plan, checkpoints, todos, and transcript on disk. Nothing is deleted; the old session stays resumable. The manual equivalent of the size-based rotation offer in [`ca`](https://github.com/dfrysinger/remote-agent-stack).

Two skills are **user-invoked** — they carry no model-facing trigger, so they
cost nothing until you type their name: `grill-me` and `writing-great-skills`.

## Layout

This repository contains curated, shareable skills loaded through the plugin
manifest. Personal-only skills can live under
`~/.copilot/skills/<name>/` and load directly in Copilot CLI without a plugin
entry.

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

For a personal-only skill that should not be published, drop the directory
under `~/.copilot/skills/<name>/` instead and run `/skills reload`.

## Forking and portability

Most of this system is hardcoded to my paths/identity by default but parametrized via env vars. To run it under a different user / repo / Copilot identity:

| Override | Default | Effect |
| -- | -- | -- |
| `SKILLS_REPO_ROOT` | `~/code/skills` | Public plugin repository path |
| `SKILLS_LOCAL_ROOT` | `~/.copilot/skills` | Personal native skills root |

Two manual edits a forker should make:

- `.claude-plugin/plugin.json` `name` field — the published plugin slug. Mine is `dfrysinger-skills`; rename it to `<your-handle>-skills` if you republish.
- `~/.copilot/copilot-instructions.md` — reword any personal trigger prose to
  your preferences.

## License

MIT. See [LICENSE](./LICENSE).

## FYI: Dreaming

[Dreaming](https://github.com/dfrysinger/dreaming) is the optional autonomous
companion that learns reusable procedures from completed work, rolls durable
memory into skills, and consolidates or prunes the personal skill library. Its
repository contains the automation, installer, operational safeguards, and
dreaming-specific skills.
