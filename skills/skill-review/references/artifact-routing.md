# Artifact routing contract

Route a lesson before changing persistent state. Record exactly one destination
and a short reason in the skill-review ledger even when no artifact is written.

| Destination | Choose when | Completion |
|---|---|---|
| `instruction` | A stable owner rule should influence nearly every relevant turn. | Record a recommendation; M1 does not edit always-loaded instructions. |
| `factual_memory` | A concise current fact or preference may change and the owner is likely to ask about it again. | Record a recommendation; M1 does not write memory. |
| `skill` | A reusable procedure has a trigger, ordered policy, observable stop, and clear interface. | Reuse or patch an umbrella before creating one; append evidence. |
| `support_file` | Reference, template, script, or reproduction material serves an existing skill. | Add one pointer from `SKILL.md`; append evidence to the owning skill. |
| `discard` | The observation is transient, duplicated, unsupported, or too narrow to reuse. | Record the reason and write no artifact. |

## Decision order

1. Separate procedures from changing facts. A fact that a skill needs becomes a
   claim with a verification method, not factual memory.
2. Search loaded skills and both managed roots. Reuse before patch, patch before
   support file, and support file before a new umbrella.
3. Choose `skill` only for a procedure likely to recur. A smooth session with no
   correction or reusable technique routes to `discard`.
4. Treat ambiguity conservatively: record `discard` or a manual recommendation
   rather than forcing creation.

## Caller boundaries

- `skill-review` uses all five destinations.
- `skill-create` uses this contract to reject fact-only and one-off requests
  before authoring.
- `memory-curator` keeps `roll | dup | obsolete | keep` as its deletion
  authority. Apply this router only after `roll`, to choose the rolled
  artifact. `discard` never makes `obsolete` or `keep` deletable.

## Evidence record

Every routed ledger entry includes:

```json
{
  "destination": "skill",
  "reason": "A reusable multi-step recovery recurred",
  "task_key": "task:opaque-uuid"
}
```

The reason contains no transcript text, credentials, private URL, copied code,
or private proper noun. `destination` is one of the five values above.
