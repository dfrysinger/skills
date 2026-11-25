#!/usr/bin/env python3
"""Stage, verify, and optionally send one message through the Slack desktop app.

Drives the composer through macOS Accessibility (AX) without raising Slack or
moving the pointer. Exit codes:
  0  staged and verified (dry run: composer restored; --leave: draft left in the
     composer for the user to edit and send) or sent (composer cleared)
  2  screen locked or lock state unknown
  3  Slack not running; window title not '<name> (…' in the workspace; composer,
     its own Send button, or the Paste menu not found or ambiguous; composer unreadable
  4  composer already holds a draft (left untouched)
  5  staged text does not match the requested text (composer restored)
  6  send pressed but composer did not clear (state unknown; do not resend)
 64  usage error, including raw <@ID>/<#ID>/<!here> tokens (they post as literal text)
"""
import argparse
import re
import subprocess
import sys
import time

CURLY = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})
EMOJI = re.compile(r":[a-z0-9_+\-]+(?:::skin-tone-\d)?:")
BULLETS = re.compile("[\ue000-\uf8ff\u2022]")
RAW_TOKEN = re.compile(r"<[@#!][A-Za-z0-9^|_-]+>")


def normalize(text: str) -> str:
    """Make requested and staged text comparable.

    Slack's composer turns :emoji: codes into inline images (read back as
    newlines or nothing), straight quotes into curly ones, and pasted list
    bullets into private-use glyphs.
    """
    text = BULLETS.sub(" ", EMOJI.sub(" ", text.translate(CURLY)))
    return " ".join(text.split())


def lock_state() -> str:
    """The session dictionary carries CGSSessionScreenIsLocked only while locked."""
    import Quartz

    d = Quartz.CGSessionCopyCurrentDictionary() or {}
    if d.get("CGSSessionScreenIsLocked"):
        return "LOCKED"
    if d.get("kCGSSessionOnConsoleKey") and d.get("kCGSessionLoginDoneKey"):
        return "UNLOCKED"
    return "UNKNOWN"


