#!/usr/bin/env python3
"""Click via CGEventPost(kCGHIDEventTap) - reaches WebKit hit-testing.

Tradeoff: the cursor briefly moves to the click point because this goes
through the system-wide HID dispatch. We save the pre-click cursor and
warp it back immediately after.

For pure-AppKit apps prefer click.py (CGEventPostToPid, zero cursor move).
For WKWebView/Electron content this is the practical choice.
"""
import sys, time
import Quartz

x = float(sys.argv[1])
y = float(sys.argv[2])

# Save cursor
ev_now = Quartz.CGEventCreate(None)
prev = Quartz.CGEventGetLocation(ev_now)
prev_x, prev_y = prev.x, prev.y

src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
pt = (x, y)
move = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventMouseMoved, pt, 0)
down = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventLeftMouseDown, pt, Quartz.kCGMouseButtonLeft)
up   = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventLeftMouseUp,   pt, Quartz.kCGMouseButtonLeft)

Quartz.CGEventPost(Quartz.kCGHIDEventTap, move)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

# Warp cursor back (one frame later)
time.sleep(0.03)
Quartz.CGWarpMouseCursorPosition((prev_x, prev_y))
print(f"clicked ({x},{y}), restored cursor to ({prev_x},{prev_y})")
