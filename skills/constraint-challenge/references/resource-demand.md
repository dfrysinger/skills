# Resource demand lens

Read this lens when a capacity, latency, quota, cost, or other resource
boundary motivates the work. Record the result under
`lens_findings.resource_demand`.

## Derive the demand equation

Trace the supported workload to the resource under pressure and write the
demand as an equation from that workload to that resource. Name every
multiplicative architecture factor between them: fan-out per request, retries,
duplicated representations, per-component copies, per-platform lanes, polling
frequency, and any other factor that multiplies one unit of supported workload
into many units of resource consumption.

## Rank the factors before touching the boundary

Rank the factors by size, then by provenance weakness. The largest weakly
authorized factor is the load-bearing one; it gets a scope-tree node and enters
the ranking in the main workflow. Raising the boundary or optimizing a leaf
operation while a larger weakly authorized factor stands is not a
minimum-design result.

## What a limit proves

A higher limit already accepted by the implementation is an available maximum.
It is not measured demand, and it is not authority to preserve the architecture
that multiplies the demand. Measured demand is observed workload evidence tied
to the supported journey.

Where the bounded packet contains no workload measurement and no external
obligation fixing the boundary, record the demand equation with the unmeasured
terms named and return the dependent necessity as `UNKNOWN` with those terms as
the decisive missing evidence.

## Record

```text
lens_findings:
  resource_demand:
    resource:
    supported_workload:
    equation:
    factors:
      - factor:
        multiplier:
        authority_anchor:
        provenance_strength:
    largest_weakly_authorized_factor:
    measured_demand_or_missing_evidence:
```
