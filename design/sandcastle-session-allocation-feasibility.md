# Sandcastle Copilot Session Allocation Feasibility

**Frozen source:** `mattpocock/sandcastle@e99f832f26dc9d245c019a9ddd19fa5dee792427`  
**Package:** `@ai-hero/sandcastle@0.12.0`  
**Result:** `PROVEN FEASIBLE`

## Question

Can the frozen Sandcastle adapter force every top-level Copilot model invocation
through evaluator-owned session-ID allocation without changing the workflow
prompts or phase ordering?

## Source observations

1. `AgentProvider` is a public interface. Its `buildPrintCommand` method returns
   the exact command executed for one agent invocation.
   Source:
   `src/AgentProvider.ts`, frozen revision above.
2. Sandcastle's Copilot provider builds
   `copilot -p ... --output-format json --model ...` but does not supply
   `--session-id`.
3. `sandbox.run` receives one `AgentProvider`; the orchestrator calls
   `invokeAgent` once per iteration using exactly that provider.
   Source: `src/Orchestrator.ts`.
4. `sequential-reviewer/main.mts` calls `sandbox.run` once for the implementer
   and, only after an implementation commit, once for the reviewer. Each call
   has `maxIterations: 1`.
5. Copilot CLI accepts evaluator-selected `--session-id`; the existing
   repository-task evaluator already uses that option for every direct
   candidate.
6. Existing measurement semantics count nested Copilot agents in the parent
   session's cumulative total rather than as additive top-level charges.
   Source: `skills/skill-evaluation/references/measurement.md`.

## Bounded adapter

The evaluator allocates one UUID for the implementer and one for the reviewer
before the external command starts and provides them through non-secret
environment variables.

The frozen Sandcastle adapter:

1. creates the published `sandcastle.copilot("gpt-5.6-sol-fast")` provider;
2. wraps `buildPrintCommand` without changing its prompt, model, effort,
   permissions, stream parser, or environment;
3. appends the evaluator-allocated `--session-id UUID` to that command;
4. uses the implementer wrapper for the implementation `sandbox.run`;
5. uses the reviewer wrapper for the review `sandbox.run`; and
6. writes the launched IDs and Sandcastle results to the bounded treatment
   result.

The adapter sets the outer iteration limit to one for the one-task evaluation.
This is a disclosed benchmark adapter: it prevents a second empty-backlog model
call after the single fixture issue is closed. It does not change the
implementer or reviewer workflow for that issue.

## Completeness rule

For this adapter, the evaluator owns the complete set of possible top-level
session IDs:

- implementer: always allocated and expected to launch;
- reviewer: allocated before execution and expected to launch only when the
  retained Sandcastle implementation result contains at least one commit.

Complete candidate credits require:

- the expected launch set derived from retained Sandcastle results;
- matching terminal event files for every expected evaluator-owned UUID;
- no duplicate or wrong-model session;
- successful post-stop collection; and
- the existing measurement collector accepting terminal credit coverage.

Any mismatch remains partial or invalid according to execution stage. The
candidate-authored result alone never establishes coverage.

## Deliberate differences from upstream

- Claude provider replaced with the published Copilot provider.
- Provider wrapped only to add evaluator-owned session IDs.
- Nested Docker provider replaced by outer evaluator isolation with no Docker
  socket.
- Outer issue-loop count fixed to one for a one-task benchmark.
- Fixture-local issue listing and close commands replace a public tracker.

The report names this adapted treatment
`sandcastle-sequential-reviewer-copilot-outer-isolated`. It does not claim an
exact replay of the upstream Docker topology.
