---
name: skill-manage
description: Patch, archive, restore, pin, or extend an existing personal skill in dfrysinger/skills. Use when the user wants to modify a skill, when skill-curator proposes a consolidation, or when a skill needs a new supporting file. For brand-new skills use skill-create instead.
---

> **Paths note:** Paths below are the defaults; `$SKILLS_REPO_ROOT`, `$SKILLS_LOCAL_ROOT` and `$SKILLS_STATE_DIR` override them. See README "Forking and portability".


# skill-manage

## When to use

- User says "edit the X skill", "patch X to handle Y", "archive X", "pin X", "add a reference file to X".
- `skill-curator` proposes a consolidation (merge sibling skills into an umbrella) and the user approves the live run.
- You need to add a `references/`, `templates/`, `scripts/`, or `assets/` file to an existing skill.

For **creating** a new skill from scratch, use `/skill-create` instead.

## Prerequisites

- macOS (scripts use `mv`, `git`, standard POSIX tools).
- Two skill roots (see `/skill-create` for the model):
  - PUBLIC repo `~/code/skills/` (clone of `dfrysinger/skills`, pushable)
  - LOCAL native `~/.copilot/skills/` (local git repo, NO remote; agent-managed)
- `find-skill.sh`, `archive-skill.sh`, `restore-skill.sh`, and `promote-skill.sh`
  are all root-aware: they search both roots and operate inside whichever root
  owns the skill.
- Never edit the installed cache under `~/.copilot/installed-plugins/`.

