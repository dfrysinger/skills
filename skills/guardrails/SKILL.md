---
name: guardrails
description: Compile a codebase's prose architecture rules into deterministic CI guards — architecture fitness functions — so an agent cannot quietly break a global invariant while every local test stays green. Use when a fast-moving or agent-written codebase is drifting from its intended architecture, when you want the rules in AGENTS.md or a design spec actually enforced, or when reviewing whether a refactor preserved a system's global contracts.
---

# guardrails

Compile the architecture you *want* into checks that fail the build when the
codebase **drifts** away from it.

Local correctness does not imply global alignment. An agent facing a failing
test satisfies that module's local contract while quietly destroying a global
invariant, and every local test staying green is exactly what hides it.

Two kinds of drift, held by different guards. **Structure drift** is the code
losing its intended shape, caught at build time. **Behavior drift** is the
system acting against contract, caught at runtime.

## Core rules

**Deterministic code enforces.** The agent is the thing being governed, never
the governor: an LLM can be talked out of anything. Every guard passes or fails
as plain code or config with no model in the loop.

**A guard is proven when it goes red.** Determinism alone proves nothing — a
stale path, an unmatched grep, or a vacuous assertion all pass deterministically
and manufacture confidence. A guard counts as enforcing only once it has gone
red on a deliberate violation and green on the restored tree. Step 4 owns how.

**A cheaper contract displaces a guard only by name.** A guard is permanent
maintenance, so it earns its place only when the rule is cross-cutting and
likely to drift; `development-loop` owns the ranking of contracts. When
a type, schema, or behavioral test carries the rule instead, record which one,
where it lives, and how it covers the cross-boundary failure the rule names.
Judging a guard unnecessary without naming its replacement leaves the rule
unenforced.

**The register is the single source of truth.** Maintain one document — for
example `docs/architecture/INVARIANTS.md` — of `INV-NNN` rows, each with a
one-line statement, the source rule it encodes, its owner, and a link to the
guard that enforces it.

**A row claims only the coverage it has.** An invariant stated but not yet
guarded is tagged `REGISTER-ONLY` so the register reads as backlog rather than
guarantee, and each such row names why — no technique in
[`references/PATTERNS.md`](references/PATTERNS.md) can yet express it, or its
guard is blocked on named follow-up work with an owner. A reviewer confirms
that set, so it is never a resting place the implementing agent picks alone.
The same honesty applies to a matrix row whose mode is not built: record the
gap as its own invariant.

**Weakening a guardrail takes the amendment path.** A firing guard is a
violation to restore. Three moves weaken one instead — amending the invariant,
narrowing its boundary because the guard fired on correct work, and retiring
the row altogether — and all three rest on the same judgement, made by the
agent under pressure to go green. So all three take
[`references/AMENDING.md`](references/AMENDING.md), which carries the burden of
proof. Replacing a guard with a stronger one that enforces the *same* boundary
is not a weakening and needs no ceremony.

**Fixing the guard is yours; changing the rule is the user's.** The source
document records the intent, so the split is checkable rather than a matter of
nerve: when the recorded intent still stands and the guard implements it
badly, a reviewer's agreement is enough and you finish the work. When the move
needs the recorded intent to change, only the user can authorize it — an agent
inventing the architecture it is governed by is the failure this skill exists
to prevent. A move that needs the user is recorded in the register as blocked,
with its evidence, while the rest of the work carries on.

## 1. Inventory the intended architecture

Dispatch an `explore` subagent to read the orienting docs — `AGENTS.md` or
constitution hard rules, the design spec's acceptance criteria, the capability
matrix, and the roadmap, which often already logs drift that crept in — and to
map the source tree those rules govern.

Ask it for a source index: every document it opened, the headings it read, and
each hard rule it extracted with a citation. The index is what makes its report
checkable rather than trusted.

Complete when every rule in that index is a seed row carrying an `INV-NNN` id,
its one-line statement, a citation to its source, and the code boundary it
governs — and you have reconciled the index against the register yourself, so
any document the subagent skipped or rule it dropped is found before you
continue. A row whose boundary is unresolved names the files already searched
and the question still open.

## 2. Confirm the drift is genuine

Dispatch an `explore` subagent per seed row whose governed boundary exists in
the tree, to open the real files and report what the code is doing. Roles
decide violations, not vocabulary: the same word is often legitimate in one
layer and forbidden in another.

Complete when every seed row carries a verdict — genuine drift, legitimate
role, or no code on that boundary yet, the last citing the boundary searched.
Every genuine one has its role boundary written into the invariant statement.

## 3. Ground each guard in real code

Read the module a guard will assert against, the test conventions around it,
and what the codebase already pins. Existing scattered checks get linked from
the register rather than reimplemented.

Match each rule to the strongest technique that can express it — a dependency
contract, then a symbol assertion, then a vocabulary match as a temporary
ratchet. The worked forms are in
[`references/PATTERNS.md`](references/PATTERNS.md).

Complete when every planned guard names the file it will live in, the real
symbol, import, or table it asserts against, the local command that runs it,
and the existing convention it follows — every one of them read first-hand.

## 4. Prove each guard red, then green

Write the guard, then prove it. Note the working tree's state before you start,
run the violating case, watch the guard go red for the stated reason, restore,
and watch it go green. Pin one legitimate near-boundary case that stays green
throughout, so the guard's false-positive edge is known before CI meets it.

Commit the violation as a negative fixture, mutation script, or documented
patch command beside the guard, along with the failure text it should produce,
so the proof repeats without a violating tree ever shipping. When a guard runs
only in CI, run that job against the deliberate violation and record the
failing run; the absence of a local command postpones the proof rather than
waiving it.

Complete when every guard has gone red on its violation and green on the
restored tree, its violating case is committed beside it, the working tree
carries no residue from the proof, and every register row either links to a
proven guard or carries a reviewer-confirmed `REGISTER-ONLY` reason.

## 5. Wire it in and hand back the loop

Run every guard in the required PR job, and in a pre-commit hook where one
already exists and the guard is cheap enough. State, next to the register, what
an agent does when a guard fires: read the invariant id in the failure, inspect
the boundary it names, then either restore conformance or open
[`references/AMENDING.md`](references/AMENDING.md).

Invoke `self-compact` before handing back. The register and the guards are
the baton; the drift survey and the red/green proof runs are not.

Complete when every proven guard runs in CI, each failure message names its
`INV-NNN` id, the recovery path is written where the next agent will meet it,
and the compact is submitted.
