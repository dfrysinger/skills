---
name: skill-create
description: Create a new personal skill in dfrysinger/skills, enforcing HARDLINE authoring standards (frontmatter, naming, structure, size caps). Use when the user says "make this a skill", "create a skill for X", or when an agent recognizes a reusable procedure worth saving (per the auto-create trigger in copilot-instructions.md). For modifying an existing skill, use /skill-manage instead.
---

> **Paths note:** Paths below are the defaults; `$SKILLS_REPO_ROOT`, `$SKILLS_LOCAL_ROOT` and `$SKILLS_STATE_DIR` override them. See README "Forking and portability".


# skill-create

## When to use

- The user says "make this a skill", "create a skill for X", or similar.
- You (the agent) just solved a non-trivial task with reusable steps and the user confirms it should become a skill.
- You're following the auto-create trigger in `$HOME/.copilot/copilot-instructions.md` (see `## Skill self-learning`).

Route the request through
[`../skill-review/references/artifact-routing.md`](../skill-review/references/artifact-routing.md)
before authoring. Do **not** invoke this for one-off tasks, throwaway scripts,
or fact-only requests.

## Two-root skill layout (where new skills go)

There are two roots, with different authority:

- **LOCAL native root** `~/.copilot/skills/<name>/` — agent-managed, mutable.
  Loaded directly by Copilot CLI (no plugin, no registry). It is a local git
  repo with NO remote (commits are reversible; nothing is ever pushed). This is
  the default home for new agent-created skills and for any skill the user is
  fine keeping personal/local.
- **PUBLIC plugin repo** `~/code/skills/skills/<name>/` — curated, shared via
  the `dfrysinger/skills` plugin. Loads via `.claude-plugin/plugin.json`
  `.skills[]` (explicit allowlist). Use this only for skills the user wants
  published. The autonomous skill-review daemon never writes here.

Layout is **flat**: `<root>/<name>/SKILL.md`. No category subdirectories. Pick
one short kebab-case name; class-level umbrella, not session-specific.

If the user is ambiguous about where the skill should live, default to LOCAL.
A user can later promote local→public with `skill-manage/scripts/promote-skill.sh`.

## Authoring standards

`writing-great-skills` in this repo is the rubric: read its `SKILL.md` and
`references/GLOSSARY.md` before drafting, so the draft arrives shaped by invocation
choice, the information hierarchy, completion criteria, and the failure modes
rather than being repaired into shape afterwards.

Then run `dual-review` on the draft before committing, and apply what the
reviewers agree on. Where they conflict, take the reading that removes an
escape hatch or an unobservable completion criterion.

The mechanical checks below are the ones a script can settle. The skill is
**not done** until all eight pass.

1. **Description ≤ 1024 characters, includes "Use when…"** Frontmatter `description:` is the only thing the agent sees when picking a skill. State the capability in plain language, then a second sentence with concrete triggers. No marketing words ("powerful", "comprehensive", "seamless"). Don't repeat the skill name. Verify:
   ```bash
   awk '/^description:/{gsub(/^description: */,""); print length}' SKILL.md
   ```

2. **Tools referenced in prose must be the ones Copilot CLI actually exposes.** Use names like `view`, `edit`, `create`, `grep`, `glob`, `bash`, `task`, `manage_schedule`, `web_fetch`, `ask_user`, `report_intent`. Do **not** name shell utilities the agent already has wrapped — `grep` → `grep` tool, `cat`/`head`/`tail` → `view`, `find`/`ls` → `glob`. Third-party CLIs are fair game inside `scripts/` but should not be the headline interaction surface.

3. **Platform gating.** Skills using macOS-only primitives (`security`, `osascript`, `launchctl`, `/Users/...` hardcoded paths, `pbcopy`) must say so in the SKILL.md `## Prerequisites` section. Default posture: try cross-platform first (Python `pathlib`, `tempfile.gettempdir()`, etc.); gate only when the dependency is genuinely OS-bound.

4. **Modern section order in SKILL.md body.** `# <Skill Name>` title, 1-3 sentence intro stating what it does (and what it does NOT do), then:
   - `## When to use` — concrete trigger conditions
   - `## Prerequisites` — required env vars, tools, files (if any)
   - `## Quick start` — minimal working invocation
   - `## Workflow` / `## Procedure` — step-by-step
   - `## Pitfalls` — known failure modes (optional but encouraged)
   - `## Verification` — how to confirm it worked (optional)

   Target ≤100 lines for simple skills, ≤200 for complex. Cut intro fluff,
   marketing prose, and re-explanations of env vars already in `## Prerequisites`.

