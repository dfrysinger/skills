# Superseded autopilot brief

Do not resume the former broadcast-based Windows proof from this file. Its
shared mutable mailbox assumptions have been replaced.

For any new validation run, use the architecture, failure model, and acceptance
criteria in
[`windows-cross-computer-mailbox-addressing.md`](./windows-cross-computer-mailbox-addressing.md).
The proof must keep local mail and state off OneDrive, route only qualified
addresses across computers, preserve immutable remote files, and verify local
outbox retry after remote transport failure.
