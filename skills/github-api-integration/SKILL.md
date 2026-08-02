---
name: github-api-integration
description: GitHub REST + GraphQL API gotchas that look like your bug but aren't. Use when building or debugging code that calls api.github.com or api.*.ghe.com, wiring GitHub sign-in (OAuth App, GitHub App, device-code), enumerating enterprises/orgs/repos, or hitting "Resource limits for this query exceeded", null enterprise/org nodes, or scope/SSO errors.
author: skill-review
---

# github-api-integration

Durable gotchas for talking to GitHub's APIs from an app (works for both
`github.com` and `*.ghe.com`). These are failure modes that look like bugs in
your code but are actually GitHub-side behaviors with known workarounds. Reach
for this before inventing a theory about why a query "randomly" fails.

## GraphQL: "Resource limits for this query exceeded"

GitHub's GraphQL endpoint enforces a **query-complexity budget**, not just a
rate limit. The classic trigger is a **fan-out subquery**: asking for one nested
field *per item* in a list — e.g. `repositories(first:0){totalCount}` under
every org in a single query. With enough orgs that's dozens of nested
connections in one request and you get one "Resource limits for this query
exceeded" error per item.

**Fix:** do not fan out. Split into **per-item lightweight queries** run
**sequentially** (top-down), caching results. One org's count query —
`organization(login:"x"){repositories(first:0){totalCount}}` — is cheap and well
under budget when issued alone. Sequential prefetch also avoids head-of-line
blocking: don't let one giant org (many paginated round-trips) stall the queue
for smaller orgs behind it; fetch a cheap count first, defer the full list.

## Sign-in: OAuth App vs GitHub App scopes behave differently

- **OAuth Apps** honor the `scope=` parameter at sign-in. Adding a scope (e.g.
  `read:enterprise`) to the authorize URL and re-authing Just Works. The consent
  screen shows real scope names ("Full control of your repositories").
- **GitHub Apps** **ignore** the `scope=` param entirely. Permissions are
  **pre-declared on the App settings** and granted at install/authorize time.
  Tell-tale signs you're dealing with a GitHub App: generic consent wording
  ("Verify your identity / Act on your behalf") and "has not been installed on
  any accounts." Changing your `scope=` string changes nothing — you must edit
  the App's declared permissions, then re-authorize.

Diagnose which one you have *first*; otherwise you'll chase a scope bug your code
can't fix.

### Device-code flow (desktop/CLI sign-in with no redirect URI)

Request device + user codes, show the `user_code` + `verification_uri`, then
poll for the token — but **bound the poll**:

- Poll `/login/oauth/access_token` no faster than the **`interval`** the
  device-code response returned. On a **`slow_down`** error, increase that
  interval by **at least 5 seconds** for all later polls. Stop when the code
  expires (**`expired_token`**) or the user denies (**`access_denied`**).
- Tie the loop's lifetime to the code-entry UI: if the user dismisses the popup
  without entering the code, **stop polling** — otherwise the UI hangs on an
  "authenticating" spinner forever.
- Persisting the token to the macOS keychain can fail with `item already exists`
  (a stale entry from a prior attempt) or `User interaction is not allowed`
  (locked keychain / no UI session). To overwrite safely, delete then re-add the
  entry pinned to **both** its service **and** account identity
  (`security delete-generic-password -s <service> -a <account>`) so you never
  destroy an unrelated credential; treat "already exists" as "overwrite," not a
  hard failure. If no credential store is available at all, report
  `CREDENTIAL_STORE_UNAVAILABLE` and stop rather than silently continuing
  without persistence.

## viewer.enterprises returns null nodes (scope/SSO redaction)

Querying `viewer.enterprises` can return a non-zero **count** while every
`EnterpriseNode` in `nodes` is `null` — e.g.
`{"viewer":{"enterprises":{"nodes":[null,null,null,null]}}}`. This is **not** a
parse bug; it's GitHub's "you can see that it exists but not read it" response.
Two causes:

1. **Missing `read:enterprise` scope** (OAuth App) or missing enterprise
   permission (GitHub App).
2. **SAML SSO authorization** not granted on the OAuth App for the enterprise's
   underlying orgs — nodes stay `null` even *with* `read:enterprise`.

**Handle it gracefully:** detect `count > 0 && all nodes null` and surface a
clear "your sign-in is missing `read:enterprise` (or SSO authorization) — sign
out and back in to re-authorize" message, not a raw JSON-parse error. The same
null-node pattern appears for individual `organization(...)` nodes behind SSO.

## Data-residency tenants: the host and the token must agree

`ghe.com` tenants are a different host from github.com, and every tool defaults
to github.com. An un-hosted `gh issue create`, `gh api`, or clone against a
tenant repo fails with **"Could not resolve to a Repository"** — which reads
like the repo is missing rather than like the host is wrong. Set
`GH_HOST=<tenant>` or pass `-h <tenant>`. The `gh` keychain service name follows
the host, as `gh:<host>`.

