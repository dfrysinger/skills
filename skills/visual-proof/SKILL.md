---
name: visual-proof
description: Capture and inspect visual evidence for a current running UI candidate, rejecting blank, stale, unopened, or unfalsifiable screenshots. Use for every user-visible UI fix or feature before review, PR creation, landing, or a success claim; also use when a change note claims a screenshot or another skill needs runtime proof a human can see. This skill supplies the visual section of development-loop's machine-validated live-proof receipt; it does not replace full interaction proof.
---

# visual-proof

Seeing the software work is a separate claim from the tests passing, and a
screenshot has to earn it. A file that was written is not a capture, and a
capture is not proof until you have looked at it and said what it shows.

## 0. Produce receipt evidence, not a verdict

For runtime work, `development-loop` owns the completion gate and
[`references/live-proof-receipt.md`](../development-loop/references/live-proof-receipt.md)
owns its structured receipt. This skill fills the receipt's `visual` section.
It cannot set the whole receipt to `PASS` by itself: the flow owner must still
record the trigger, every meaningful interaction checkpoint, the terminal
state, forbidden outcomes, and running-candidate identity.

For every capture, return:

- its stable path;
- whether it was opened and rendered;
- one falsifiable claim read from its pixels;
- its actual width and height;
- a passed pixel-spread check.

Keep `visual.required: true` until all affected states have that evidence. A
final screenshot cannot stand in for button clicks, submissions, redirects,
agent tool calls, persistence, or reload behavior that happened before it.

Complete when the visual entries are ready for the shared validator, not when
the image file merely exists.

## 1. Answer it without pixels first

DOM state, console output, the API response, the accessibility tree, and the
process's own logs settle most questions faster and more precisely than an
image. Reach for those first, and spend a capture on what only pixels decide:
layout, overflow, spacing, contrast, and the proof a human will look at.

Complete when you have the answer, and — for any change with a visual surface
— a named question the human-facing capture still has to settle. Diagnosing
without pixels never retires the screenshot the record owes.

## 2. Prove the running process is the current tree

A running app will serve the old bundle after an edit. Hot reload reports
success and applies nothing, a service worker returns a cached build, a reload
serves the same stale asset, and a second instance is listening on the port you
are driving.

Prefer a signal that needs no source edit: the dev server's own rebuild line, a
served version or revision value, or a runtime result the old path could not
produce. When only a planted marker will do, capture it, remove it, reload, and
confirm `git diff --stat` holds only the intended files — a marker left in the
tree ships, and can change the very rendering you are proving.

A hot reload also tears down module-scoped state. Any check of what survives a
navigation — an in-memory cache, a store, a singleton — has to start from a
fresh pass taken after the last edit, or it measures reload recovery instead of
the behavior you meant to prove.

Complete when the durable record carries the signal you looked for and the
running-process line that returned it, and no temporary proof code remains.

## 3. Capture at the surface the software lives on

Pick a route the host can actually run before starting.

- **Web page, no login** — headless Playwright works on any host with Node.
  Locate the wrapper `authenticated-browse` ships, then screenshot directly:

  ```sh
  PW="$(find "$HOME/.copilot/installed-plugins" -maxdepth 7 -type f \
    -name pw-session.sh -path '*authenticated-browse*' 2>/dev/null | head -1)"
  bash "$PW" screenshot http://localhost:3000/route out.png
  ```

  It installs Playwright and Chromium on first run and waits on network idle.
- **Web page behind a login** — `authenticated-browse` owns the auth phase and
  profile reuse; run its browse phase against the authenticated profile.
- **macOS app** — `macos-background-app-control` captures a window sitting
  behind the user's foreground window, and clicks native controls without
  taking their focus. Go through its `capture_app.sh` wrapper, which validates
  pixel spread and fails a blank capture itself; its Python primitives exit 0
  on a blank PNG.
- **Webview, Tauri, or Electron content** — drive through the app's own route
  and eval surface. WebKit discards synthetic OS clicks on webview content, so
  a click that reports success can change nothing.
- **Terminal or CLI** — keep the output as text. A screenshot of text is
  weaker evidence than the text.

Name the viewport, theme, route, and interaction state the change can affect,
and capture each one: a responsive breakpoint and dark mode are where layout,
overflow, and contrast actually break, and hover, focus, loading, and error
states are invisible at rest. Freeze animation or wait for its end state, or
the frame you catch is mid-flight and reads as a bug. Wait on the specific
element you intend to show — a cold start can hold an empty root for a long
time, so an empty capture is a timing question before it is a crash.

There are hosts with no browser, no display, and no supported capture route.
Say that visual proof is unavailable, keep the deterministic runtime result,
and leave any acceptance criterion that requires a visual check unmet rather
than claiming it. Reach this only after step 3a.

Complete when every visual state the change affects has a capture, or the
missing capability is named.

## 3a. When no route reaches it, instrument the app

