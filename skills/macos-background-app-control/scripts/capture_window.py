#!/usr/bin/env python3
"""Capture a window by CGWindowID even when occluded/in-background."""
import sys
import Quartz

winid = int(sys.argv[1])
out = sys.argv[2]
# kCGWindowImageBoundsIgnoreFraming strips the drop shadow; kCGWindowListOptionIncludingWindow
# captures just that window. Works on occluded windows because it pulls from the
# window-server's backing store, not from screen pixels.
img = Quartz.CGWindowListCreateImage(
    Quartz.CGRectNull,
    Quartz.kCGWindowListOptionIncludingWindow,
    winid,
    Quartz.kCGWindowImageBoundsIgnoreFraming | Quartz.kCGWindowImageNominalResolution,
)
if img is None:
    # macOS 26 (Tahoe) nil-returns the deprecated CGWindowListCreateImage even with a
    # Screen Recording grant — Apple is retiring the legacy CGWindowList capture path in
    # favor of ScreenCaptureKit. Fall back to `screencapture -l<winid>`, which is
    # SCK-backed and still captures the window's backing store (works while occluded).
    import os
    import subprocess
    r = subprocess.run(["screencapture", "-x", "-o", f"-l{winid}", out],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
        print(f"OK wrote {out} (via screencapture -l fallback)")
        sys.exit(0)
    print("FAIL: no image returned (CGWindowListCreateImage nil + screencapture fallback failed)")
    if r.stderr.strip():
        print(r.stderr.strip())
    sys.exit(1)

# Write PNG
url = Quartz.CFURLCreateFromFileSystemRepresentation(None, out.encode('utf-8'), len(out), False)
dst = Quartz.CGImageDestinationCreateWithURL(url, "public.png", 1, None)
Quartz.CGImageDestinationAddImage(dst, img, None)
Quartz.CGImageDestinationFinalize(dst)
print(f"OK wrote {out} {Quartz.CGImageGetWidth(img)}x{Quartz.CGImageGetHeight(img)}")
