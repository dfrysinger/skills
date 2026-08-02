#!/usr/bin/env bash
# capture_app.sh — autonomous screenshot of a macOS app window.
#
# Default flow (does not steal focus, works while the screen is locked):
#   1. Resolve candidate winids (onscreen layer-0 matches, largest first).
#   2. Capture each via CGWindowListCreateImage, falling back to
#      `screencapture -l` when the Quartz path returns nothing.
#   3. Pixel-content verify with an extrema-based blank detector.
#
# `--raise` flow (for hidden/non-composited windows; unlocked screen only):
#   1. Refuse if screen is locked (raise requires GUI focus).
#   2. Record the frontmost app BEFORE raising — never hardcode the restore.
#   3. Raise target, sleep, capture, restore focus, verify the restore landed.
#
# Usage:
#   capture_app.sh [--raise] [--winid N] <owner-name-substring> [output-path]
#
# Examples:
#   capture_app.sh "MyApp dev"                     # works locked
#   capture_app.sh --raise "MyApp dev" /tmp/n.png  # unlocked + hidden
#   capture_app.sh --winid 111 Finder /tmp/f.png   # exact window, no guessing
#
# Exit codes:
#   0  success — output written, pixels verified non-blank
#   2  --raise requested while screen locked (raise requires GUI focus)
#   3  no matching onscreen window found
#   4  every capture backend failed to produce an image
#   5  an image was produced but is blank/uniform (window not composited;
#      try --raise if unlocked, or unhide/open the window)
#   6  prerequisite missing (pyobjc venv at /tmp/bgctl/.venv)
#  64  usage error

set -euo pipefail

DO_RAISE=0
WANT_WINID=""
while [[ $# -gt 0 ]]; do
  case "${1:-}" in
    --raise) DO_RAISE=1; shift ;;
    --winid) WANT_WINID="${2:-}"; shift 2 || true ;;
    *) break ;;
  esac
done

usage() {
  echo "usage: $(basename "$0") [--raise] [--winid N] <owner-name-substring> [output-path]" >&2
  exit 64
}

NEEDLE="${1:-}"
[[ -z "$NEEDLE" ]] && usage
if [[ -n "$WANT_WINID" && ! "$WANT_WINID" =~ ^[0-9]+$ ]]; then
  echo "ERR: --winid takes a numeric CGWindowID" >&2
  usage
fi

# osa <seconds> <applescript> — bounded osascript. A denied Automation grant
# makes System Events hang rather than fail, so every call gets a deadline.
# Prints stdout on success; empty string on timeout or failure.
osa() {
  local secs="$1" script="$2" tmp rc=0
  tmp=$(mktemp -t bgctl-osa)
  ( osascript -e "$script" >"$tmp" 2>/dev/null ) & local pid=$!
  ( sleep "$secs"; kill -9 "$pid" 2>/dev/null ) >/dev/null 2>&1 & local watchdog=$!
  wait "$pid" 2>/dev/null || rc=$?
  { kill "$watchdog" && wait "$watchdog"; } 2>/dev/null || true
  [[ $rc -eq 0 ]] && cat "$tmp"
  rm -f "$tmp"
  return 0
}

VENV_PY=/tmp/bgctl/.venv/bin/python3
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIND_WINDOW="$SCRIPT_DIR/find_window.py"

if [[ ! -x "$VENV_PY" ]] || [[ ! -f "$FIND_WINDOW" ]]; then
  echo "ERR: missing pyobjc venv at $VENV_PY or find_window.py at $FIND_WINDOW" >&2
  echo "     bootstrap per SKILL.md → Prerequisites" >&2
  exit 6
fi

