# Boundary and composition lens

Read this lens when an active scope node exposes a custom API, service, store,
broker, or protocol, or when the minimum design composes capability-ledger
candidates across an interface. Record the result under
`lens_findings.boundary_composition`.

## Split a boundary before comparing it

List the operations and semantics the boundary exposes, then split it into
independently authorized operation families. One valid responsibility does not
justify unrelated operations that happen to share its process, service, or
credential. Compare each family separately and account for every family; a
family left unexamined is `UNKNOWN`, not implicitly justified.

## Mirror each family against a native provider

For each operation family, find any capability-ledger candidate that provides
the same required effect or property natively, and name the verified required
property the custom family adds beyond it. The native path need not reproduce
the incumbent abstraction. Where wiring or lifecycle evidence for the native
path is missing, record it as `MAY_PROVIDE` and return the family's necessity
as `UNKNOWN` rather than omitting the path.

A proposed but unbuilt custom boundary that adds no independently required
property is not the minimum design; mark its necessity `FAILED`. Existing
dependencies establish that it can be built, not that it is needed.

Record each material operation family's `node_id`. In section 4.2, carry the
same `necessity_status` into an active node or retain it in this lens result
when the node is deferred. Either form participates in the verdict; do not
average a failed or unknown family into a supported parent boundary.

## Trace every composition edge

For each edge in the composed path, cite the existing supported interface and
trace four things across it: authority, data flow, lifecycle, and failure
semantics. Where the packet cannot show the candidates compose without a new
boundary or a weakened control, mark the path `UNKNOWN`.

## Splitting changes trust

When this lens recommends moving an operation family out of a shared boundary,
run the checks in [`trust-transfer.md`](trust-transfer.md) for the family's
post-split authority. The replacement must preserve or narrow credential and
capability distribution; a simpler component graph does not justify granting
authority to more callers.

## Record

```text
lens_findings:
  boundary_composition:
    boundaries:
      - node_id:
        operation_families:
          - family:
            operations:
            native_candidate_id:
            native_disposition: PROVIDES | MAY_PROVIDE | NOT_RELEVANT
            added_property_or_none:
            necessity_status: SUPPORTED | FAILED | UNKNOWN
    composition_edges:
      - from_candidate_id:
        to_candidate_id:
        interface:
        authority_trace:
        data_flow_trace:
        lifecycle_trace:
        failure_semantics_trace:
        status: TRACED | UNKNOWN
```
