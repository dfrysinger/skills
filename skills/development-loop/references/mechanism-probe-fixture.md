# Mechanism-probe behavioral fixture

Use this fixture when reviewing changes to the mechanism-probe rule in
`development-loop`.

## Scenario

A Windows WebView API call reports success, but the visible document does not
change. Unit tests prove ownership, acknowledgement, retry, and close-timer
state transitions. The failed WebView is still running, and a CDP evaluation
route can execute JavaScript and read the resulting title, marker, and body.

## Expected routing

The workflow:

1. records that API success and visible document replacement are different
   claims;
2. states one hypothesis about document replacement and one distinguishing
   DOM observation;
3. uses the existing CDP route to run one reversible replacement probe against
   the failed WebView;
4. keeps or rejects the mechanism from the DOM readback;
5. probes marker publication separately if the close path remains uncertain;
6. resumes section 1, classifies the authentication and shared-ownership change,
   and satisfies its design and durable-contract requirements before editing;
7. makes the smallest production edit that matches the observed mechanism;
8. runs focused regression checks, then the complete live acceptance flow
   before review.

It must not choose another production patch, native rebuild, retry layer,
timeout, ownership protocol, or abstraction before the direct probe settles
the uncertain mechanism.

## Passing criterion

The fixture passes when an agent given the scenario chooses the CDP mechanism
probe before another production edit or rebuild, resumes section 1 to satisfy
the lane's design and durable-contract requirements before editing, and still
requires complete live acceptance after the mechanism succeeds.
