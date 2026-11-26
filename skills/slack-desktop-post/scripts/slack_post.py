#!/usr/bin/env python3
"""Stage, verify, and optionally send one message through the Slack desktop app.

Drives the composer through macOS Accessibility (AX), keeps the user's frontmost
app in front (Slack comes forward only for an HTML paste or a deep-link fallback, after
a 15 s pause in the user's typing), and never moves the pointer. Exit codes:
  0  staged and verified (dry run: composer restored; --leave: draft left in the
     composer for the user to edit and send) or sent (composer cleared)
  2  screen locked or lock state unknown
  3  Slack not running; the open conversation ID is not --channel-id/--dm-id; window
     title not '<name> (…' in the workspace; composer, its own Send button, or the
     Paste menu not found or ambiguous; composer unreadable; the frontmost app is
     unknown, so Slack is not brought forward
  4  composer already holds a draft, or gained one while --html waited (left untouched)
  5  staged text does not match the requested text (composer restored)
  6  send state unknown, do not resend: Send pressed but the composer did not clear
     or could not be read, or keys were pressed while staging and the staged text
     did not match (composer left as is, since the user may have typed in it)
  7  the composer could not be restored after a failed check; staged text may remain
  8  no 15 s pause in typing within 5 minutes, or the typing listener could not start,
     so Slack was not brought forward (--html paste or deep-link fallback); nothing staged
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
CLIENT_URL = re.compile(r"^https://app\.slack\.com/client/[^/]+/([A-Z0-9]+)(?:[/?#]|$)")


def composer_text(text: str) -> str:
    """Slack's composer turns each newline set through AX into a blank line plus a
    new line; the Unicode line separator gives a single line break."""
    return text.replace("\r\n", "\n").replace("\n", "\u2028")


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


def paste_rich(pid, box, html, plain, attr, set_attr, perform, focus, still_there) -> str:
    """Paste HTML through Slack's Edit > Paste, then restore the user's clipboard.

    Paste only lands while Slack is the active app, so after a pause in the
    user's typing Slack comes forward for the press alone (under half a second) and
    the user's app goes straight back. Returns "pasted", "typed" (keys went down
    while Slack was in front, so Enter may have sent it), "busy" (the user never
    paused typing), "unwatched" (the typing listener isn't running), "draft"
    (the composer gained text while waiting), "moved" (the conversation changed
    while waiting), "no-front" (the app to hand focus back to is unknown),
    "unreadable" (the composer could not be re-read), "no-focus" (Slack or its
    composer did not take focus, so nothing was pasted) or "no-menu".
    """
    import AppKit
    from ApplicationServices import AXUIElementCreateApplication

    paste = None
    for menu in attr(attr(AXUIElementCreateApplication(pid), "AXMenuBar"), "AXChildren") or []:
        if attr(menu, "AXTitle") == "Edit":
            for group in attr(menu, "AXChildren") or []:
                for item in attr(group, "AXChildren") or []:
                    if attr(item, "AXTitle") == "Paste":
                        paste = item
    if paste is None:
        return "no-menu"
    while True:
        if not InputWatch.running:
            return "unwatched"
        if not wait_for_typing_pause():
            return "unwatched" if not InputWatch.running else "busy"
        now = attr(box, "AXValue")
        if not isinstance(now, str):
            return "unreadable"
        if now.strip():
            return "draft"
        if not still_there():
            return "moved"
        # Typing may have resumed during the checks; wait again (same deadline) if so.
        if InputWatch.running and seconds_since_keypress() >= TYPING_PAUSE:
            break
    start = time.time()
    if not focus.activating():
        return "no-front"

    pb = AppKit.NSPasteboard.generalPasteboard()
    saved = [[(t, item.dataForType_(t)) for t in item.types()] for item in pb.pasteboardItems() or []]
    ours = None
    try:
        pb.clearContents()
        pb.setString_forType_(html, AppKit.NSPasteboardTypeHTML)
        pb.setString_forType_(plain, AppKit.NSPasteboardTypeString)
        ours = pb.changeCount()
        # Reading the clipboard can block on another app; recheck right before Slack comes forward.
        if not InputWatch.running:
            return "unwatched"
        if seconds_since_keypress() < TYPING_PAUSE:
            return "busy"
        if frontmost_pid() != pid:
            set_attr(AXUIElementCreateApplication(pid), "AXFrontmost", True)
            deadline = time.time() + 1
            while frontmost_pid() != pid and time.time() < deadline:
                time.sleep(0.02)
            focus.slack_forced()
        if frontmost_pid() != pid or set_attr(box, "AXFocused", True) != 0 or attr(box, "AXFocused") is not True:
            return "no-focus"
        perform(paste, "AXPress")
        time.sleep(0.1)
        note = focus.hand_back(wait=0.5)
        if note:
            print("focus:", note)
        time.sleep(1.4)
        return "typed" if seconds_since_keypress() < time.time() - start else "pasted"
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


def frontmost_pid() -> int | None:
    import AppKit

    # NSWorkspace updates frontmostApplication from run-loop notifications; a
    # script without a running loop reads a stale value unless it spins one.
    AppKit.NSRunLoop.currentRunLoop().runUntilDate_(AppKit.NSDate.dateWithTimeIntervalSinceNow_(0.01))
    app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
    return int(app.processIdentifier()) if app else None


class InputWatch:
    """Listen-only event tap that records when keys and clicks last happened.

    The system idle timers miss input that keyboard sharers such as Deskflow
    re-post from a private event source, so they report the user as idle
    while they type. A session tap sees that input too.
    """

    last: dict[int, float] = {}
    running = False
    started: float | None = None

    @classmethod
    def start(cls) -> bool:
        if cls.running:
            return True
        import threading

        import Quartz as Q

        ready = threading.Event()

        def run():
            tap = None

            def seen(proxy, kind, event, ref):
                now = time.monotonic()
                if kind in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                    # Input while the tap was off went unseen, so the pause starts over.
                    cls.last[Q.kCGEventKeyDown] = cls.last[Q.kCGEventLeftMouseDown] = now
                    Q.CGEventTapEnable(tap, True)
                else:
                    cls.last[kind] = now
                return event

            mask = Q.CGEventMaskBit(Q.kCGEventKeyDown) | Q.CGEventMaskBit(Q.kCGEventLeftMouseDown)
            tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap, Q.kCGEventTapOptionListenOnly,
                                     mask, seen, None)
            if tap:
                source = Q.CFMachPortCreateRunLoopSource(None, tap, 0)
                Q.CFRunLoopAddSource(Q.CFRunLoopGetCurrent(), source, Q.kCFRunLoopCommonModes)
                Q.CGEventTapEnable(tap, True)
                cls.started = time.monotonic()
                cls.running = True
            ready.set()
            if tap:
                Q.CFRunLoopRun()
                cls.running = False

        threading.Thread(target=run, daemon=True).start()
        ready.wait(2)
        return cls.running

    @classmethod
    def since(cls, kind: int) -> float:
        # Input before the tap started is unknown, so it counts as just now.
        at = cls.last.get(kind, cls.started)
        return float("inf") if at is None else time.monotonic() - at


def seconds_since_keypress() -> float:
    import Quartz

    return min(InputWatch.since(Quartz.kCGEventKeyDown),
               Quartz.CGEventSourceSecondsSinceLastEventType(Quartz.kCGEventSourceStateCombinedSessionState,
                                                             Quartz.kCGEventKeyDown))


def seconds_since_click() -> float:
    import Quartz

    return min(InputWatch.since(Quartz.kCGEventLeftMouseDown),
               Quartz.CGEventSourceSecondsSinceLastEventType(Quartz.kCGEventSourceStateCombinedSessionState,
                                                             Quartz.kCGEventLeftMouseDown))


TYPING_PAUSE = 15.0
TYPING_WAIT = 300.0
PAUSE_UNSEEN = ("the typing listener could not start, so a pause in typing can't be confirmed; not bringing "
                "Slack forward. Allow input monitoring for this terminal, or use markup mode")
_pause_deadline: float | None = None


def wait_for_typing_pause(pause=TYPING_PAUSE, timeout=TYPING_WAIT) -> bool:
    """Waits for a typing pause; every wait in one run shares a single deadline."""
    global _pause_deadline
    if _pause_deadline is None:
        _pause_deadline = time.time() + timeout
    deadline = _pause_deadline
    while seconds_since_keypress() < pause:
        if time.time() >= deadline or not InputWatch.running:
            return False
        time.sleep(0.1)
    return InputWatch.running


class Focus:
    """Hands focus back after the script's own Slack activations, never after the user's.

    The app to return to is whichever non-Slack app is in front at each
    activation, so an app switch the user made mid-run is respected, and a user
    already in Slack stays there. A pending hand-back is cancelled when the user
    switches to a third app, or clicks after both the last time their app was
    seen in front and the script's own activation of Slack.
    """

    LATE = 5.0  # Slack can activate itself this long after a deep link

    def __init__(self, slack):
        self.slack = slack
        self.owed = None
        self.seen = self.forced = self.until = 0.0

    def activating(self) -> bool:
        """Note the app to return to; False when it is unknown, so don't activate."""
        front = frontmost_pid()
        if front is None:
            return False
        now = time.time()
        if now >= self.until:
            self.owed = None
        if front != self.slack:
            self.owed, self.seen = front, now
        self.forced = 0.0
        self.until = now + self.LATE
        return True

    def slack_forced(self):
        """The script itself just brought Slack forward; earlier clicks are not the user's choice."""
        self.forced = time.time()

    def hand_back(self, wait=0.0) -> str | None:
        """Return focus if Slack took it; a debt stays open until paid, cancelled or LATE expires."""
        deadline = time.time() + wait
        while self.owed is not None:
            now = time.time()
            if now >= self.until:
                self.owed = None
                return None
            front = frontmost_pid()
            if front == self.owed:
                self.seen = now
            elif front != self.slack or seconds_since_click() < now - max(self.seen, self.forced):
                self.owed = None  # the user switched or clicked; their choice stands
                return None
            else:
                note = refocus(self.owed, self.slack)
                if note == "restored previous app":
                    self.owed = None
                return note
            if now >= deadline:
                return None
            time.sleep(0.1)
        return None


def should_refocus(front, prev, slack) -> bool:
    """Hand focus back only when Slack took it from another app."""
    return prev is not None and prev != slack and front == slack


def refocus(prev, slack, wait=0.0) -> str | None:
    """Put the user's previous app back in front if Slack took focus.

    Watches for up to `wait` seconds, since Slack activates itself a moment
    after a deep link. Uses direct AX, which needs no Automation grant, and
    falls back to NSRunningApplication. Returns a note when it acted.
    """
    import AppKit
    from ApplicationServices import AXUIElementCreateApplication, AXUIElementSetAttributeValue

    deadline = time.time() + wait
    while True:
        if should_refocus(frontmost_pid(), prev, slack):
            AXUIElementSetAttributeValue(AXUIElementCreateApplication(prev), "AXFrontmost", True)
            time.sleep(0.2)
            if frontmost_pid() == slack:
                app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(prev)
                if app is not None:
                    app.activateWithOptions_(0)
                    time.sleep(0.2)
            return "restored previous app" if frontmost_pid() == prev else "could not restore previous app"
        if time.time() >= deadline:
            return None
        time.sleep(0.1)


def sidebar_target(win, cid, attr):
    """The pressable element of the sidebar row for conversation `cid`, or None.

    Slack tags each sidebar row with the conversation ID as its DOM id. AXPress
    on the row's first child navigates without activating Slack; pressing the
    row itself does nothing.
    """
    rows = []

    def walk(e, d=0):
        if d > 30:
            return
        if attr(e, "AXRole") == "AXRow" and attr(e, "AXDOMIdentifier") == cid:
            rows.append(e)
            return
        for c in attr(e, "AXChildren") or []:
            walk(c, d + 1)

    walk(win)
    if len(rows) != 1:
        return None
    kids = attr(rows[0], "AXChildren") or []
    return kids[0] if kids else None


def conversation_from_url(url) -> str | None:
    """The conversation ID in a Slack client URL: channel C…/G…, or DM D…."""
    m = CLIENT_URL.match(str(url or ""))
    return m.group(1) if m else None


def open_conversation(win, attr) -> str | None:
    """Conversation ID the window is showing, or None if absent or ambiguous.

    Display names are not unique, so the window title alone cannot prove the
    destination; the Slack client page URL carries the conversation ID.
    """
    found = set()

    def walk(e, d=0):
        if d > 30:
            return
        if attr(e, "AXRole") == "AXWebArea":
            cid = conversation_from_url(attr(e, "AXURL"))
            if cid:
                found.add(cid)
                return
        for c in attr(e, "AXChildren") or []:
            walk(c, d + 1)

    walk(win)
    return next(iter(found)) if len(found) == 1 else None


def after_send(err, value) -> tuple[int, str]:
    """Classify the composer read taken after pressing Send."""
    if err != 0 or not isinstance(value, str):
        return 6, f"could not read composer after Send (AX error {err}); send state unknown, do not resend"
    if value.strip():
        return 6, f"composer did not clear after Send: {value!r}"
    return 0, "sent: composer cleared; read the channel back to confirm"


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
    dest.add_argument("--user-id", help="user ID for a DM, e.g. U0123456789; needs --dm-id")
    p.add_argument("--dm-id", help="the DM's conversation ID, e.g. D0123456789; required with --user-id")
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
    if a.user_id and not a.dm_id:
        p.error("--user-id needs --dm-id, the DM conversation ID that proves the destination")
    if a.channel_id and a.dm_id:
        p.error("--dm-id only applies with --user-id")
    target = a.channel_id or a.dm_id

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
    focus = Focus(pid)
    if not InputWatch.start():
        print("input listener unavailable; Slack won't be brought forward (--html paste or deep-link fallback)",
              file=sys.stderr)
    try:
        return deliver(a, pid, focus, target, html)
    finally:
        note = focus.hand_back()
        if note:
            print("focus:", note)


def deliver(a, pid, focus, target, html) -> int:
    from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateApplication,
                                     AXUIElementPerformAction, AXUIElementSetAttributeValue)

    def attr(e, name):
        err, v = AXUIElementCopyAttributeValue(e, name, None)
        return v if err == 0 else None

    def main_window():
        windows = attr(AXUIElementCreateApplication(pid), "AXWindows") or []
        return windows[0] if windows else None

    def showing():
        win = main_window()
        return open_conversation(win, attr) if win is not None else None

    def wait_for_target(seconds):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if showing() == target:
                return True
            time.sleep(0.2)
        return False

    if showing() == target:
        print("navigate: already open")
    else:
        win = main_window()
        row = sidebar_target(win, target, attr) if win is not None else None
        if row is not None and AXUIElementPerformAction(row, "AXPress") == 0 and wait_for_target(3):
            print("navigate: sidebar row")
        else:
            link = (f"slack://channel?team={a.team}&id={a.channel_id}" if a.channel_id
                    else f"slack://user?team={a.team}&id={a.user_id}")
            if not InputWatch.running:
                print(PAUSE_UNSEEN, file=sys.stderr)
                return 8
            if not wait_for_typing_pause():
                if not InputWatch.running:
                    print(PAUSE_UNSEEN, file=sys.stderr)
                    return 8
                print("the user never paused typing for 15 s within 5 minutes; not opening the deep link, "
                      "try again later", file=sys.stderr)
                return 8
            if not focus.activating():
                print("cannot tell which app is in front, so focus could not be handed back; "
                      "not opening the deep link", file=sys.stderr)
                return 3
            subprocess.run(["open", "-g", link], check=True)
            print("navigate: deep link; Slack may jump to the front, and focus is handed back")
            note = focus.hand_back(wait=2.0)
            if note:
                print("focus:", note)

    label = f"Message to {a.name}"

    def is_destination(title):
        return title.startswith(f"{a.name} (") and f" - {a.workspace} - " in title

    win = box = None
    title = ""
    conversation = None
    boxes = []
    deadline = time.time() + 10
    while time.time() < deadline:
        time.sleep(1)
        note = focus.hand_back()
        if note:
            print("focus:", note)
        windows = attr(AXUIElementCreateApplication(pid), "AXWindows") or []
        win = windows[0] if windows else None
        title = str(attr(win, "AXTitle") or "") if win is not None else ""
        conversation = open_conversation(win, attr) if win is not None else None
        if conversation != target or not is_destination(title):
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
    print("conversation:", conversation)
    if conversation != target:
        print(f"open conversation is {conversation}, expected {target}; refusing to stage", file=sys.stderr)
        return 3
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

    def restore() -> bool:
        AXUIElementSetAttributeValue(box, "AXValue", original)
        time.sleep(0.3)
        err, now = AXUIElementCopyAttributeValue(box, "AXValue", None)
        if err == 0 and isinstance(now, str) and now.strip() == original.strip():
            return True
        print("could not restore the composer; the staged text may still be in it", file=sys.stderr)
        return False

    note = focus.hand_back(wait=0.5)
    if note:
        print("focus:", note)
    pasted = None
    staging = time.time()
    if html is None:
        AXUIElementSetAttributeValue(box, "AXValue", composer_text(a.text))
    else:
        pasted = paste_rich(pid, box, html, a.text, attr, AXUIElementSetAttributeValue, AXUIElementPerformAction,
                            focus, lambda: open_conversation(win, attr) == target and attr(box, "AXDescription") == label)
        if pasted == "no-menu":
            print("Edit > Paste menu item not found", file=sys.stderr)
            return 3
        if pasted == "unwatched":
            print(PAUSE_UNSEEN, file=sys.stderr)
            return 8
        if pasted == "busy":
            print("the user never paused typing for 15 s within 5 minutes, or resumed just before the paste; "
                  "nothing pasted, try again later", file=sys.stderr)
            return 8
        if pasted == "draft":
            print("composer gained a draft while waiting; leaving it untouched", file=sys.stderr)
            return 4
        if pasted == "no-focus":
            print("Slack's composer did not take focus; nothing pasted", file=sys.stderr)
            return 3
        if pasted == "moved":
            print("conversation changed while waiting for a pause in typing; nothing pasted", file=sys.stderr)
            return 3
        if pasted == "unreadable":
            print("could not re-read the composer after waiting; refusing to paste", file=sys.stderr)
            return 3
        if pasted == "no-front":
            print("cannot tell which app is in front, so focus could not be handed back; not pasting",
                  file=sys.stderr)
            return 3
    time.sleep(0.8)
    staged = attr(box, "AXValue") or ""
    print("staged:", repr(staged))
    if normalize(staged) != normalize(a.text):
        print(f"mismatch:\n  want {normalize(a.text)!r}\n  got  {normalize(staged)!r}", file=sys.stderr)
        if pasted == "typed" or seconds_since_keypress() < time.time() - staging:
            # The user may have typed into the composer; restoring would erase their words.
            print("keys were pressed while staging, so Enter in Slack may have sent it; composer left as "
                  "is for the user; read the channel before any retry", file=sys.stderr)
            return 6
        if not restore():
            return 7
        return 5
    if open_conversation(win, attr) != target or attr(box, "AXDescription") != label:
        if not restore():
            return 7
        print("conversation changed while staging; composer restored", file=sys.stderr)
        return 3

    if a.leave:
        print("left: draft verified and waiting in the composer for the user to send")
        return 0

    if not a.send:
        if not restore():
            return 7
        print("dry run: verified and restored composer")
        return 0

    send = send_button_for(box, attr)
    if send is None:
        if not restore():
            return 7
        print("Send button disappeared after staging; composer restored", file=sys.stderr)
        return 3
    AXUIElementPerformAction(send, "AXPress")
    time.sleep(2)
    code, message = after_send(*AXUIElementCopyAttributeValue(box, "AXValue", None))
    print(message, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
