---
name: authenticated-browse
description: Read websites that need a login. Use when a URL is behind SSO/MFA/auth that the agent can't do itself — internal repos, wikis, dashboards, vendor portals. User logs in once, agent browses after.
---

# authenticated-browse

A two-phase protocol for letting the user hand off an authenticated browser session to the agent.

1. **Auth phase (user-interactive):** A real Chromium window opens with a persistent profile. The user completes any SSO / MFA / device-trust flow manually and navigates to anything else they want the agent to be able to see. When they close the window, cookies and local storage are persisted to disk.
2. **Browse phase (agent-driven):** The agent re-opens the same profile *headlessly* and fetches rendered text, HTML, links, screenshots, or evaluates JS in page context - all as the logged-in user.

The profile is reusable across sessions until cookies expire or the user runs `purge`.

## When to invoke

### Intent signal: URL + "how do I / where is / show me" = use this skill

When the user pastes a URL alongside a navigational or page-understanding question, treat that as a strong signal they want help with the **rendered UI** of that specific URL, not a programmatic call against the same backend. Default to this skill in those cases, even when an alternative tool (API CLI, MCP, REST endpoint) could technically answer.

The principle: **respect the view the user pointed at.** They pasted the URL because they're looking at that page; substituting a different view (API JSON, CLI output, GraphQL response) is changing the question.

Trigger phrases (URL + any of):

- "How do I do X on this site / page / repo: <URL>"
- "Where is the X setting on <URL>"
- "Show me / point me to X on <URL>"
- "What does this page say / summarize this: <URL>"
- "I'm looking at <URL>, help me ..."
- "Help me navigate / find X on <URL>"

Also invoke when:

- The user explicitly mentions SSO, MFA, "behind our VPN," "internal," "private," "corp," etc.
- A `web_fetch` / `curl` probe on the URL returns HTTP 401 / 403 / 404 / a login redirect / a "this page is private" body when the user expected real content
- The user explicitly asks you to "look at" or "see" something

### When to skip this skill

- The user pasted a URL but asked for a **clearly programmatic action** against its backend: "delete the repo at <URL>", "create an issue titled X on <URL>", "list the open PRs there as JSON", "run `gh` / `aws` / `jira` / etc. against this". Use the appropriate CLI / MCP / REST tool instead.
- The user did not paste a URL at all and is asking a generic question (e.g. "how do I add a contributor on GitHub" with no URL) - answer from general knowledge unless they ask for site-specific help.
- The URL is a public page `web_fetch` can already read cleanly and text is all you need - use `web_fetch`. A screenshot is not text: when you need the rendered page as pixels, use this skill's `screenshot` subcommand regardless of whether the page needs a login.

### Don't pre-probe with alternative tools

When the user has pasted a URL with a navigational question, do **not** silently call an equivalent API/CLI/MCP first to "check" whether you can answer without the browser. Examples of the wrong pattern:

- User pastes a `github.com/...` URL → don't first run `gh api repos/<owner>/<repo>`
- User pastes a Jira/Confluence URL → don't first hit the REST API
- User pastes an AWS Console URL → don't first run `aws` describe-something
- User pastes any vendor dashboard URL → don't first try the vendor's API CLI

That kind of probe burns time and produces a different answer (structured backend data) than what the user is looking at (rendered UI). Go straight to Step 1 below.

Only reach for an alternative tool if the user explicitly redirects you ("actually just use the API" / "use gh") or if this skill's auth phase fails (e.g. bot-detection blocks Playwright).


## Underlying tool

Playwright (`chromium.launchPersistentContext`) in headed mode for auth, headless for browse. Cookies / IndexedDB / localStorage / service workers persist in the profile directory so the same login is reused on subsequent commands.

This skill does **not** store passwords, tokens, or credentials anywhere itself - it stores only whatever the site's own auth flow writes into the browser profile (typically session cookies).

## Locating the helper

The skill ships two files under `scripts/`:

- `pw-session.sh` - wrapper that lazily installs Playwright + Chromium into a user cache dir (`~/.cache/copilot-skills/authenticated-browse/`) on first run
- `pw-session.mjs` - Node script that implements the subcommands

Locate the wrapper before each command run:

