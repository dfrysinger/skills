#!/usr/bin/env python3
"""Find on-screen windows for a given owner-name substring. Print pid, winid, bounds, title."""
import sys, json
import Quartz

needle = sys.argv[1] if len(sys.argv) > 1 else "Safari"
opts = Quartz.kCGWindowListOptionAll | Quartz.kCGWindowListExcludeDesktopElements
wl = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
rows = []
for w in wl:
    owner = w.get('kCGWindowOwnerName', '') or ''
    if needle.lower() not in owner.lower():
        continue
    rows.append({
        'pid': w.get('kCGWindowOwnerPID'),
        'winid': w.get('kCGWindowNumber'),
        'owner': owner,
        'title': w.get('kCGWindowName', ''),
        'layer': w.get('kCGWindowLayer'),
        'onscreen': bool(w.get('kCGWindowIsOnscreen')),
        'bounds': dict(w.get('kCGWindowBounds') or {}),
    })
print(json.dumps(rows, indent=2))
