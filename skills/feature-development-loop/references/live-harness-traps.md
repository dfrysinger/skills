# Live-harness traps (CI / shell / API-driven E2E)

These are concrete failure classes that bite when the E2E is driven by a shell
script or runs against a remote API (CI pipelines, agent loops, GitHub
automation). They are the detailed backing for the general "make the harness
fail closed" and "clean up artifacts" pitfalls in `SKILL.md`. App- and
web-development E2Es usually won't hit the bash-specific ones, but the
fail-closed and fixture/cleanup principles still apply.

## Harness self-report is not evidence

A scenario script can print "passed" while having aborted before its real
assertion. Always verify the real end state out-of-band — query the system's
actual state (PR/issue state via API, a database row, a rendered UI, a file on
disk) rather than trusting the runner's final message.

## Fail-open test integrity (bash)

On a `set -u` abort, bash 3.2 hands the `EXIT` trap `$?=0`, so successful
cleanup commands mask the abort into a false pass. Guard with a sentinel set
*only* after the main body returns normally, and have the trap
`exit "${RESULT:-1}"` — fail closed on any abort. Verify the three cases:
pass→0, real-fail→1, abort→1.

## Shell quoting / multibyte traps

A multibyte char (e.g. `…`) placed immediately after `$VAR` can be folded into
the parameter name under bash 3.2, yielding an unset-variable `set -u` abort.
Brace-delimit (`${VAR}`) and prefer ASCII in scripts that run on the live host.

## Relative-path resolution off by a level

Scripts that derive a repo root via `dirname`/`../..` break when the file moves
or the depth is miscounted; a shared `include`/library path silently 404s.
Verify the resolved path, not the arithmetic.

## Non-gating steps that can still abort under `set -e`

A best-effort provenance/log step placed *after* the real assertions can abort
the whole run on a transient API error, flaking an already-passing scenario to
failure. Scope `set +e`/`set -e` around it and `return 0`.

## Consumable fixtures

If the E2E mutates a fixture, restore it idempotently *before* filing the next
run: fetch current content+sha together, only patch if the expected pre-state
holds, fail closed otherwise. Don't blind-rewrite.

## Async cleanup leaks

Workers can open a PR (or create a record) *after* your scenario aborted and
cleaned up. Record created identifiers as soon as they exist so the cleanup trap
can reclaim them, and do a post-run sweep.
