#!/usr/bin/env python3
"""Click via CGEventPostToPid with explicit HID source - more reliable for WebKit."""
import sys, time
import Quartz

pid = int(sys.argv[1])
x = float(sys.argv[2])
y = float(sys.argv[3])

src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
point = (x, y)

down = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
up   = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventLeftMouseUp,   point, Quartz.kCGMouseButtonLeft)
# A move event before the down can help hit-testing
move = Quartz.CGEventCreateMouseEvent(src, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)

Quartz.CGEventPostToPid(pid, move)
time.sleep(0.02)
Quartz.CGEventPostToPid(pid, down)
time.sleep(0.05)
Quartz.CGEventPostToPid(pid, up)
print(f"clicked pid={pid} at ({x},{y}) via HID source")
