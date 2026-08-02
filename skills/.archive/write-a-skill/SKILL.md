---
name: write-a-skill
description: Generic mechanics of scaffolding a skill — folder, SKILL.md template, scripts.
disable-model-invocation: true
---

# Writing a skill

This skill is the **mechanics** of creating a skill. For the principles — what
makes a skill good (invocation, information hierarchy, pruning, leading words,
failure modes) — read the `writing-great-skills` skill and its `references/GLOSSARY.md`
(`../writing-great-skills/SKILL.md`). Apply those principles as you draft; don't
restate them here.

## Process

1. **Gather requirements** — what task/domain the skill covers, which use cases
   it must handle, whether it needs executable scripts or just instructions, and
   any reference material to bundle.
2. **Draft** — write `SKILL.md`, push overflow reference into linked files, and
   add scripts for deterministic operations. Judge every line against
   `writing-great-skills` (relevance, no-ops, duplication, sprawl).
3. **Review with the user** — present the draft; confirm it covers the use
   cases and that nothing is missing or over-detailed.

## Folder structure

```
skill-name/
├── SKILL.md           # required
├── REFERENCE.md       # disclosed reference, if SKILL.md would sprawl
└── scripts/           # utility scripts, if deterministic ops are needed
    └── helper.js
```

## SKILL.md template

```md
---
name: skill-name
description: What it does. Use when [specific triggers].
---

# Skill Name

## Quick start
[Minimal working example]

## Workflow
[Ordered steps, each ending on a checkable completion criterion]

## Reference
[Facts/rules, or a pointer to a disclosed file: See [REFERENCE.md](REFERENCE.md)]
```

The `description` is the invocation trigger — see `writing-great-skills` for how
to word it. Hard limits: **max 1024 chars**, third person, first sentence states
what it does, second sentence starts "Use when …". Set
`disable-model-invocation: true` for a user-invoked skill (no description reach,
zero context load).

## When to add scripts

Add a script when the operation is deterministic (validation, formatting), when
the same code would otherwise be regenerated each run, or when errors need
explicit handling. Scripts save tokens and beat generated code on reliability.

## Review checklist

- [ ] `description` states what it does and lists concrete triggers
- [ ] Principles from `writing-great-skills` applied (no no-ops, no duplication,
      reference disclosed, no sprawl)
- [ ] Completion criteria are checkable
- [ ] No time-sensitive info; consistent terminology
- [ ] References one level deep
