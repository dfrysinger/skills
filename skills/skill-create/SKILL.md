---
name: skill-create
description: Create reusable agent skills through a predictable authoring, validation, and review gate. Use when a user asks to make a new skill, turn a recurring procedure into a skill, or publish a skill without depending on a lifecycle or curation system.
---

# skill-create

Create a skill whose invocation and execution are predictable. This procedure
owns authoring and review; lifecycle systems may wrap it with provenance,
promotion, scheduling, or curation policy.

## When to use

- A user asks to create or publish a skill.
- A recurring procedure has a clear trigger, interface, and observable finish.
- An existing skill cannot absorb the behavior without losing its class-level
  purpose.

Route fact-only notes, one-off automation, and reference material for an
existing skill to their proper homes instead.

## Prerequisites

- `writing-great-skills` and `dual-review` are available.
- The target skill directory or repository is writable.
- Python 3 is available for the bundled validator.

## Quick start

Provide the reusable procedure, intended users, target location, and whether
the skill should be model-invoked or user-invoked. If any are unknown, resolve
them during step 1.

## Procedure

1. **Route and bound the artifact.**
   Search the available skill roots for the same trigger and procedure. Extend
   the closest class-level skill when one already owns the behavior. Otherwise
   choose the target root, audience, publishability boundary, objective, and
   non-goals for a new skill.

   **Complete when:** one destination is selected, no existing skill has a
   stronger claim, and private context is excluded from anything public.

2. **Shape the skill with the rubric.**
   Invoke `writing-great-skills` and read its glossary before drafting. Decide
   the invocation mode, name, leading word, trigger branches, information
   hierarchy, completion criteria, and any deterministic helper or disclosed
   reference the skill needs.

   **Complete when:** the authoring brief states each decision and every branch
   has an observable completion criterion.

3. **Draft one source of truth.**
   Create `SKILL.md`, putting ordered actions in the main file and conditional
   reference behind explicit context pointers. Co-locate each rule with its
   caveats. Put deterministic operations in `scripts/`, long reference in
   `references/`, reusable starting material in `templates/`, and static files
   in `assets/`. Keep optional package-level `README`, `LICENSE`, and `NOTICE`
   files at the skill root. Follow the target host's frontmatter and
   installation conventions.

   **Complete when:** every line changes invocation or execution, every
   required file exists, and no meaning is duplicated.

4. **Run mechanical validation.**
   Run:

   ```sh
   python3 <skill-create-dir>/scripts/validate_skill.py <path-to-SKILL.md>
   ```

   Resolve `<skill-create-dir>` from this active skill's own base directory,
   independent of the current working directory.

   Also run any checks owned by the target repository and exercise every
   bundled script with representative input.

   **Complete when:** every deterministic check exits successfully.

5. **Run the independent review gate.**
   Invoke `dual-review` with the full skill diff, objective, acceptance
   criteria, non-goals, target host conventions, and the
   `writing-great-skills` rubric. Apply verified `must-fix` findings and use the
   bounded follow-up rounds from `dual-review`; optional findings do not block.

   **Complete when:** both reviewer families complete and no verified,
   in-scope `must-fix` finding remains.

6. **Register, activate, and persist.**
   Add the skill to every manifest or registry required by its target hosts,
   update package versions when the repository requires them, and use each
   host's supported reload or restart path. Commit or publish only the reviewed
   inventory and preserve the repository's history policy.

   **Complete when:** the skill is discoverable on every intended host, its
   files are persistent, and the committed diff matches the reviewed diff.

## Pitfalls

- A new skill that duplicates an existing trigger creates competing sources of
  truth. Prefer the existing umbrella.
- A validator proves file shape, not prompt quality. The rubric and independent
  review remain required.
- Installation, provenance, and autonomous mutation are lifecycle policy.
  Keep them outside the reusable authoring core unless the target repository
  explicitly owns them.

## Verification

The creation gate passes only when:

1. routing, audience, invocation mode, and non-goals are explicit;
2. the draft applies `writing-great-skills` before review;
3. deterministic validation passes;
4. `dual-review` has no remaining `must-fix` finding;
5. all intended hosts discover the activated skill; and
6. the persisted inventory is exactly the reviewed inventory.
