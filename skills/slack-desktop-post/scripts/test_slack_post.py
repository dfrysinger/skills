"""Offline checks for slack_post.py. Run: python3 -m unittest discover scripts"""
import unittest

import contextlib
import io
import sys

from slack_post import (RAW_TOKEN, after_send, conversation_from_url, main, normalize, open_conversation,
                        send_button_for, should_refocus, sidebar_target)
import slack_post


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
    def __init__(self, role, desc="", children=(), url=None, dom=None):
        self.role, self.desc, self.children, self.parent, self.url = role, desc, list(children), None, url
        self.dom = dom
        for c in self.children:
            c.parent = self


def fake_attr(e, name):
    return {"AXRole": e.role, "AXDescription": e.desc, "AXChildren": e.children, "AXParent": e.parent,
            "AXURL": e.url, "AXDOMIdentifier": e.dom}[name]


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


class ConversationTest(unittest.TestCase):
    def test_reads_conversation_id_from_client_url(self):
        self.assertEqual(conversation_from_url("https://app.slack.com/client/T0123456789/D0123456789"), "D0123456789")
        self.assertEqual(conversation_from_url("https://app.slack.com/client/T01/C0123456789/thread/C0123456789-1.2"),
                         "C0123456789")
        self.assertIsNone(conversation_from_url("https://app.slack.com/client/T0123456789"))

    def test_window_shows_one_conversation(self):
        win = Node("AXWindow", children=[Node("AXGroup", children=[
            Node("AXWebArea", url="https://app.slack.com/client/T01/D0123456789")])])
        self.assertEqual(open_conversation(win, fake_attr), "D0123456789")

    def test_two_conversations_is_ambiguous(self):
        win = Node("AXWindow", children=[Node("AXWebArea", url="https://app.slack.com/client/T01/D01"),
                                         Node("AXWebArea", url="https://app.slack.com/client/T01/D02")])
        self.assertIsNone(open_conversation(win, fake_attr))


class SidebarTest(unittest.TestCase):
    def test_presses_the_inner_element_of_the_matching_row(self):
        inner = Node("AXGroup")
        sidebar = Node("AXOutline", children=[Node("AXRow", dom="C111", children=[Node("AXGroup")]),
                                              Node("AXRow", dom="D222", children=[inner])])
        self.assertIs(sidebar_target(Node("AXWindow", children=[sidebar]), "D222", fake_attr), inner)

    def test_missing_or_duplicate_row_falls_back(self):
        rows = [Node("AXRow", dom="C111", children=[Node("AXGroup")]) for _ in range(2)]
        win = Node("AXWindow", children=rows)
        self.assertIsNone(sidebar_target(win, "C111", fake_attr))
        self.assertIsNone(sidebar_target(win, "C999", fake_attr))


class RefocusTest(unittest.TestCase):
    def test_hands_back_only_when_slack_took_focus_from_another_app(self):
        self.assertTrue(should_refocus(front=10, prev=20, slack=10))
        self.assertFalse(should_refocus(front=20, prev=20, slack=10))
        self.assertFalse(should_refocus(front=10, prev=10, slack=10))
        self.assertFalse(should_refocus(front=10, prev=None, slack=10))


class FocusTest(unittest.TestCase):
    def setUp(self):
        self.front, self.calls = 20, []
        self._saved = slack_post.frontmost_pid, slack_post.refocus, slack_post.seconds_since_click
        self.click = 1e9
        slack_post.frontmost_pid = lambda: self.front
        slack_post.seconds_since_click = lambda: self.click
        self.note = "restored previous app"
        slack_post.refocus = lambda prev, slack, wait=0.0: self.calls.append(prev) or self.note

    def tearDown(self):
        slack_post.frontmost_pid, slack_post.refocus, slack_post.seconds_since_click = self._saved

    def test_hands_back_to_the_app_in_front_at_activation(self):
        focus = slack_post.Focus(slack=10)
        self.front = 30
        focus.activating()
        self.assertIsNone(focus.hand_back())
        self.front = 10
        focus.hand_back()
        self.assertEqual(self.calls, [30])

    def test_late_activation_stays_owed_until_paid(self):
        focus = slack_post.Focus(slack=10)
        focus.activating()
        self.front = 10
        self.note = "could not restore previous app"
        focus.hand_back()
        self.note = "restored previous app"
        focus.hand_back()
        focus.hand_back()
        self.assertEqual(self.calls, [20, 20])

    def test_second_activation_keeps_the_unpaid_debt(self):
        focus = slack_post.Focus(slack=10)
        focus.activating()
        self.front = 10
        focus.activating()
        focus.hand_back()
        self.assertEqual(self.calls, [20])

    def test_user_click_or_switch_cancels_the_debt(self):
        for click, front in ((0.0, 10), (1e9, 30)):
            focus = slack_post.Focus(slack=10)
            self.front = 20
            focus.activating()
            focus.seen -= 1.0
            self.click, self.front = click, front
            self.assertIsNone(focus.hand_back())
            self.assertIsNone(focus.owed)
        self.assertEqual(self.calls, [])

    def test_newer_app_replaces_a_stale_debt(self):
        focus = slack_post.Focus(slack=10)
        focus.activating()
        self.front = 30
        focus.activating()
        self.front = 10
        focus.hand_back()
        self.assertEqual(self.calls, [30])

    def test_click_before_scripted_activation_does_not_cancel(self):
        focus = slack_post.Focus(slack=10)
        focus.activating()
        focus.seen -= 1.0
        focus.slack_forced()
        self.click, self.front = 0.5, 10
        focus.hand_back()
        self.assertEqual(self.calls, [20])

    def test_expired_debt_is_dropped_not_revived(self):
        focus = slack_post.Focus(slack=10)
        focus.activating()
        focus.until = 0.0
        self.front = 10
        self.assertTrue(focus.activating())
        self.assertIsNone(focus.hand_back())
        self.assertEqual(self.calls, [])

    def test_unknown_front_app_refuses_activation(self):
        self.front = None
        self.assertFalse(slack_post.Focus(slack=10).activating())

    def test_user_switching_to_slack_is_left_alone(self):
        focus = slack_post.Focus(slack=10)
        self.front = 10
        self.assertIsNone(focus.hand_back())
        self.assertTrue(focus.activating())
        self.assertIsNone(focus.hand_back())
        self.assertEqual(self.calls, [])


class AfterSendTest(unittest.TestCase):
    def test_unreadable_composer_is_unknown_not_sent(self):
        self.assertEqual(after_send(-25204, None)[0], 6)

    def test_cleared_composer_is_sent_and_leftover_text_is_not(self):
        self.assertEqual(after_send(0, "")[0], 0)
        self.assertEqual(after_send(0, "still here")[0], 6)


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

    def test_dm_without_conversation_id_is_a_usage_error(self):
        sys.argv = ["slack_post.py", "--team", "E1", "--workspace", "Acme", "--user-id", "U1", "--name", "x",
                    "--text", "hi"]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main()
        self.assertEqual(cm.exception.code, 64)


if __name__ == "__main__":
    unittest.main()
