# Superseded validation objective

The original Windows validation objective assumed that an unqualified mailbox
was a shared live broadcast and that acknowledgements mutated a OneDrive-backed
queue. That architecture is no longer the product contract.

The current local-first architecture and acceptance criteria are authoritative
in [`windows-cross-computer-mailbox-addressing.md`](./windows-cross-computer-mailbox-addressing.md).
Unqualified mail is local-only. Qualified `name@machine` mail crosses computers
through immutable transport files, is imported into the recipient's local
mailbox, and is acknowledged locally.