> **Attribution.** Ported from [Hermes Agent](https://github.com/NousResearch/hermes-agent)'s
> `skill_manage` tool (`tools/skill_manager_tool.py`), adapted to Copilot CLI.

## Actions

All actions operate on a skill identified by its `<name>` (slug). The script `scripts/find-skill.sh <name>` resolves a name to its directory; you'll need it for everything below.

| Action | What it does | Reversible? |
|---|---|---|
| `patch` | Find-and-replace inside `SKILL.md` or any support file | yes (git revert) |
| `edit` | Full rewrite of `SKILL.md` | yes (git revert) |
| `write-file` | Add/overwrite a `references/<f>.md`, `templates/<f>.<ext>`, `scripts/<f>.<ext>`, or `assets/<f>` | yes (git revert) |
| `remove-file` | Delete a supporting file | yes (git revert) |
| `archive` | Delete the skill dir in a commit and record the commit that still holds it | yes (`restore`) |
| `restore` | Check the skill back out of the commit named in its retirement record | yes (`archive`) |
| `pin` | Touch `.pinned` in the skill dir — curator skips it | yes (`unpin`) |
| `rename` | Move the skill to a new slug and rewrite every reference in both roots | yes (rename back) |
| `unpin` | Remove `.pinned` | yes (`pin`) |
| `promote` | Move a LOCAL skill into the PUBLIC repo (strip provenance, register, commit both) | yes (manual) |

**Hard rule**: **no unrecoverable delete**. Archiving removes the skill from the working tree but never from history: the commit before the deletion still holds it, and `archive-skill.sh` writes that SHA to `~/.copilot/skill-state/skill-review/retired/<name>.json` so `restore` is one command.

An earlier design parked retired skills in a git-tracked `.archive/` directory. It was dropped: it published dead skills to everyone installing the plugin, and every script that walked the tree had to remember to filter `.archive/` out — a filter that was, at least once, forgotten, so archived skills counted as live name collisions. Git history already is the archive.

## Workflow

### patch (the most common)

1. Resolve target file path with `find-skill.sh`.
2. Use the `edit` tool (NOT a shell `sed`) — Copilot CLI's `edit` tool verifies uniqueness of `old_str` and won't silently match the wrong block.
3. After edit, re-run validator:
   ```bash
   ~/code/skills/skills/skill-manage/scripts/validate-skill.sh \
     "$(scripts/find-skill.sh <name>)/SKILL.md"
   ```
4. Commit with the user's per-clone author config (already set):
   ```bash
   cd ~/code/skills && git add -A && git commit -m "skills/<name>: <change>

   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
   ```

### archive

1. Verify the skill is **not pinned** (`.pinned` file absent). Pinned skills refuse archive — surface a clear message and stop.
2. Run:
   ```bash
   scripts/archive-skill.sh <name> [--absorbed-into <umbrella>]
   ```
   `--absorbed-into <umbrella>` is required when the curator merged this skill's content into another — it gets recorded in the commit message so consolidation history stays traceable. The script auto-detects which root the skill lives in: PUBLIC repo archives commit to `~/code/skills` and unregister from `plugin.json`; LOCAL native archives commit to `~/.copilot/skills` (no registry touch). Tombstones for agent-created skills always go to `~/.copilot/skill-state/skill-review/tombstones/`.

3. Verify: the skill dir is gone, `git log -1` in the owning root shows the deletion, and `~/.copilot/skill-state/skill-review/retired/<name>.json` exists.

### restore

```bash
scripts/restore-skill.sh <name>
```
Reads the retirement record for the restore commit and path, falling back to
finding the deletion in the log when no record exists. Clears any
matching tombstone in the state dir. Re-registers in `plugin.json` only when
restoring into the public repo.

### promote (LOCAL → PUBLIC)

```bash
scripts/promote-skill.sh <name>
```
Moves `~/.copilot/skills/<name>` into `~/code/skills/skills/<name>`, strips the
`.agent-created` provenance markers (it becomes a curated skill), registers in
`plugin.json`, validates, and commits BOTH repos. USER-RUN ONLY — the
unattended daemon never promotes.

**Clear the publishability gate first** (`skill-create`, PUBLIC procedure step
0): `~/code/skills` is a public GitHub repo, so a skill naming an
employer-internal codebase, repo, org, host, team, or person stays LOCAL. A
local skill earned its detail from private work, so this gate bites hardest
exactly here.

### rename

A rename is not a `git mv`. The slug appears in the directory name, the frontmatter, the H1, every other skill that names this one, the PUBLIC plugin manifest, and the README — and references cross roots, so renaming a PUBLIC skill can require a commit in the LOCAL repo too. Do the whole set at once:

```bash
scripts/rename-skill.sh <old-name> <new-name>     # add --no-commit to inspect first
```

It refuses a name that is taken or malformed, rewrites only the forms that name a skill (backticked mentions, `skills/<name>/` paths, `/dfrysinger-skills:<name>`, and `[<name>](…)` links) so prose containing the same words survives, re-registers the skill in the manifest, validates, and fails if any stale reference is left. Prose that describes a *process* rather than naming a skill is the caller's judgment call — after `dual-review` was briefly renamed, phrases like "note dual-reviewed in the commit message" were correct to leave alone.

Before choosing the new name, run `scripts/check-name-prefix.sh <new-name>`; `skill-create` rule 7 covers what makes a name good.

**Complete when** the script reports the rename, the version is bumped, the PUBLIC repo is pushed, and the plugin cache is re-synced. Until that sync, other sessions still hold the old name.

### pin / unpin

```bash
scripts/pin-skill.sh <name>     # touch <skill-dir>/.pinned
scripts/pin-skill.sh <name> --unpin
```

Pin protects from **archive only**. Patch/edit/write-file still work — pinning preserves a skill while letting it evolve.

### write-file

Add a supporting file under one of `references/`, `templates/`, `scripts/`, `assets/`:

1. Validate the destination is one of the allowed subdirs (script `scripts/check-subdir.sh`).
2. Validate the file path has no `..` traversal and stays inside the skill dir.
3. Validate size ≤ 1 MiB.
4. Use the `create` tool (errors if file exists — overwrite uses `edit`).
5. `chmod +x` if it's a script.
6. Commit.

## Pitfalls

- **Editing the installed cache.** Always operate under `~/code/skills/` (PUBLIC) or `~/.copilot/skills/` (LOCAL). The installed cache at `~/.copilot/installed-plugins/_direct/dfrysinger--skills/` gets wiped on every plugin sync.
- **Trying to push the LOCAL repo.** `~/.copilot/skills` is a local git repo with NO remote — commits stay machine-local on purpose. `git push` will fail. Use `promote-skill.sh` if you want a local skill published.
- **Patching a pinned skill is fine; archiving it is not.** If you need to archive a pinned skill, ask the user to unpin first. Don't unpin → archive on your own — pin is the user's explicit signal "preserve this".
- **Skipping the validator after a patch.** Frontmatter is easy to break (missing `---`, malformed YAML, description that grew past 1024 chars). Always re-validate.
- **Forgetting to push.** PUBLIC-repo commits aren't shared until `git push origin main` — the user's other clones won't see the change. LOCAL-repo commits never push (no remote); that's intentional.
- **Consolidation without preserving support files.** If you're absorbing skill X into umbrella Y, X may have `references/`, `templates/`, or `scripts/` that the absorbed content references. Re-home those files into Y's matching subdirs and update the destination paths in Y's prose. (See `references/curator-prompt.md` in `skill-curator`.)

## Verification

After any mutating action:

1. `git -C <owning-root> status` shows the change staged or committed (PUBLIC: `~/code/skills`; LOCAL: `~/.copilot/skills`).
2. `validate-skill.sh` on the changed SKILL.md returns zero errors.
3. `scripts/find-skill.sh <name>` resolves to the expected path (a retired skill resolves to nothing — it is not in the tree).
4. For archive/restore: directory listing matches the new location, the old location is gone.