5. **Scripts go in `scripts/`, references in `references/`, templates in `templates/`.** Don't expect the model to inline-write parsers or non-trivial logic every call — ship a helper script. Reference it from SKILL.md by path relative to the skill directory.

6. **Frontmatter shape.**
   ```yaml
   ---
   name: <slug>            # lowercase, regex ^[a-z0-9][a-z0-9._-]*$, ≤64 chars
   description: <≤1024 chars, two sentences ending with "Use when…">
   ---
   ```
   Optional: `version`, `author`, `license`, `platforms: [macos]`.

   The body then opens with a single H1 that is exactly the slug — `# <slug>`, lowercase, no Title Case and no prose title. That heading is what the agent reads as the skill's identity when the body is injected into context, so it must match the name the user types to invoke it.

7. **Name is short, distinct, and reachable in 3-4 keystrokes.** Prefer one word (`scout`, `explain`, `prototype`); use two when the second word earns its place by disambiguating (`dual-review`, `self-compact`, `visual-proof`). Avoid naming a skill after a CLI command it drives — `/compact` and `/autopilot` are typed by the user, and a skill sharing that name reads as the command.

   A name the user types has to autocomplete: some word in it needs a 3- or 4-character prefix that reaches this skill and nothing else installed, and the leading word is the one worth spending that prefix on. A skill reached only by an agent, a script, or a scheduled job spends no keystrokes and is exempt — give it the clearest name and set `hand-invoked: false` in its frontmatter. Slug regex `^[a-z0-9][a-z0-9._-]*$`. Check the name and its collisions in one pass:
   ```bash
   ~/code/skills/skills/skill-manage/scripts/check-name-prefix.sh <slug>
   ```
   Exit 1 prints what the candidate collides with. Read that list before renaming the candidate, because the fix is often to **move the squatter instead**: an accurate name is worth more than a free prefix, and a prefix held by a rarely used skill can usually be freed. `development-loop` was briefly renamed to dodge `/loo`, when the actual blocker was a Microsoft Loop skill that had no claim to the generic word. Renaming that one gave the loop skill its name back. Move the squatter only when it is genuinely the worse claim to the prefix and nothing external is wired to its name — a daemon's name is not worth a keystroke.

   Name the skill from its contents, then test the prefix. Reaching for whatever prefix happens to be free produces a name that has to be justified afterward from a stray phrase in the description: a Nexus skill that is 900 lines of build traps and known bugs was briefly called `nexus-map`, for the `/map` nobody else had taken.

   Then confirm the slug itself is unused across both roots:
   ```bash
   grep -lr "^name: <slug>$" \
     ~/code/skills/skills/ ~/.copilot/skills/ \
     ~/.copilot/installed-plugins/ 2>/dev/null
   ```

8. **Size caps.** SKILL.md body ≤ 100k characters (~36k tokens). Individual supporting files ≤ 1 MiB. If you're over, split into `references/`.

## Procedure (LOCAL root — the default)

This is the path the autonomous daemon uses and the right default for any new
agent-created skill. NO git push, NO plugin.json registration.

1. **Gather** (use `ask_user` if anything is missing; never multiple-choice for @dfrysinger):
   - Skill `name` (kebab-case)
   - One-sentence what-it-does + one-sentence "Use when…"
   - Whether it needs scripts (deterministic ops) or references (long docs)

2. **Pre-flight collision check across BOTH roots:**
   ```bash
   ls -d ~/code/skills/skills/<name> ~/.copilot/skills/<name> 2>/dev/null \
     && echo "COLLISION"
   ```
   If collision, ask the user to pick a different name or confirm overwrite.
   Also run `~/code/skills/skills/skill-review/scripts/check-tombstone.sh <name>`
   — exit 0 means a curator tombstone exists and you must NOT recreate it.

3. **Create the directory:**
   ```bash
   mkdir -p ~/.copilot/skills/<name>/{scripts,references}
   ```
   Only create the subdirs you'll actually populate.

4. **Author SKILL.md** following the modern section order (rule 4).

5. **Validate.**
   ```bash
   ~/code/skills/skills/skill-manage/scripts/validate-skill.sh \
     ~/.copilot/skills/<name>/SKILL.md
   ```

6. **Test scripts.** Sanity-run anything in `scripts/` to confirm it executes.

7. **Mark provenance** (only when this skill was created autonomously, not by hand):
   ```bash
   ~/code/skills/skills/skill-review/scripts/mark-agent-created.sh \
     <name> <session_id> <mode> \
     --task-key <platform-or-baton-task-key> \
     --independence verified \
     --evidence-kind <kind> \
     --summary "<privacy-safe summary>" \
     --routing-reason "<why this is a skill>"
   ```
   Pass the current task key and privacy-safe evidence summary. Continuations
   reuse the handoff/rotation task key. If no explicit task key is available,
   the helper mints one but records the evidence as unverified.

