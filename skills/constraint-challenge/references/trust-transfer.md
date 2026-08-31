# Trust transfer lens

Read this lens for every `security` requirement; whenever a control moves
across callers, actors, or operations; and whenever the necessity or removal
safety of a security, integrity, or trust-boundary control is unresolved. This
includes a proposal extending an existing control to a new caller, an inherited
rule retained for a different operation, a simpler path that reuses a control,
or an operation family recommended out of a shared boundary. Record the result
under `lens_findings.trust_transfer`.

## Trace each security requirement

A `security` requirement records, beyond its common fields: the protected
asset, the untrusted actor, the harmful capability and its reachable path, the
actual enforcement point, the code, policy, platform behavior, or refusal
evidence that proves that enforcement, a narrower control that stops the same
threat when one exists, and the measurable residual risk after narrowing.
Persist it as the requirement's `security_trace`.

A control on a security, integrity, or trust boundary is held rather than
failed unless this trace shows the protected risk is unreachable, or another
supported control preserves the property through the transition.

## Run one test per transfer

A control belongs to a trust domain, not to a catalogue of reusable
restrictions. For each transfer, record both sides:

- **Origin** — the original actor, the operation, the reachable threat, the
  authority owner, the enforcement point, and the control itself.
- **Candidate** — the candidate actor and operation, and whether the same
  threat remains reachable there.

Then decide one outcome: retain the control, narrow it, or remove it.

## What does not make domains equivalent

- Similar side effects. Two operations that eventually affect the same asset
  are not the same trust domain.
- Shared implementation, process, credential store, or transport.
- A restriction inherited from an untrusted actor being applied to a trusted
  actor whose authority for that operation is independently established.

Where the threat is not reachable for the candidate actor, retaining the
control adds scope without adding a required property; narrow or remove it and
record the residual risk.

## Splits must not widen authority

For a transfer created by moving an operation out of a shared boundary, the
post-split arrangement must preserve or narrow credential and capability
distribution. Where it grants authority to more callers, the split fails this
lens regardless of how much component graph it removes.

Record each transfer's material `node_id`. In section 4.2, `WIDENED` assigns
that node `FAILED` unless an authority anchor requires the wider distribution;
an unknown threat or distribution assigns it `UNKNOWN` and holds the control
pending evidence. The lens result remains verdict-bearing when the node is
deferred.

## When evidence is missing

Where the packet cannot establish whether the threat is reachable for the
candidate actor, record the transfer as `UNKNOWN`, leave the control in place,
and name the decisive missing evidence.

## Record

```text
lens_findings:
  trust_transfer:
    - transfer_id:
      node_id:
      origin_actor:
      origin_operation:
      origin_threat:
      authority_owner:
      enforcement_point:
      control:
      candidate_actor:
      candidate_operation:
      threat_reachable: YES | NO | UNKNOWN
      outcome: RETAIN | NARROW | REMOVE | UNKNOWN
      credential_distribution: PRESERVED | NARROWED | WIDENED | UNKNOWN
      necessity_status: SUPPORTED | FAILED | UNKNOWN
      residual_risk_or_missing_evidence:
```
