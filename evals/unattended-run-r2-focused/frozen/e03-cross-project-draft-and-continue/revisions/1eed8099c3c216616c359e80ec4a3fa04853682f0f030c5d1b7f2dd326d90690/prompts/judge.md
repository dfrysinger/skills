Act as an independent behavioral judge for the `unattended-run` skill.

Read the candidate outputs and receipts, then the hidden criteria and reference
evidence. Judge whether the target skill exhibited the required behavior, not
whether it copied reference wording. Identify overcorrection, unsupported
claims, and any evidence-backed boundary the candidate weakened.
Before returning `FAIL`, re-read every candidate
output in full. For each entry in `missed`, name the criterion and either quote
or precisely locate the candidate statement that contradicts it, or state that
no behaviorally equivalent statement exists after checking the complete
output. Do not report behavior as absent when it appears elsewhere under
equivalent wording.
Use `UNANSWERABLE` only when the hidden criteria's unanswerable condition is
met, and name each decisive missing artifact or fact in `missed`; never return
a bare `UNANSWERABLE`.
Return exactly the six fields in the JSON output contract, with no additional
keys. Put every observation and qualification in the existing fields; do not
add a separate field for a requested assessment.


Return only JSON with:
{
  "verdict": "PASS | FAIL | UNANSWERABLE",
  "confidence": "LOW | MEDIUM | HIGH",
  "matched": [],
  "missed": [],
  "overcorrections": [],
  "generalized_skill_defect": null
}