if [[ $# -ge 2 ]]; then
  OUT="$2"
else
  SAFE=$(printf '%s' "$NEEDLE" | tr -c 'A-Za-z0-9._-' '-' | tr -s '-')
  OUT="/tmp/${SAFE}-$(date +%Y%m%dT%H%M%S).png"
fi

is_locked() {
  ioreg -n Root -d1 -a 2>/dev/null | grep -A1 'CGSSessionScreenIsLocked</key>' | grep -q '<true/>'
}

# 1. --raise needs GUI focus; refuse fast if screen is locked.
if [[ $DO_RAISE -eq 1 ]] && is_locked; then
  echo "ERR: --raise requires unlocked screen (set frontmost has no effect under lock)" >&2
  echo "     for locked screens, try the default no-raise path instead" >&2
  exit 2
fi

# 2. Resolve candidate winids (ALL onscreen layer-0 matches, largest first).
#    We iterate through them because multiple windows can match a needle
#    (e.g., two instances of the same app) and we can't tell from the WindowList
#    API which one has a valid backing store. Try each until pixel-verify
#    passes.
CANDIDATES=$("$VENV_PY" "$FIND_WINDOW" "$NEEDLE" 2>/dev/null \
  | "$VENV_PY" -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
m = [w for w in d
     if w['layer'] == 0
     and w['onscreen']
     and w['bounds']['Width'] > 200
     and w['bounds']['Height'] > 100]
m.sort(key=lambda w: w['bounds']['Width'] * w['bounds']['Height'], reverse=True)
if not m:
    sys.exit(1)
for w in m:
    print(f\"{w['winid']}|{w['owner']}\")
" || true)

if [[ -z "$CANDIDATES" ]]; then
  echo "ERR: no onscreen layer-0 window matching '$NEEDLE'" >&2
  echo "     a denied Screen Recording grant also presents as no match" >&2
  exit 3
fi
if [[ -n "$WANT_WINID" ]]; then
  CANDIDATES=$(printf '%s\n' "$CANDIDATES" | grep "^${WANT_WINID}|" || true)
  if [[ -z "$CANDIDATES" ]]; then
    echo "ERR: winid $WANT_WINID is not an onscreen layer-0 match for '$NEEDLE'" >&2
    exit 3
  fi
fi
N_CANDIDATES=$(printf '%s\n' "$CANDIDATES" | wc -l | tr -d ' ')
echo "matched $N_CANDIDATES candidate window(s) for '$NEEDLE'"
if [[ $N_CANDIDATES -gt 1 && -z "$WANT_WINID" ]]; then
  echo "WARN: needle is ambiguous; taking the first candidate that verifies." >&2
  echo "      pass --winid to name the window you mean:" >&2
  printf '%s\n' "$CANDIDATES" | sed 's/^/      /' >&2
fi

# capture_via_pyobjc <winid> <out> — uses CGWindowListCreateImage. Works
# for occluded windows and for composited windows under screen lock.
capture_via_pyobjc() {
  local winid="$1" out="$2"
  "$VENV_PY" -c "
import Quartz, sys
img = Quartz.CGWindowListCreateImage(
    Quartz.CGRectNull,
    Quartz.kCGWindowListOptionIncludingWindow,
    $winid,
    Quartz.kCGWindowImageBoundsIgnoreFraming,
)
if img is None:
    sys.exit(1)
url = Quartz.CFURLCreateWithFileSystemPath(None, '$out', Quartz.kCFURLPOSIXPathStyle, False)
dest = Quartz.CGImageDestinationCreateWithURL(url, 'public.png', 1, None)
if dest is None:
    sys.exit(2)
Quartz.CGImageDestinationAddImage(dest, img, None)
ok = Quartz.CGImageDestinationFinalize(dest)
sys.exit(0 if ok else 3)
" >/dev/null 2>&1
}

# capture_via_screencapture <winid> <out> — ScreenCaptureKit path. Required
# on macOS 26, where the legacy CGWindowList capture path nil-returns. Fails
# outright under screen lock.
capture_via_screencapture() {
  local winid="$1" out="$2"
  screencapture -x -o -l"$winid" "$out" >/dev/null 2>&1 || return 1
  [[ -s "$out" ]]
}

# capture_any <winid> <out> — try both backends, in the order that costs
# least. Returns 0 if either produced a file, 1 if both failed.
capture_any() {
  local winid="$1" out="$2"
  capture_via_pyobjc "$winid" "$out" && [[ -s "$out" ]] && return 0
  capture_via_screencapture "$winid" "$out" && return 0
  return 1
}

# verify_pixels <path> — extrema-based blank detector. Catches the silent-
# failure mode where CGWindowListCreateImage / screencapture -x return a
# valid-shape PNG with zeroed pixels (locked screen + non-composited
# window). Uses dynamic-range check rather than unique-sample count so
# legitimately dark UIs (dark-mode Tauri/Electron) don't false-positive.
verify_pixels() {
  local f="$1"
  [[ -s "$f" ]] || return 1
  "$VENV_PY" -W ignore -c "
from PIL import Image
import sys
im = Image.open('$f')
ext = im.getextrema()
color = ext[:3]
max_span = max((hi - lo) for lo, hi in color)
data = list(im.getdata())[::5000]
brightness = sum(sum(p[:3])/3 for p in data) / len(data)
print(f'{im.width}x{im.height} max_channel_span={max_span} mean_brightness={brightness:.1f}')
sys.exit(0 if max_span > 30 else 1)
" 2>/dev/null
}

if [[ $DO_RAISE -eq 0 ]]; then
  # 2. Default path: pyobjc capture. Works in every state where the window
  #    has a composited backing store, including under screen lock.
  #    Iterate candidates — first non-blank wins.
  LAST_OUT=""
  LAST_METRICS=""
  ANY_IMAGE=0
  while IFS='|' read -r WINID OWNER; do
    [[ -z "$WINID" ]] && continue
    echo "try: '$OWNER' winid=$WINID"
    if capture_any "$WINID" "$OUT"; then
      ANY_IMAGE=1
      if METRICS=$(verify_pixels "$OUT"); then
        echo "OK: $OUT  target='$OWNER' winid=$WINID  ($METRICS)"
        exit 0
      fi
      LAST_OUT="$OUT"
      LAST_METRICS="$METRICS"
      echo "  blank ($METRICS) — trying next candidate"
    else
      echo "  every capture backend failed for this window — trying next"
    fi
  done <<< "$CANDIDATES"
  if [[ $ANY_IMAGE -eq 0 ]]; then
    echo "ERR: every capture backend failed on all $N_CANDIDATES candidate(s)" >&2
    if is_locked; then
      echo "     screen is locked; ScreenCaptureKit does not run under lock" >&2
    else
      echo "     check Screen Recording permission for the responsible process" >&2
    fi
    exit 4
  fi
  echo "ERR: all $N_CANDIDATES candidate window(s) returned blank/uniform" >&2
  echo "     last attempt: $LAST_METRICS" >&2
  if is_locked; then
    echo "     screen is locked AND no matching window was composited before lock" >&2
    echo "     no fix until screen unlocks (raise requires GUI focus)" >&2
  else
    echo "     all matching windows likely AX-hidden (Cmd-W'd); retry with: --raise" >&2
  fi
  [[ -n "$LAST_OUT" ]] && echo "     last file kept at $LAST_OUT for inspection" >&2
  exit 5
fi

# --raise path: capture-PREV-first, raise, capture, restore, verify.
# Use the first candidate (largest by area) since raising will composite it anyway.
WINID=$(printf '%s\n' "$CANDIDATES" | head -1 | cut -d'|' -f1)
OWNER=$(printf '%s\n' "$CANDIDATES" | head -1 | cut -d'|' -f2)
echo "target: '$OWNER' winid=$WINID → $OUT"

PREV=$(osa 5 'tell application "System Events" to get name of first application process whose frontmost is true')
if [[ -z "$PREV" ]]; then
  echo "WARN: could not read the frontmost app (Automation grant denied or timed out)." >&2
  echo "      proceeding; focus will not be restored." >&2
else
  echo "prev_frontmost=$PREV"
fi

osa 5 "tell application \"System Events\" to set frontmost of process \"$OWNER\" to true" >/dev/null
sleep 0.4

RC=0
capture_any "$WINID" "$OUT" || RC=$?

if [[ -n "$PREV" ]]; then
  osa 5 "tell application \"$PREV\" to activate" >/dev/null
  sleep 0.2
  AFTER=$(osa 5 'tell application "System Events" to get name of first application process whose frontmost is true')
  if [[ "$AFTER" != "$PREV" ]]; then
    echo "WARN: restore-focus check: wanted=$PREV got=$AFTER" >&2
  fi
fi

if [[ $RC -ne 0 ]] || [[ ! -s "$OUT" ]]; then
  echo "ERR: every capture backend failed even with --raise (winid $WINID)" >&2
  echo "     window may be fully closed (not just hidden); reopen it first" >&2
  exit 4
fi

if METRICS=$(verify_pixels "$OUT"); then
  echo "OK: $OUT ($METRICS)"
  exit 0
else
  echo "ERR: captured image still blank with --raise ($METRICS)" >&2
  echo "     file kept at $OUT for inspection" >&2
  exit 5
fi
