# Concurrency, writer lifecycle, and actor topology lens

Read this lens when the work claims or retains concurrency, fencing, locking,
leasing, or coordination machinery, or when an active scope node persists or
coordinates state even though no concurrency is claimed. Record the result
under `lens_findings.concurrency`.

## Writer lifecycle is the single record

Describe each logical writer or execution once in `writer_lifecycle`: how it is
created, when it can remain active, how a retry or resume starts one, and how
termination, cancellation, or lease expiry ends its authority. Cite the
scheduler and lifecycle evidence that permits or excludes overlap. Actor
entries reference these lifecycle records rather than restating them.

Where scheduler or lifecycle evidence is unavailable, record the lifecycle as
`UNKNOWN`, leave any existing integrity control in place, and name the missing
evidence.

## Prove overlap before crediting coordination

For any claimed coordination, name the actual actors or executions, the
reachable overlap, and the concrete failure their interleaving causes.

- Retries, resumed or restarted attempts, at-least-once delivery, and stale
  in-flight predecessors are candidate actors, not proof of overlap. Cite
  evidence that two executions can remain active against the same state.
- Platform-serialized execution does not justify multi-writer machinery.
- Cancellation rules out overlap only when evidence shows termination is
  synchronous and effective before another writer starts.
- An authority-anchored second writer with a named triggering event may justify
  coordination before that event; record the authority and reachable overlap.
- Hypothetical future callers do not justify present machinery.

## Actor topology per protected resource

For each active node's persistence or coordination mechanism, record the
complete actor topology per protected resource or effect. Defer other material
mechanisms through `scope_tree.deferred` with their rank and reason. One
sequential owner does not justify multi-writer coordination. A service,
adapter, broker, or transport that executes one owner's command is not an
independent writer unless it can initiate a competing mutation. Vague
categories such as other callers, policies, or future consumers are missing
evidence, not actors.

An unknown actor topology cannot support retaining or expanding coordination
machinery. Hold the machinery and name the evidence needed.

## Transactional effects narrow the protection

A transactional stale-completion boundary may protect one named effect while
overlap remains reachable elsewhere. Record that narrower protection per active
node: the boundary, the single effect it protects, and the effects it does not.
The node's removal counterfactual must then cover every other read, write,
external call, and duplicate side effect under that node, not only the
protected effect. Defer other material transactional boundaries through
`scope_tree.deferred`.

## Record

```text
lens_findings:
  concurrency:
    writer_lifecycle:
      - writer_id:
        creation:
        active_window:
        retry_or_resume:
        termination:
        overlap_evidence:
    actors:
      - node_id:
        protected_resource:
        writer_ids:
        overlap_reachable: YES | NO | UNKNOWN
        duplicate_execution_outcome:
    actor_topology:
      - protected_resource:
        independent_writers:
        excluded_intermediaries:
    transactional_effects:
      - node_id:
        boundary:
        protected_effect:
        unprotected_effects:
```
