"""Offline checks for slack_post.py. Run: python3 -m unittest discover scripts"""
import unittest

import contextlib
import io
import sys

from slack_post import RAW_TOKEN, main, normalize, send_button_for


class NormalizeTest(unittest.TestCase):
    def test_emoji_images_and_curly_quotes_match_request(self):
        requested = "@reviewer can I get a staging :stamp: on it? It's ready :pray::skin-tone-3:"
        staged = "@reviewer can I get a staging \n\n on it? It\u2019s ready \n"
        self.assertEqual(normalize(staged), normalize(requested))

    def test_changed_words_still_differ(self):
        self.assertNotEqual(normalize("stamp pull/101"), normalize("stamp pull/102"))

    def test_pasted_list_bullets_are_ignored(self):
        staged = "Title\n\ue506repo | merged: first\n\ue506second\n"
        self.assertEqual(normalize(staged), normalize("Title\n• repo | merged: first\n• second"))


class RawTokenTest(unittest.TestCase):
    def test_raw_mentions_are_detected(self):
        self.assertEqual(RAW_TOKEN.findall("hi <@U0123456789> in <#C0123456789> <!here>"),
                         ["<@U0123456789>", "<#C0123456789>", "<!here>"])

    def test_handles_and_links_pass(self):
        self.assertEqual(RAW_TOKEN.findall("@reviewer https://github.com/octo-org/x/pull/1"), [])


class Node:
    def __init__(self, role, desc="", children=()):
        self.role, self.desc, self.children, self.parent = role, desc, list(children), None
        for c in self.children:
            c.parent = self


def fake_attr(e, name):
    return {"AXRole": e.role, "AXDescription": e.desc, "AXChildren": e.children, "AXParent": e.parent}[name]


class SendButtonTest(unittest.TestCase):
    def test_picks_the_button_beside_its_composer_not_the_thread_one(self):
        box = Node("AXTextArea", "Message to team-chat")
        mine = Node("AXButton", "Send now")
        thread = Node("AXGroup", children=[Node("AXTextArea", "Reply"), Node("AXButton", "Send now")])
        Node("AXGroup", children=[Node("AXGroup", children=[Node("AXGroup", children=[box]), mine]), thread])
        self.assertIs(send_button_for(box, fake_attr), mine)

    def test_two_buttons_in_one_container_is_ambiguous(self):
        box = Node("AXTextArea", "Message to team-chat")
        Node("AXGroup", children=[box, Node("AXButton", "Send now"), Node("AXButton", "Send message")])
        self.assertIsNone(send_button_for(box, fake_attr))


class UsageTest(unittest.TestCase):
    def test_bad_arguments_exit_64_not_the_locked_code(self):
        sys.argv = ["slack_post.py", "--team", "E1"]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 64)

    def test_send_and_leave_together_is_a_usage_error(self):
        sys.argv = ["slack_post.py", "--team", "E1", "--workspace", "Acme", "--channel-id", "C1", "--name", "x",
                    "--text", "hi", "--send", "--leave"]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 64)


if __name__ == "__main__":
    unittest.main()
