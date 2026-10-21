---
name: arch-map
description: Map implemented architecture from source evidence. Use when creating or refreshing Mermaid call-flow diagrams, or auditing an architecture map for drift, missing returns, failure paths, or ownership boundaries.
argument-hint: "System or workflow, source revision, and output path if known."
---

# arch-map

Turn source code into a map readers can follow from entry to outcome and back.
Use this for implemented architecture; use `design-doc` for proposed changes.
Before drafting, invoke `explain` for the surrounding prose. Keep exact file
paths, symbols, and runtime labels in diagrams.

## 1. Bound the map

Identify the repository, revision or working-tree state, readers, workflows,
platforms, and target document. Infer reasonable scope from the request and
existing docs; ask only when ambiguity would change the architecture covered.
Name exclusions. Use production paths unless the request specifies otherwise.

For an audit, treat the existing document as claims to check, not as evidence.
Report corrections without editing it unless the request includes fixes.

**Complete when:** each workflow has a named trigger and expected outcomes,
and the selected source state is explicit.

## 2. Trace both directions

Before drawing, keep an evidence ledger in task notes. For each hop record the
file and symbol, source location, caller/producer, callee/consumer, edge kind,
state owner, and observable result. Include relevant request IDs, generations,
or other keys that keep concurrent work separate.

Follow success, failure, cancellation, timeout, and recovery where supported.
Trace results back through adapters, dispatchers, waiters, and subscribers.
Mark unavailable evidence explicitly rather than inventing a connection.

**Complete when:** every in-scope trigger reaches each supported outcome and
returns to its caller, or has a named evidence gap.

## 3. Draw the smallest complete set

Read [document shape](references/document-shape.md) when creating or
restructuring a document. Include a boundary overview, entry/exit table, and
ownership summary. Add focused diagrams only where ordering or ownership
would otherwise be ambiguous. Scope the overview to the requested workflows,
not every subsystem in the repository.

Use `path/to/file<br/>symbol` for implementation nodes. Identify external
systems separately. Preserve separate nodes when their authority or ordering
differs.

Give every diagram an unambiguous edge grammar:

- Solid forward arrow: direct call or **labeled** owned handoff.
- Labeled reverse arrow: result/return.
- Dotted, labeled arrow: publication, subscription, or other non-call relation.
- In sequence diagrams, `->>` is a call/message and `-->>` is its response.

Name transports at process or language boundaries and show both sides of
adapters. Explain what each subsystem owns in ordinary language.

**Complete when:** every ledger hop has a detailed home; overview diagrams
agree with it, and readers can distinguish calls, results, and messages.

## 4. Audit against source

Check every file/symbol and direct-call edge against the selected code. For
asynchronous edges, identify both producer and consumer. Check exact state and
event names, result adapters, error handling, and platform branches. Apply any
correction consistently across overview and focused views.

**Complete when:** no unsupported claim is presented as fact. For an audit,
return source-cited findings or an explicit no-drift result; list evidence
gaps separately from verified defects.

## 5. Verify renderability

Use the repository's existing Mermaid renderer. The bundled helper is an
alternative when the target repository already has `mermaid` and `jsdom`:

```sh
node <skill-dir>/scripts/validate-mermaid.mjs \
  --repo /path/to/repository --file /path/to/architecture.md
```

Resolve `<skill-dir>` from this skill's loaded location, not a particular
agent's installation layout. Use `--file -` to read Markdown from stdin.
The helper handles top-level and space-indented list fences using backticks
or tildes; move blockquoted diagrams out of quotes or use the site's renderer.
It approximates text dimensions: a successful SVG proves renderability,
not visual layout or architectural correctness.

If no renderer is available, report rendering as unverified and name the
missing tool. A parser-only check is not a rendering pass. Installing new
documentation dependencies requires the user's approval.

**Complete when:** all in-scope Mermaid blocks render, their count matches the
document, and the factual audit is complete. Otherwise deliver the map or audit
with the specific unverified checks, without claiming full verification.