The tools above are where previous sessions stopped, not a boundary. An agent
that cannot reach what the user sees cannot validate its own work, so a
missing route is a thing to build, not a limitation to report.

Instrument the app under test with the affordance you are missing: a
debug-gated eval or IPC endpoint that runs a command in the live UI and returns
state, a `--screenshot` flag on the app's own dev harness, stable
`data-testid` hooks on anything you drive, a fixture route that puts the UI
into a state that is otherwise hard to reach. One general endpoint that takes
an arbitrary command beats per-button glue, because the next session gets it
for free. `macos-background-app-control`'s
[`references/DRIVING-CONTROLS.md`](../macos-background-app-control/references/DRIVING-CONTROLS.md)
carries a worked example, including the loopback token and discovery-file
details that make one safe.

Build it in the app's own repository, gated so release builds cannot expose it,
and treat it as shipped code: it goes through the same review and tests as the
feature. A one-off script in `/tmp` fails the point of this step.

Then write the route down. A capture path that lives only in this session's
transcript will be rediscovered from scratch next time — record the project's
harness, selectors, and invocation in the repository. When the procedure is
reusable beyond this project, capture it through the installed skill-authoring
workflow so it reaches future sessions.

Complete when the missing route exists and produced a capture, or you have
named the specific thing that blocked building it.

## 4. Look at the capture before believing it

A successful write is not a successful capture. When the route validated the
file itself — `capture_app.sh` exit 0 is a decode and pixel-spread pass, and it
reports the dimensions it got — take that and check the dimensions against what
you expected. Otherwise check both here. Blank, black, and white captures are
the ordinary failure, not a rare one.

Then open the image with a tool that renders it and read it. Say what it shows
in a sentence tied to visible pixels, text, or geometry, which reopening the
file could contradict: "the invoice total row reads 1,240.00 next to a red
overdue badge", not "the UI looks correct". A description nothing could
falsify is not evidence.

Record the path, opened state, actual dimensions, pixel-spread result, and
claim in the shared live-proof receipt. The receipt validator independently
decodes PNG captures and rejects missing, dimensionally inconsistent, or
single-color images.

Complete when the image has been viewed, its dimensions and pixel spread pass,
the written claim matches what you saw, and the structured capture entry is
ready for validation.

## 5. Pair the after against a baseline

A **fix** earns an after only against a before. Capture the failure while it
still fails — `development-loop` establishes it at section 0, before
any edit — and keep its path, route, viewport, and theme for the after. When
editing has already begun, reach the failing revision through a separate
worktree, or stash the fix, capture, reapply, and recheck the intended diff.

**New behavior** has no before. Pair the after against the approved
`prototype` sketch or the acceptance criteria, and name which one in the
durable record.

A lone after labelled `no baseline` is a report, not a pair, and does not
satisfy an acceptance criterion that calls for a visual regression check.

Complete when the after has its named counterpart and the only difference
between them is the behavior you changed.

## 6. Put it where the user will find it

A capture is a durable artifact of whatever was on screen. Frame it on the UI
under test, and when a token, password field, private message, or security code
would land in frame, change the state or crop it out before writing the file —
`secret-hygiene` governs the artifact the same as it governs a log.

Take the first route that works, without waiting on a reply:

1. **A live canvas**, when the host exposes one — some agent hosts render an
   HTML file in a panel, which beats an image for anything interactive. Check
   the host's canvas tools before falling through.
2. **Their browser or viewer** otherwise — `open` hands the file to whichever
   app they have set for that type.
3. **A synced folder or the macOS Photos library**, once the user says they are
   on their phone. Reuse the destination memory or context already records, and
   ask only when nothing does — then store the answer so it is asked once.
   `macos-photos-library` owns the import, and iCloud sync is not instant.

When no route is reachable, commit the file at a stable path and record that
path in the durable record. The evidence exists and is findable; carry on
rather than waiting.

Rungs 1 and 3 are macOS today. On other platforms the file path in the durable
record is the delivery.

Complete when the evidence sits at a route the user can reach and its path is
in the durable record.

## Pitfalls

- **Treating the written file as the proof.** The capture path succeeds and
  returns a black PNG more often than it fails outright.
- **Describing an image you did not open.** The sentence is only evidence if
  you read it off the pixels.
- **Capturing before the settle.** The screenshot shows a spinner, a skeleton,
  or an empty root, and reads as a regression.
- **Driving the app with synthetic clicks it never receives.** The script
  reports the click and the state does not move.
- **A screenshot standing in for a diagnosis.** Pixels show that something is
  wrong far better than they show why.
- **A screenshot standing in for the interaction.** The final pixels do not
  prove that the supported trigger, intermediate states, assistant actions, or
  persistence path worked.
- **Closing the runtime proof gate here.** Visual proof supplies evidence to
  the shared receipt; only the complete, current receipt validator can admit
  review, landing, or a success claim.
