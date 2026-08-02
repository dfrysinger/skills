# CURATOR_DRY_RUN_BANNER — verbatim from Hermes Agent

Source: [`agent/curator.py`](https://github.com/NousResearch/hermes-agent/blob/main/agent/curator.py),
constant `CURATOR_DRY_RUN_BANNER`.

Print this block first, verbatim, at the start of every `--dry-run` pass. It
is the hard guard that gates mutation: the curator prompt instructs you to
refuse all mutating actions while it is in effect.

```
═══════════════════════════════════════════════════════════════
DRY-RUN — REPORT ONLY. DO NOT MUTATE THE SKILL LIBRARY.
═══════════════════════════════════════════════════════════════

This is a PREVIEW pass. Follow every instruction below EXCEPT:

  • DO NOT call /skill-manage with action=patch, create, delete,
    write-file, or remove-file.
  • DO NOT call bash to mv skill directories into .archive/.
  • DO NOT call bash to mv, cp, rm, or rewrite any file under
    ~/code/skills/skills/.

  • Read tools (view, grep, glob, find-skill.sh) are FINE — read as much
    as you need.

Your output IS the deliverable. Produce the exact same human-readable
summary and structured YAML block you would produce on a live run — but
describe the actions you WOULD take, not actions you took. A downstream
reviewer will read the report and decide whether to approve a live run
with `/skill-curator --live`.

If you accidentally take a mutating action, say so explicitly in the
summary so the reviewer can revert it.
═══════════════════════════════════════════════════════════════
```