The Copilot CLI needs the same treatment: set `COPILOT_GH_HOST` or `GH_HOST`,
or run `copilot login --host <tenant>`. Without it the CLI defaults to
github.com and 401s a tenant token.

A **401 on `/info/refs?service=git-upload-pack`** proves the credential was
*rejected*, not *absent* — the usual cause is a github.com token sent to a
tenant remote, or the reverse. Do not chase it as a missing-credentials problem.
Authenticate git through `gh auth setup-git --hostname <host>`; the
`http.extraheader` bearer-token trick is rejected by tenant hosts as invalid
credentials.

## 404 on private resources hides the auth-vs-permission distinction

GitHub returns **HTTP 404 (not 401/403)** for both *unauthenticated* and
*unauthorized* access to a private resource, deliberately, so it never discloses
that the resource exists. On a private web or JSON endpoint, a logged-out session
and a signed-in-but-unpermissioned session **both** look like 404 — so status
code alone cannot distinguish an expired session from a missing permission.

To disambiguate, **probe a known-accessible resource first**: hit an endpoint the
current identity is definitely entitled to (e.g. an authenticated root page whose
HTML carries a `user-login` marker). If that probe shows you're authenticated, a
later 404/403 on a locked-down endpoint means **permission-denied**, not session
expiry; if the probe itself fails, the session is logged out/expired.

## Make API errors actionable, not scary

Several GitHub error families are normal operating conditions, not breakage —
catch and humanize them at the UI boundary instead of dumping raw strings:

- **IP allow list**: `the 'X' organization has an IP allow list enabled, and
  your IP address is not permitted...` — org policy, per-org. Show a "IP
  restricted" badge, not a wall of GraphQL errors. (Returns HTTP 200 with errors
  in the body, so check the GraphQL `errors` array even on 200.)
- **Unauthorized: Invalid or expired token**: usually a token minted for the
  wrong host (a `*.ghe.com` token sent to `api.github.com` or vice versa) — keep
  host and token strictly paired.
- **GraphQL JSON parse error**: before theorizing, inspect the actual response
  shape (is it HTML, a different shape, or null nodes?). Most "parse errors" are
  really redacted nulls. Error bodies can carry tokens or private metadata, so
  redact before surfacing — see [`secret-hygiene`](../secret-hygiene/SKILL.md)
  for the canonical rules; do not echo a raw body.

## Pagination & search correctness (REST)

- `/orgs/{org}/repos` (and similar) paginate at up to **100 per page**; an org
  large enough to span many pages is many round-trips — budget for it or defer
  it.
- Watch for a **paginator that hard-codes `per_page`** (e.g. 50) and silently
  overrides a caller's 100 — `max_pages * per_page` then caps results lower than
  intended (5x50 = 250, not 500), and any "truncated?" check keyed on a higher
  threshold never fires. Keep `per_page`, `max_pages`, and the truncation
  threshold consistent across the call path.
- **REST search API** is rate-limited to **30 req/min per user**. With no `in:`
  qualifier it matches a repository's **name, description, and topics** (README
  only with `in:readme`; never code) — fine for a picker, not exhaustive
  enumeration. "Instant" results over a huge org usually mean you're searching a
  locally-cached/first-page subset, not live.

## Org repo ownership & enumerating who has admin

A repo's **creation path** decides its initial ownership — and that bites later
when someone needs admin:

- A repo created **via the API / `gh` CLI** under an org (e.g.
  `gh repo create org/name`) is **ownerless by default** — no owning team is
  assigned, and the human creator is **not** automatically an admin. Admin then
  lives only in the org's owner/admin teams. The creator can end up with mere
  `push`/`triage` via some inherited team and be unable to reach
  **Settings -> Collaborators and teams** at all.
- Creating the same repo **via the web UI** forces an **owner-team picker** at
  creation time, so ownership is explicit from the start. Assign a team
  immediately after a CLI create if you want a clear owner.

**Enumerating who has admin as a non-admin is mostly blocked by the API.** The
team/collaborator/branch-protection endpoints (`/repos/{o}/{r}/teams`,
`/orgs/{o}/teams`, admin collaborator lists, org-owners list) **404 or redact**
for a viewer without admin/`read:org`. Don't read those 404s as "no admins
exist" — they mean "you can't see them."

A `GET /users/{login}` **404 is not "no such account"**: an account with a
hidden/private profile 404s there yet remains a valid recipient for a
`PUT /repos/{o}/{r}/collaborators/{login}` invite — 404 means "not visible," not
"nonexistent."

## Enterprise enumeration & policy surfaces

Enumerating Copilot seats, licenses, or agent activity across an enterprise, or
checking which enterprise/org policy surfaces have a REST API vs are UI-only?
See [`references/enterprise-enumeration.md`](references/enterprise-enumeration.md)
— reconcile-to-total pagination, seat/license endpoints, audit-log scope by
host, and the rulesets/custom-properties policy engine.
