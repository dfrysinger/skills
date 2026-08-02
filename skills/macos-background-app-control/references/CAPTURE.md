# Capture mechanism

The wrapper `scripts/capture_app.sh` owns the fallback chain and the pixel
validation. This file is why it is built that way; a caller does not need it.

## The two capture paths

`CGWindowListCreateImage` with `kCGWindowListOptionIncludingWindow` pulls from
the WindowServer's backing store, so z-order does not matter.

```python
img = Quartz.CGWindowListCreateImage(
    Quartz.CGRectNull,
    Quartz.kCGWindowListOptionIncludingWindow,
    winid,
    Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageNominalResolution,
)
```

- `kCGWindowImageNominalResolution` gives a 1x (points-sized) PNG. Skip it for
  native 2x Retina.
- `kCGWindowImageBoundsIgnoreFraming` strips drop shadow and NSWindow chrome.

The CLI path is `screencapture -x -o -l<WINID> file.png`, backed by
ScreenCaptureKit. Same source bitmap, but it includes Retina scaling and drop
shadow by default.

## Which path applies where

macOS 26 (Tahoe) retires the legacy CGWindowList capture path in favour of
ScreenCaptureKit, so `CGWindowListCreateImage` nil-returns there even with a
Screen Recording grant. Lock state cuts the other way: the backing store
survives a lock for any window composited before it, while `screencapture -l`
fails outright under lock with "could not create image from window", and
`screencapture -x` returns a valid-shape PNG of all-zero pixels.

|                | macOS 15 and earlier   | macOS 26 (Tahoe)              |
|----------------|------------------------|-------------------------------|
| **Unlocked**   | Quartz path            | `screencapture -l`, validated |
| **Locked**     | Quartz path, composited windows only | neither path works |

On Tahoe the ScreenCaptureKit fallback is inconsistent for occluded windows:
one session produced real content for some windows and blank, zero-spread,
wrong-sized frames for others. Exit codes do not reflect it, which is why
validation is mandatory rather than advisory.

## Blank-frame detection

`unique_sample_count > N` misfires on dark-mode UIs. Use channel extrema
spread: a real frame has at least one RGB channel where `max - min > 30`; a
blank frame has all channels at `(0, 0)`. `capture_app.sh` uses this.

## Resolving a window

```python
opts = Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements
wl = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
for w in wl:
    if owner_name_matches and w.get('kCGWindowLayer') == 0 and w.get('kCGWindowIsOnscreen'):
        winid, pid, bounds = w['kCGWindowNumber'], w['kCGWindowOwnerPID'], w['kCGWindowBounds']
```

Filter on `kCGWindowLayer == 0` and prefer `kCGWindowIsOnscreen`. Tauri apps
emit many off-screen helper windows that pass a name filter. CGWindowID is not
stable across app restarts, and neither are PIDs — re-resolve each session.

## A live app that will not capture

When a DOM bridge, app log, or backend probe proves the app is live and every
capture is blank, the display or session layer is not providing current pixels.
Read the lock state, check Screen Recording for the running bundle id, and check
the AX window count before trying more capture variants. When the machine is
reached over VNC or a KVM, the transport is the more likely suspect than the
capture call.

## Primitives are unvalidated

`capture_window.py` and `find_window.py` are building blocks for custom flows.
`capture_window.py` checks only that it wrote a non-empty file and will exit 0
on a fully blank PNG; `find_window.py` only enumerates window metadata as JSON.
Only `capture_app.sh` validates pixels.
