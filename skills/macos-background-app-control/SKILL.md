---
name: macos-background-app-control
description: Screenshot or click a macOS app window sitting behind the user's foreground window, without stealing focus or moving the cursor. Use when verifying a macOS GUI end to end while sharing the user's Mac, when another skill needs a capture of an occluded native or WebView app window, or when a click must reach a background app without disrupting whatever the user is doing.
---

# macos-background-app-control

Catch a macOS app's state, or drive it, while it sits behind the user's
foreground window on the machine they are working on. The cursor does not move
and the frontmost app does not change.

## When to use

- Verifying a GUI end to end while sharing a Mac with the user.
- Capturing a window that is not frontmost.
- Driving a native AppKit or SwiftUI app with no visible cursor jumps.
- Driving a Tauri or Electron app, where most automation paths only appear to
  work.

The user clicking is cheaper than any of this when they are at the machine. An
app that exposes its own debug eval bridge is cheaper still — use it.

## Prerequisites

- macOS 15 or later.
- `uv` and Python 3.13 (`brew install uv`) for the pyobjc venv at
  `/tmp/bgctl/.venv`.
- Screen Recording permission, for capturing other apps' windows.
- Accessibility permission, for AX reads and `CGEventPost*`. Without it AX
  returns empty and events silently no-op.

```bash
mkdir -p /tmp/bgctl && cd /tmp/bgctl
uv venv --python 3.13 --quiet
uv pip install --quiet pyobjc-framework-Quartz pyobjc-framework-Cocoa pillow
```

**Both permissions attach to the responsible process, not the terminal you can
see.** When the agent shell is parented to a `tmux` server started by a
LaunchAgent, the responsible process is `tmux`, and granting Terminal or iTerm
does nothing. Walk `ps -o ppid= -p $$` up to launchd; the topmost non-launchd
ancestor needs the grant.

**Accessibility and Automation are two separate grants.** Direct AX
(`AXUIElementCopyAttributeValue`, `AXIsProcessTrusted`) needs only
`kTCCServiceAccessibility`. Driving `System Events` over AppleScript also needs
`kTCCServiceAppleEvents`. A tmux-LaunchAgent commonly holds Accessibility while
Automation is denied with no prompt, and in that state `System Events` **hangs**
rather than failing. Verify with a direct AX read and prefer direct AX for
foregrounding; a hanging `osascript "System Events"` call means missing
Automation, not missing Accessibility.

Neither grant can be provisioned from an SSH session. Report the specific
missing grant and carry on rather than waiting.

## Capture a window

Run the wrapper. It resolves the window, tries the WindowServer backing store,
falls back to ScreenCaptureKit when that returns nothing, validates the PNG has
real pixel spread, and exits with a specific reason when it cannot.

```bash
scripts/capture_app.sh "MyApp dev - feature-x" /tmp/out.png
```

Run it from the directory holding this `SKILL.md`; it locates its own
siblings, and `/tmp/bgctl` is only where the venv lives, not a working
directory. Exit 0 is a validated capture: an image was produced, it decoded,
and at least one RGB channel spans more than 30. It prints the dimensions it
got — check them yourself when they matter, since the wrapper does not know
what you expected. Act on any other code rather than reading the raw result.

- **3 — no window matched.** Re-resolve the needle; window titles and IDs
  change every session. A denied Screen Recording grant presents the same way.
- **5 — an image came back blank.** Unlocked, retry with `--raise`: the window
  is AX-hidden, usually because Cmd-W destroyed a Tauri window while leaving
  the process alive. Locked, the window was never composited and no capture is
  possible until unlock.
- **4 — every capture backend failed.** Under lock this is expected on macOS
  26, where the surviving path needs a GUI session. Unlocked it points at
  Screen Recording permission.
- **2 — `--raise` under lock.** Raising needs GUI focus. Report locked and
  continue.
- **6 — venv missing.** Run the bootstrap above. **64** is a usage error.

A needle matching several windows is ambiguous, and the wrapper says so on
stderr while returning the first candidate that verifies — a real window, but
possibly a stale sibling instance. Pass `--winid` from that listing to name the
one you mean whenever the answer has to be exact.

The version and lock-state dependent failure modes are exactly why the wrapper
owns the fallback chain and the validation.
[`references/CAPTURE.md`](references/CAPTURE.md) holds the mechanism, and notes
that `capture_window.py` and `find_window.py` are unvalidated primitives that
exit 0 on a blank PNG.

## Read the lock state before concluding anything

A locked Mac is capture-only, and only for windows composited before the lock.
Clicks, AX, and HID do not navigate a locked screen.

```bash
ioreg -n Root -d1 -a | grep -A1 'CGSSessionScreenIsLocked</key>' | grep -q '<true/>' \
  && echo LOCKED || echo UNLOCKED
```

The key is present and `<false/>` on an unlocked machine, so test the value,
not the key. Prefer this over the pyobjc equivalent, which needs a Quartz
install the system `python3` usually lacks. Locked is a fact you can read, so
read it before telling the user you cannot verify visually.

Headless browser screenshots are unaffected — they render offscreen inside the
browser process and still validate browser-renderable UI on a locked Mac.

## Click or type into the app

[`references/DRIVING-CONTROLS.md`](references/DRIVING-CONTROLS.md) covers native
AppKit clicks, why every synthetic path fails against webview content, and the
three routes through it. Read it when you need to drive rather than capture.

The one fact worth carrying without opening it: **a click reported against
webview content did not happen.** WebKit and Chromium discard synthetic events
that did not arrive through HID dispatch, so the script succeeds and the UI does
not move.

## Verification

```bash
BEFORE=$(osascript -e 'tell app "System Events" to get name of first application process whose frontmost is true')
scripts/capture_app.sh Finder /tmp/finder.png; echo "exit=$?"
osascript -e 'tell app "System Events" to get name of first application process whose frontmost is true'
echo "was: $BEFORE"
```

Exit 0 with the frontmost app unchanged means capture, permissions, and
focus preservation all work. An `osascript` call that never returns means the
Automation grant is missing, not the Accessibility one.

## References

- Apple: [CGWindowListCreateImage](https://developer.apple.com/documentation/coregraphics/1455730-cgwindowlistcreateimage)
- Apple: [CGEventPostToPid](https://developer.apple.com/documentation/coregraphics/1408785-cgeventposttopid)
