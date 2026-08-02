# Driving controls

Clicking and typing into a background app. Capture needs none of this.

## Native AppKit content

`CGEventPostToPid(pid, event)` delivers the event straight to the target
process's queue. The cursor does not move and the frontmost app keeps focus.

```python
src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
pt = (x, y)
for kind in (Quartz.kCGEventMouseMoved,
             Quartz.kCGEventLeftMouseDown,
             Quartz.kCGEventLeftMouseUp):
    ev = Quartz.CGEventCreateMouseEvent(src, kind, pt, Quartz.kCGMouseButtonLeft)
    Quartz.CGEventPostToPid(pid, ev)
    time.sleep(0.03)
```

`CGEventCreateKeyboardEvent(src, keycode, True/False)` follows the same pattern
for keystrokes, against any control holding key focus in that process.

Read window pose and native chrome through Accessibility:

```bash
osascript -e 'tell app "System Events" to tell process "MyApp dev - feature-x" to ¬
  return (get position of window 1) & (get size of window 1) & (title of window 1)'
```

AX exposes window position, size, title, the menu bar, traffic-light buttons,
and native elements (`AXButton`, `AXTextField`, `AXMenuItem`).

## Webview content reaches none of that

Three separate walls stand between a background webview and automation:

- **`CGEventPostToPid` is discarded.** WebKit and Electron's Chromium drop
  synthetic mouse events that did not arrive through HID dispatch. The event
  reaches the process, no hit-test fires, and the script reports a click that
  changed nothing.
- **`CGEventPost(kCGHIDEventTap, …)` hit-tests correctly but hits the
  frontmost window at that coordinate.** With the target behind Chrome, Chrome
  receives the click. Real hit-testing and occluded targeting cannot both hold.
- **AX cannot see the DOM.** Traversing a Tauri window yields one opaque
  `AXGroup`; Electron's WebContents is not AX-exposed either. Tauri also starts
  no remote-inspector TCP server, so there is no localhost port for a CDP
  client to attach to.

## Three ways through, in order

1. **An eval-JS bridge the app exposes.** For an app you control, add a
   debug-only path taking a JS string and running it in the webview via
   `webview.eval` (Tauri) or `webContents.executeJavaScript` (Electron). A
   loopback TCP listener on `127.0.0.1:<auto>`, with the port and a
   per-instance random token written to a discovery file, is the cleanest
   shape. Gate the module on `cfg(debug_assertions)` so release binaries
   cannot expose it.

   Three security details are non-obvious:

   - **Loopback is cross-user reachable on macOS.** Any local user can hit the
     port, so the bridge needs a per-instance token compared in constant time,
     and the discovery file and its directory need mode 0600/0700.
   - **Bound each request read.** Cap bytes and wrap the read in a timeout —
     slowloris defeats a byte cap alone.
   - **Write the discovery file per PID** (`~/.<app>/run/debug-eval-<pid>.json`)
     so parallel dev instances do not clobber each other; the agent globs and
     `kill -0`s to find a live one. Unlink then create with `O_EXCL`, so a
     stale file from a recycled PID cannot keep its old mode.

   One IPC command then covers every button with no per-button glue. Ask for
   `data-testid` attributes on anything you drive, so selectors survive CSS and
   layout changes.

   ```bash
   eval.sh 'document.querySelector("[data-testid=share]").click()'
   eval.sh 'JSON.stringify({url: location.href, title: document.title})'
   ```

2. **Raise briefly, click through HID, restore.** Needed for webview clicks
   when there is no bridge. The disruption is short but real.

   ```bash
   PREV=$(osascript -e 'tell app "System Events" to get name of first application process whose frontmost is true')
   osascript -e 'tell app "System Events" to set frontmost of process "MyApp dev - feature-x" to true'
   sleep 0.3
   scripts/click_hid.py <X> <Y>
   osascript -e "tell application \"$PREV\" to activate"
   osascript -e 'tell app "System Events" to get name of first application process whose frontmost is true'
   ```

   Capture `$PREV` before raising and restore to it. A hardcoded restore target
   silently no-ops whenever the previously-frontmost app is something else,
   which strands the target window in front and looks exactly like broken AX
   permissions.

3. **Capture instead of driving.** Most verification needs only the screenshot
   half of the loop; the user can do the clicking.

## Pitfalls

- **`activate` and `set frontmost` can silently no-op** under focus-steal
  prevention. Set `kAXFrontmostAttribute = True` on the app's AX element, then
  confirm with `NSWorkspace.frontmostApplication()` and retry. Give the window
  a settle delay before a HID click, or the raise lands after the event and the
  click registers as a hover.
- **AppleScript `set frontmost` often needs a second call.** Sleep 100ms
  between attempts.
- **A second webview breaks a Tauri bridge's window lookup.** Opening a browser
  or canvas panel demotes a `WebviewWindow` to a multi-webview `Window`, so
  `app.get_webview_window("main")` returns `None` and the bridge goes dark
  exactly while you are driving an artifact. Fall back to `app.webviews()` and
  select by label.
- **Nothing here works while the screen is locked.** `set frontmost` no-ops,
  `CGEventPostToPid` is dropped, and AX returns stale state.
- **`CGWarpMouseCursorPosition` is visible for about one frame.** For truly
  invisible operation use `CGEventPostToPid` and accept that webviews ignore it.