```sh
PW="$(find "$HOME/.copilot/installed-plugins" -maxdepth 7 -type f -name pw-session.sh -path '*authenticated-browse*' 2>/dev/null | head -1)"
[ -x "$PW" ] || { echo "authenticated-browse skill not found on disk"; exit 1; }
```

All subsequent invocations call `bash "$PW" <subcommand> ...`.

## The helper is general; the protocol below is not

`pw-session.sh` is a plain Playwright driver. Its `fetch`, `screenshot`, and `eval` subcommands work against any URL, including a local dev server, and need no login and no profile. Another skill - `proof` captures a running UI this way - can call it directly and skip everything below.

The protocol that follows is for the branch where a person asked you to go look at a page for them. It exists to settle where to land, what to do there, and how to get through a login without a password ever reaching you.

## Protocol

### Step 1 - Confirm intent and gather inputs

You need two things before touching the browser:

1. **Starting URL** - the page to land on (login page, dashboard root, etc.). Required.
2. **Goal** - what to do once logged in (summarize a page, answer a question, extract a list, etc.) - so you know what to fetch in Step 3.

When the request or the calling skill already supplies both, proceed. When either is missing, ask for it in plain prose as part of your reply and wait for the next turn.

**Profile name is optional.** A shared `default` profile is used if none is given, which keeps the UX clean for one-off browses. Only ask the user for a profile name if any of these apply:

- They explicitly want isolation from other sites they've logged into before
- They're likely to want to keep this login alive long-term while also using `default` for unrelated browses
- They're authenticating as a different identity on a site they already have a session for under `default`

If you do ask, suggest a slug derived from the URL hostname (e.g. `corp-wiki`, `vendor-portal`). Allowed chars: letters, digits, `.`, `-`, `_`.

Show the user the cache directory path (`~/.cache/copilot-skills/authenticated-browse/profiles/<profile>/`) and note that closing the browser saves the session.

### Step 2 - Auth phase (blocking, interactive)

Check whether the chosen profile already exists:

```sh
bash "$PW" list-profiles | grep -Fxq "<profile>" && echo "exists" || echo "new"
```