8. **Commit in the LOCAL repo only:**
   ```bash
   cd ~/.copilot/skills
   git add <name>/
   git commit -m "skills/<name>: <one-line summary>

   <Optional body.>

   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   ```
   There is no remote — nothing is pushed.

9. **Tell the user how to activate it:**
   - Run `/skills reload` in any open Copilot CLI session, or restart.
   - The skill loads automatically as `/<name>` (native personal skill — no
     plugin entry needed).

## Procedure (PUBLIC repo — when the user asks for a shareable skill)

Use only when the user explicitly wants the skill shared via the plugin. Do
NOT default to this path for autonomous creation.

0. **Publishability gate — `~/code/skills` is a PUBLIC GitHub repo.** Read the
   drafted skill and confirm every line is safe for the open internet. Keep it
   in the LOCAL root instead when it names an employer-internal codebase, repo,
   org, host, team, or person; describes a private system's file layout,
   models, or endpoints; or encodes anything learned from a private repo.
   Generic technique stays public; the private specifics that made it concrete
   do not. Completion criterion: you can name, for each proper noun in the
   skill, why it is public knowledge — otherwise use the LOCAL procedure.

1. Steps 1–6 same as above, but with `~/code/skills/skills/<name>/` as the
   target dir. Skip step 7 (no `.agent-created` marker on a curated skill).

2. **Register the skill in `.claude-plugin/plugin.json`** (REQUIRED — skills
   are an explicit allowlist; an unlisted dir is silently ignored):
   ```bash
   ~/code/skills/skills/skill-manage/scripts/registry.sh register <name>
   ```

3. **Commit and push** the public repo:
   ```bash
   cd ~/code/skills
   git add skills/<name>/ .claude-plugin/plugin.json
   git commit -m "skills/<name>: <summary>

   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   git push origin main
   ```

4. **Refresh the plugin cache** so the new skill loads:
   ```bash
   git -C ~/.copilot/installed-plugins/_direct/dfrysinger--skills pull --ff-only
   ```
   Then `/restart` (or `/skills reload` is not enough for plugin changes).

If the skill already exists in the LOCAL root and you just want to publish it,
use `~/code/skills/skills/skill-manage/scripts/promote-skill.sh <name>` instead
— it moves, strips provenance, registers, and commits both repos.
Before promotion, run the normal independent review over every file, then seal
the exact reviewed inventory:

```bash
skill-manage/scripts/promotion-review.py approve ~/.copilot/skills/<name> \
  --reviewer <claude-review-id> --reviewer <gpt-review-id>
```

Promotion refuses a missing, stale, single-reviewer, or private-sentinel
inventory.

## Pitfalls

- **Forgetting that LOCAL and PUBLIC have different rules.** Local skills need
  no `plugin.json` entry and never get pushed. Public skills require
  registration and a plugin-cache refresh. Don't apply the public workflow to
  a local skill (you'll fail at `git push` since there's no remote).
- **Description that doesn't trigger.** If your description doesn't include
  concrete keywords for when to load the skill, the agent will never pick it.
  Re-read rule 1.
- **Skill that duplicates an existing capability.** Before creating, glob
  `~/code/skills/skills/**/SKILL.md` AND `~/.copilot/skills/**/SKILL.md` for
  overlap. Better to extend an existing skill via `skill-manage patch` than to
  create a near-duplicate.
- **Auto-create spam.** The auto-create trigger in `copilot-instructions.md`
  is a *proposal* (Tier 1) or contained autonomous (Tier 2 daemon). The bar
  is: "would I want to invoke this same procedure again next month?"
- **Vendoring third-party skills.** When importing externally-authored skills,
  copy them verbatim, pin the source commit, preserve the license, and add a
  `NOTICE.md` (see `~/code/skills/skills/NOTICE.md` for the existing example).

## Verification

After completing the procedure, the new skill should:

1. Exist at `~/.copilot/skills/<name>/SKILL.md` (LOCAL) or
   `~/code/skills/skills/<name>/SKILL.md` (PUBLIC)
2. Pass `validate-skill.sh` with zero errors
3. For PUBLIC only: be listed in `.claude-plugin/plugin.json` `.skills[]`
4. Be committed in its owning repo
5. Appear as `/<name>` after `/skills reload` (LOCAL) or `/restart` after
   plugin cache refresh (PUBLIC)

If any of these fail, the skill is not done — fix and re-validate.
