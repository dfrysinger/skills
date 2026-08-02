# Guardrail patterns

Worked examples for `guardrails`. Read when writing a guard.

## Structure drift guards, strongest first

The order matters: it follows the contract ladder in `shipping`.
Reach for the weakest technique only when the stronger ones cannot express the
rule.

**Dependency contract.** "The core layer never imports an infrastructure
adapter" → an import-linter contract that fails the build on a forbidden
dependency edge. Strongest: it names the boundary directly and cannot be
satisfied by renaming.

**Symbol assertion.** "The adapter registry is exactly `{mock, remote, local}`"
→ import the tuple and assert its contents. When an agent adds an unapproved
`extra`, the build goes red. Strong: it reads the real runtime object rather
than the text that produced it.

**Vocabulary match, as a temporary ratchet.** "The core engine carries no
scanner vocabulary (`scan_types`)" → a test that greps or AST-parses the core
package and fails on a match. Weakest, and the most prone to firing on
legitimate code in another layer. Use it to stop the bleeding while a stronger
guard is built, and record what would replace it.

## Behavior drift guards

**Matrix conformance.** Pin the whole table in one test: a per-mode
security/capability matrix asserted end to end, so no backend can start
silently faking a lever. Behavior guards answer "does the system still act to
contract", which structure guards cannot see.

## The trap: banning a word instead of a role

A system distinguishes **point-like** data (a single moment) from
**range-like** data (an interval T0→T1). An agent hits a failing overlap check
and collapses a point into a degenerate interval so the check passes. The test
goes green, the local module is correct, and the cross-component invariant
"point is not an interval" is gone. The next agent inherits the confusion.

The same shape appears when writing the guard. A vocabulary match on
`scan_type` is legitimate in one layer and forbidden in another. *Scanner as a
workload the engine runs* is the violation; *security validators as an
output-governance gate* is correct usage of the same word. A guard that bans
the word rather than the role fails the build on correct code.

State the role boundary in the invariant, and pin a near-boundary legitimate
case that stays green.