(Use `default` as the profile name if you didn't prompt in Step 1.)

If the profile is new, or if a prior `fetch` returned an obvious "please log in" page, run the auth phase:

```sh
# With explicit profile:
bash "$PW" auth <profile> <url>
# Or, using the default profile (omit the profile arg entirely):
bash "$PW" auth <url>
```

This blocks until the user closes the browser window. In Copilot CLI, run it with a long `initial_wait` (e.g. 600s) and be ready to read remaining output via `read_bash` if the user takes longer. **Do not** background-detach this; the user needs the foreground window and the agent needs the exit signal.

On exit, the command prints a single JSON line on stdout: `{"profile":"...","profile_dir":"...","last_url":"..."}`. Use `last_url` as a strong hint for where the user wants you to start browsing - they likely navigated to it deliberately.

If the profile already exists and a sample `fetch` returns logged-in content, skip the auth phase entirely. Re-auth only when needed.

### Step 3 - Browse phase (agent-driven, headless)

Use these subcommands as needed. In every case, the `[profile]` argument is optional - omit it (or just pass the URL as the first arg) to use the shared `default` profile.

| Command | Purpose |
|---|---|
| `bash "$PW" fetch [profile] <url> text`  | Rendered visible text (`document.body.innerText`). Default starting point for "summarize this page". |
| `bash "$PW" fetch [profile] <url> html`  | Full rendered HTML after JS hydration. Use when you need attributes, structure, or hidden elements. |
| `bash "$PW" fetch [profile] <url> links` | JSON array of `{text, href}` for every `<a href>`. Use to discover navigation. |
| `bash "$PW" fetch [profile] <url> title` | Page `<title>`. Cheap probe to detect login redirects. |
| `bash "$PW" screenshot [profile] <url> [out.png]` | Full-page PNG. Prints the output path on stdout. Use when the visual layout matters or text extraction is insufficient. |
| `bash "$PW" eval [profile] <url> '<jsExpr>'` | Run a single JS expression in page context; result printed as JSON. Use sparingly for structured extraction (e.g. `Array.from(document.querySelectorAll('.row')).map(r => r.innerText)`). |

The wrapper distinguishes profile from URL by detecting `http(s)://` on the first positional arg, so `fetch https://example.com text` works exactly like `fetch default https://example.com text`.

Tips:

- Always probe with `title` or a small `text` fetch first when re-using a profile, to confirm you're still logged in. If you see a login page, drop back to Step 2.
- Output can be large. Pipe through `head`, `wc -l`, or save to a temp file and then `grep`/`view` it.
- The `networkidle` wait may legitimately time out on long-polling SPAs; the helper prints a warning to stderr and proceeds with the current DOM. That's usually fine - re-run with a more specific selector via `eval` if you need to wait for a particular element.
- Two commands against the same profile cannot run concurrently (Chromium user-data-dir lock). Run them sequentially.

### Step 4 - Report and clean up

Summarize findings to the user. Mention:

- The profile name (so they know how to invoke you against the same site later)
- That the session cookies remain on disk in `~/.cache/copilot-skills/authenticated-browse/profiles/<profile>/`
- How to revoke: `bash "$PW" purge [profile]` deletes that profile's persisted data (defaults to the `default` profile if omitted)

Do not delete the profile automatically - re-auth is annoying. Only purge when the user asks.

## Privacy and trust

- Auth happens in a real browser window the user controls; the agent never sees their password.
- Persisted data lives only on the user's machine, under `~/.cache/copilot-skills/authenticated-browse/profiles/<profile>/`. Nothing is uploaded by this skill.
- However, **everything the agent fetches becomes part of the conversation context** and is sent to the model provider. That includes:
  - `fetch text` - visible page text, which can include account info, names, internal data
  - `fetch html` - full DOM, which may include hidden fields, signed URLs, tokens embedded in markup or `data-*` attributes
  - `fetch links` - `href` values, which may include signed URLs and one-time access tokens
  - `screenshot` - pixel content of the page (browser chrome is not captured)
  - `eval` - whatever the JS expression returns, including localStorage values if you read them
- Before fetching from sensitive sites, remind the user of that boundary. If the user fetches something they didn't intend to share, ending the session does not retroactively scrub model-provider logs.
- `eval` runs arbitrary authenticated JavaScript in the page - use read-only expressions, never mutations or POSTs.
- `purge` deletes the local profile data only. It does **not** revoke server-side sessions or tokens issued during auth. If the user wants to invalidate the session, they must sign out via the site itself first, then purge.

## Failure modes

- **`node` or `npm` not on PATH** - wrapper exits with code 127 and a clear message. Tell the user to install Node 18+.
- **First-run install fails** - usually a corporate proxy blocking npm or Playwright's browser download. Surface the stderr verbatim to the user; suggest `HTTP_PROXY` / `HTTPS_PROXY` env vars or `npm config set registry`.
- **`fetch` returns the login page after a previously-good `auth`** - cookies expired, or the site uses `sessionStorage` (which does **not** persist across browser close - only cookies, localStorage, IndexedDB, and service workers do). Re-run `auth`. If the site relies on `sessionStorage`, every browse session needs a fresh interactive auth.
- **Headless `fetch` redirects to login but headed `auth` worked fine** - some SSO / device-trust / bot-detection systems treat headless Chromium differently from headed. Workaround: rerun `auth` against the target page, navigate to it manually so it's the `last_url`, then immediately fetch. If that still fails, the site is incompatible with this skill in headless mode.
- **`Profile "..." is already in use by another command`** - wrapper exits with code 75. A previous `auth` or `fetch` against the same profile is still running. Wait for it to finish, or use a different profile name.
- **Page requires a click-through (e.g. "I trust this device") before content loads** - the `auth` step is exactly where the user handles this. If `fetch` later still hits an interstitial, re-run `auth` and have the user dismiss it.
- **Site uses a non-standard browser fingerprint check** - Playwright's Chromium is close to real Chrome but not identical. Most enterprise SSO works; some bot-detection-heavy sites won't. If it doesn't work, this skill can't fix it.

## Non-goals

This skill explicitly does **not**:

- Store, type, or recover passwords / TOTP secrets / SSH keys
- Bypass MFA, CAPTCHAs, or device-trust prompts
- Import cookies from an existing Chrome/Safari/Firefox profile
- Provide a long-running browser the agent attaches to via CDP while the user is also using it (single-context lock - out of scope for v0.1)
- Crawl / scrape at scale - it's a single-page-at-a-time helper, not a crawler
