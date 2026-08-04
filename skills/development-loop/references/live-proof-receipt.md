# Live-proof receipt

Use this compact record for user-visible runtime changes. Keep it in the
existing plan, issue, handoff, or session artifact; do not add a permanent repo
document solely for the receipt.

```text
LIVE_PROOF
candidate: <clean commit, or identity covering tracked changes and every untracked build/runtime input>
running: <process/build identity and evidence mapping current running code to candidate>
scenario: <trigger through terminal user-visible result>
status: PASS | FAIL | BLOCKED | STALE | INCONCLUSIVE
excluded_outputs: <evidence/test-output paths designated before proof that cannot affect build/runtime, or none>

| checkpoint | expected | observed | evidence | result |
|---|---|---|---|---|
| <trigger> | ... | ... | <direct observation/artifact/query/user confirmation> | PASS/FAIL |
| <intermediate state> | ... | ... | ... | PASS/FAIL |
| <terminal state> | ... | ... | ... | PASS/FAIL |
| forbidden errors | none of: ... | ... | ... | PASS/FAIL |

first_divergence: <checkpoint or none>
unverified: <acceptance criteria not directly proved, or none>
covered_deltas: <post-proof delta identities accepted under SKILL.md section 6, or none>
```

`status: PASS` is valid only when every row passes, `unverified` is `none`, the
running identity still matches the candidate, and no manual workaround changed
the supported flow. A receipt with missing evidence is `INCONCLUSIVE`. A
receipt becomes `STALE` when the candidate changes unless section 6's
receipt-validity rule explicitly covers and records the delta.