def slack_pid() -> int | None:
    out = subprocess.run(["pgrep", "-x", "Slack"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def paste_rich(pid, box, html, plain, attr, set_attr, perform) -> bool:
    """Paste HTML through Slack's Edit > Paste, then restore the user's clipboard."""
    import AppKit
    from ApplicationServices import AXUIElementCreateApplication

    pb = AppKit.NSPasteboard.generalPasteboard()
    saved = [[(t, item.dataForType_(t)) for t in item.types()] for item in pb.pasteboardItems() or []]
    ours = None
    try:
        pb.clearContents()
        pb.setString_forType_(html, AppKit.NSPasteboardTypeHTML)
        pb.setString_forType_(plain, AppKit.NSPasteboardTypeString)
        ours = pb.changeCount()
        set_attr(box, "AXFocused", True)
        paste = None
        for menu in attr(attr(AXUIElementCreateApplication(pid), "AXMenuBar"), "AXChildren") or []:
            if attr(menu, "AXTitle") == "Edit":
                for group in attr(menu, "AXChildren") or []:
                    for item in attr(group, "AXChildren") or []:
                        if attr(item, "AXTitle") == "Paste":
                            paste = item
        if paste is None:
            return False
        perform(paste, "AXPress")
        time.sleep(1.5)
        return True
    finally:
        if ours is None or pb.changeCount() == ours:
            pb.clearContents()
            items = []
            for values in saved:
                item = AppKit.NSPasteboardItem.alloc().init()
                for kind, data in values:
                    if data is not None:
                        item.setData_forType_(data, kind)
                items.append(item)
            if items:
                pb.writeObjects_(items)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(64, f"{self.prog}: error: {message}\n")


SEND_LABELS = ("send now", "send message")


def send_button_for(box, attr):
    """The Send button in the composer's own container, or None if absent or ambiguous."""
    def sends(e, d=0, out=None):
        out = [] if out is None else out
        if d > 40:
            return out
        if attr(e, "AXRole") == "AXButton" and str(attr(e, "AXDescription") or "").lower() in SEND_LABELS:
            out.append(e)
        for c in attr(e, "AXChildren") or []:
            sends(c, d + 1, out)
        return out

    e = box
    for _ in range(8):
        e = attr(e, "AXParent")
        if e is None:
            return None
        hits = sends(e)
        if hits:
            return hits[0] if len(hits) == 1 else None
    return None


def main() -> int:
    p = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--team", required=True, help="workspace or enterprise team ID from the slack:// link, e.g. T0123456789")
    p.add_argument("--workspace", required=True,
                   help="workspace name the Slack window title must show, e.g. Acme")
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--channel-id", help="channel ID, e.g. C0123456789")
    dest.add_argument("--user-id", help="user ID for a DM, e.g. U0123456789")
    p.add_argument("--name", required=True,
                   help="name in the composer label 'Message to <name>' (channel name without #, or DM handle)")
    p.add_argument("--text", required=True,
                   help="message text; with --html, the plain-text version used for the clipboard and verification")
    p.add_argument("--html", help="file holding an HTML version to paste as rich text (bold, italics, lists, links)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--send", action="store_true", help="press Send after verification (default: dry run)")
    mode.add_argument("--leave", action="store_true",
                      help="leave the verified draft in the composer for the user to edit and send")
    a = p.parse_args()

    if not a.text.strip():
        print("empty --text", file=sys.stderr)
        return 64
    html = open(a.html, encoding="utf-8").read() if a.html else None
    raw = RAW_TOKEN.findall(a.text) + RAW_TOKEN.findall(html or "")
    if raw:
        print(f"raw Slack tokens {raw} post as literal text; write mentions as @handle", file=sys.stderr)
        return 64
    state = lock_state()
    if state != "UNLOCKED":
        print(f"screen {state}; AX input needs an unlocked session", file=sys.stderr)
        return 2
    pid = slack_pid()
    if pid is None:
        print("Slack is not running", file=sys.stderr)
        return 3

    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateApplication,
                                     AXUIElementPerformAction, AXUIElementSetAttributeValue)

    link = (f"slack://channel?team={a.team}&id={a.channel_id}" if a.channel_id
            else f"slack://user?team={a.team}&id={a.user_id}")
    subprocess.run(["open", "-g", link], check=True)

    def attr(e, name):
        err, v = AXUIElementCopyAttributeValue(e, name, None)
        return v if err == 0 else None

    label = f"Message to {a.name}"

    def is_destination(title):
        return title.startswith(f"{a.name} (") and f" - {a.workspace} - " in title

    win = box = None
    title = ""
    boxes = []
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(1)
        windows = attr(AXUIElementCreateApplication(pid), "AXWindows") or []
        win = windows[0] if windows else None
        title = str(attr(win, "AXTitle") or "") if win is not None else ""
        if not is_destination(title):
            continue
        boxes = []

        def walk(e, d=0):
            if d > 60:
                return
            if attr(e, "AXRole") == "AXTextArea" and str(attr(e, "AXDescription") or "") == label:
                boxes.append(e)
            for c in attr(e, "AXChildren") or []:
                walk(c, d + 1)

        walk(win)
        if boxes:
            break
    print("window:", title)
    if not is_destination(title):
        print(f"window title does not show '{a.name} (…' in workspace '{a.workspace}'; refusing to stage",
              file=sys.stderr)
        return 3
    if len(boxes) != 1:
        print(f"expected one composer '{label}', found {len(boxes)}", file=sys.stderr)
        return 3
    box = boxes[0]
    if send_button_for(box, attr) is None:
        print(f"no single Send button belongs to composer '{label}'", file=sys.stderr)
        return 3

    err, original = AXUIElementCopyAttributeValue(box, "AXValue", None)
    if err != 0 or not isinstance(original, str):
        print(f"could not read composer (AX error {err}); refusing to touch a possible draft", file=sys.stderr)
        return 3
    if original.strip():
        print(f"composer already holds a draft; leaving it untouched: {original!r}", file=sys.stderr)
        return 4

    if html is None:
        AXUIElementSetAttributeValue(box, "AXValue", a.text)
    elif not paste_rich(pid, box, html, a.text, attr, AXUIElementSetAttributeValue, AXUIElementPerformAction):
        print("Edit > Paste menu item not found", file=sys.stderr)
        return 3
    time.sleep(0.8)
    staged = attr(box, "AXValue") or ""
    print("staged:", repr(staged))
    if normalize(staged) != normalize(a.text):
        AXUIElementSetAttributeValue(box, "AXValue", original)
        print(f"mismatch:\n  want {normalize(a.text)!r}\n  got  {normalize(staged)!r}", file=sys.stderr)
        return 5

    if a.leave:
        print("left: draft verified and waiting in the composer for the user to send")
        return 0

    if not a.send:
        AXUIElementSetAttributeValue(box, "AXValue", original)
        print("dry run: verified and restored composer")
        return 0

    send = send_button_for(box, attr)
    if send is None:
        AXUIElementSetAttributeValue(box, "AXValue", original)
        print("Send button disappeared after staging; composer restored", file=sys.stderr)
        return 3
    AXUIElementPerformAction(send, "AXPress")
    time.sleep(2)
    after = attr(box, "AXValue") or ""
    if after.strip():
        print(f"composer did not clear after Send: {after!r}", file=sys.stderr)
        return 6
    print("sent: composer cleared; read the channel back to confirm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
