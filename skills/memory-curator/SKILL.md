---
name: memory-curator
description: Audit the GitHub Copilot memory store, roll durable facts into skills, and delete migrated/duplicate memories to cut always-loaded context. Use when curating Copilot memories, when the memory list at github.com/settings/copilot/memory has grown large, when memories duplicate existing skills, or when running the weekly automated memory-curation job.
---

# memory-curator

GitHub Copilot **memories** load in full on every turn; **skills** load only
their one-line description until invoked. So a fact that lives as a memory costs
context every single turn, while the same fact woven into a skill costs nothing
until the skill is opened. This skill moves durable memory content into the
right skills and then deletes the migrated memories — the memory analog of the
`skill-review` daemon that curates transcripts.

It is designed to run **both** interactively (you, now) and as the roll pass of
the unattended effective-weekly dreaming job (see
`references/memory-curate-prompt.txt`).

## Hard safety rails (deletion is irreversible)

The GitHub memory store has **no undelete**. Obey these without exception:

1. **Commit before delete.** Roll a memory's content into a skill and `git
   commit` it BEFORE deleting that memory from the store. Content must be
   recoverable from git at all times.
2. **Only delete what you rolled or that is an exact duplicate.** Never delete
   an uncatalogued or unreviewed memory. The deleter is signature-matched
   (`mem-delete.sh`): it only clicks a row whose body starts with the first-55
   chars of a body you explicitly passed in.
3. **Protect keepers.** Maintain an explicit keep-allowlist and verify **zero**
   signature collisions between the delete list and the keepers before any
   delete (see the collision check in the runbook prompt).
4. **Login-safe.** If the browse session has expired, `mem-extract.sh` exits 5
   and notifies — no-op, do not crash, do not delete.
5. **Every skill write is validated + its own reversible git commit.** Run
   `skill-manage/scripts/validate-skill.sh` on each touched skill.
6. **Ledger everything.** Record each processed memory by content-hash in
   `~/.copilot/skill-state/memory-curator/ledger.jsonl` so future runs skip it.

## The memory page is a capped window of 100

`github.com/settings/copilot/memory` is a rotating SPA window showing at most
100 rows even when the store holds more. Deleting rows surfaces previously
hidden ones. So the curator **drains across passes/weeks**: extract → roll →
delete → re-extract, repeating until the window is empty or only keepers remain.

## Scripts (all in `scripts/`, source `mem-lib.sh`)

| Script | Purpose |
|---|---|
| `mem-extract.sh [-o FILE]` | Headless authenticated-browse dump of all visible memories as JSON `[{body,subject}]`. Detects logout (exit 5). Repairs mojibake. |
| `mem-delete.sh -f bodies.json` | Signature-matched deleter. Only removes rows matching a first-55-char signature of a supplied body. Loops passes until 0. |
| `mem-ledger.sh {hash\|seen\|add\|filter-new\|stats}` | Content-hash ledger to dedupe processed memories across runs. |
| `should-run-now.sh` | Foreground/legacy weekly self-gate. The dreaming orchestrator owns scheduled cadence. |

`mem-lib.sh` provides `mem_browse_eval` (retry-on-profile-lock), `mem_unwrap`
(double-JSON decode **+ latin1←utf8 mojibake repair**), `mem_logged_in`,
`mem_notify`, and the page URL/selectors.

### Known gotcha: mojibake in the prefix

Non-ASCII glyphs (—, →, §) can arrive double-encoded from the browse transport.
`mem_unwrap` now repairs this via a latin1→utf8 round-trip. If you extracted
bodies with an older build, repair before rolling:
`body.encode('latin-1').decode('utf-8')`. A corrupted body also breaks
signature matching (the garbage lands in the first 55 chars), so always extract
with the current `mem-lib.sh`.

## Interactive procedure

1. **Extract**: `mem-extract.sh -o /tmp/mem.json`. If exit 5, tell the user to
   re-auth (`authenticated-browse auth default <memory-url>`) and stop.
2. **Filter new**: `cat /tmp/mem.json | mem-ledger.sh filter-new` to skip
   already-processed memories.
3. **Categorize** each memory: `roll` (durable, belongs in a skill), `dup`
   (exact duplicate of another memory or an existing skill fact), `obsolete`
   (no longer true), or `keep` (a live preference you want as a memory).
   This categorization remains the deletion authority. For each `roll`, apply
   [`../skill-review/references/artifact-routing.md`](../skill-review/references/artifact-routing.md)
   only to choose its skill or support-file destination; an artifact-router
   discard never makes `obsolete` or `keep` deletable.
   Map each `roll` to a target skill (`ls ~/code/skills/skills
   ~/.copilot/skills`).
4. **Roll — stitch into the prose, never append a log.** Weave each fact into
   the most relevant existing section of the target skill (a rule, a pitfall, a
   workflow step, a prerequisite), matching the skill's own voice and structure.
   Do **not** paste memories into a `## Field notes` block at the bottom — that
   reads as a foreign log rather than part of the skill. Add a new section only
   when the fact is substantial and no existing section fits. **Public-repo
   skills (`~/code/skills/skills`) must stay universal:** strip usernames,
   machine paths, one-off repo names, and personal preferences, and phrase the
   lesson so anyone could apply it; if a fact is inherently personal or
   build-specific, route it to a local skill (`~/.copilot/skills`) instead of
   the public repo (extracting any general lesson for the public skill first).
   Local skills may keep personal/build-specific detail. Drop facts already
   covered by the skill's prose. Validate each skill:
   `skill-manage/scripts/validate-skill.sh`.
   For a new local skill, stamp schema-v2 provenance with
   `skill-review/scripts/mark-agent-created.sh --created-by memory-curator`
   using `memory-curator` as the evidence source. For an existing marker-backed
   skill, append the rolled
   evidence with `skill-review/scripts/append-skill-evidence.sh`. Never add an
   authority marker to a hand-made skill.
5. **Review before committing.** Rolling grows skills, so hold each edited
   skill to `writing-great-skills` in this repo and run `dual-review` on the
   diff. Rolls are where sediment accumulates and no human reads the diff.
   Apply what the reviewers agree on; where they conflict, take the reading
   that removes duplication.
6. **Commit** both roots (`~/code/skills` public, `~/.copilot/skills` local).
7. **Collision-check** the delete list against the keep-allowlist (must be 0).
8. **Delete**: `mem-delete.sh -f /tmp/delbodies.json`.
9. **Ledger**: `mem-ledger.sh add rolled <target> "<body>"` for each.
10. **Re-extract** and repeat until the window is empty or only keepers remain.
11. **Surface** the categorized list to the user before deleting when running
    interactively.

## Provenance

Skills that already exist absorb the fact into their prose; only genuinely new
topics warrant a new skill (respect the `skill-curator` umbrella preference — a
small library of broad skills beats a sprawl of micro-skills). Agent-created
local skills carry `.agent-created` markers.
