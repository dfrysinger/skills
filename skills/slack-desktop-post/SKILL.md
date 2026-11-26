---
name: slack-desktop-post
description: Drafts or posts a Slack message through the macOS desktop app in the background, verified by read-back and screenshot. Use when the user wants a Slack message drafted for them to send, an approved message posted, or a chatops command sent to a bot; or when a Slack MCP is read-only and a post is needed.
---

# slack-desktop-post

`scripts/slack_post.py` drives Slack's composer through macOS Accessibility. It keeps the user's frontmost app in front and never moves the pointer, so their typing stays where it was going. Messages to people end as a **handoff**: `--leave` puts the verified draft in the channel's message box and the user edits and sends it there, which is faster than revising wording in chat. Commands to bots are a **two-phase send**: a dry run stages and verifies the text and then restores the composer; the same command with `--send` posts it. Slack is the source of truth: a post or draft counts only after a screenshot shows it rendered.

## Setup

- macOS with the Slack desktop app signed in, and Accessibility permission for the process that runs the agent (see [`macos-background-app-control`](../macos-background-app-control/SKILL.md) for which process needs the grant).
- The pyobjc venv from `macos-background-app-control` at `/tmp/bgctl/.venv`, plus `pyobjc-framework-ApplicationServices`.
- A Slack MCP or other read access, for step 6's read-back.
- A personal **channel book** at `~/.config/slack-desktop-post/CHANNELS.md`: workspace, channel and user IDs, people's handles, the team's message style, and chatops commands. Copy [`references/CHANNELS.example.md`](references/CHANNELS.example.md) to start one. If it is missing, ask the user for the destination IDs instead of guessing.

**Keep personal details in the channel book, not in this skill.** This skill folder may be shared or published. When you learn something specific to the user's workspace (a new channel ID, a handle, a style example, a newly granted command), add it to `~/.config/slack-desktop-post/CHANNELS.md`. Never write real IDs, names or message text into `SKILL.md`, `references/` or `scripts/`.

## Steps

1. **Confirm the grant.** There are two kinds of message:
   - **To bots:** only the chatops commands the user has granted (for example a staging deploy, or unlocking a lock your own deploy took), plus tests to the self-DM. Record each grant in the channel book. Production deploys and other people's locks need the user each time.
   - **To people:** only when the user asks for a message. Default to the handoff (step 5). Use `--send` only when the user explicitly asks you to post exact text they approved in this conversation.

   Done when you can name which grant covers this message.
2. **Pick the destination** from the channel book by ID, never by typing a name in Slack's switcher. For a DM you also need `--dm-id`, the DM's own conversation ID (`D…`): display names are not unique, so the script checks this ID, not the name. If the channel book lacks it, read the DM once by user ID (for example `slack_read_channel` with the user ID shows `Channel: DM (D…)`) and save it to the channel book. Done when you have `--team`, `--workspace`, `--channel-id` or `--user-id` with `--dm-id`, and the composer `--name` (channel name without `#`, or the DM person's display name).
3. **Write it in the team's style.** Follow the matching example in the channel book. Mention people as plain `@handle`; the script refuses raw `<@U…>` tokens (exit 64) because they post as literal text. For bold, italics, lists, code blocks or links, write an HTML file and pass `--html FILE`, with `--text` set to exactly the plain text Slack will show (link text, not the URL). Done when the text says what the user asked for.
4. **Dry run** with neither `--send` nor `--leave`. Done at exit 0 with `staged:` showing the right window and text.
5. **Hand off or send.**
   - **Handoff (default for people):** the same arguments plus `--leave`. Done at exit 0 (`left:`). Then take a screenshot (step 7) to confirm the draft is in the right channel, tell the user it is ready there and show the text in chat too. Skip step 6; the user's send is the post.
   - **Send (bots, or an explicit request to post):** the same arguments plus `--send`. Done at exit 0 (`composer cleared`).
6. **Prove it landed once, in the right place.** Read the channel back (for example `slack_read_channel` with `oldest` set just before the send; index lag can be 30+ seconds) and confirm the message appears exactly once. If it is missing, wait and read again; resend only after a screenshot also shows it absent. Bots usually reply in a thread; read it with `slack_read_thread`.
7. **Prove it rendered.** Run `../macos-background-app-control/scripts/capture_app.sh "Slack" /tmp/bgctl/post.png`, crop with PIL, and view it. Mentions must be highlighted names, links blue, emoji images. A read-back is not enough: it can show `<@U…|handle>` even when Slack rendered literal text. Done when the screenshot shows the message or draft as intended.
8. **Log it** where the task keeps its record, with the time, channel and message timestamp.

## Usage

```sh
/tmp/bgctl/.venv/bin/python scripts/slack_post.py \
  --team T0123456789 --workspace Acme --channel-id C0123456789 --name team-chat \
  --text "Plain text as Slack shows it" [--html draft.html] [--leave | --send]
```

For a DM, replace `--channel-id …` with `--user-id U0123456789 --dm-id D0123456789`.

## Exit codes

| Code | Meaning | Action |
| --- | --- | --- |
| 0 | Verified (dry run), left in the composer (`--leave`), or sent | Next step |
| 2 | Screen locked or lock state unknown | Wait; retry later |
| 3 | The open conversation's ID is not `--channel-id` or `--dm-id`; the window title is not `<name> (…` in workspace `--workspace`; the composer, its own Send button or the Paste menu is missing or ambiguous; the composer could not be read; or the script couldn't tell which app was in front, so it didn't bring Slack forward | Check Slack is running, the IDs, `--name` and any open thread; retry once |
| 4 | The composer already holds a draft, or gained one while `--html` waited for a typing pause | Leave it. Show the draft in chat and ask the user to clear the box. Never clear it yourself |
| 5 | Staged text differs from `--text` (composer restored) | Fix `--text` or the HTML so they match; dry-run again |
| 6 | Send state unknown: Send pressed but the composer did not clear or could not be read, or keys were pressed while staging and the text didn't match (Enter in Slack may have sent it; the composer is left as is, since the user may have typed in it) | Take a screenshot before anything else. Never resend until it proves the post is missing. If staged text is still in the box, show the user; never send or clear it yourself |
| 7 | A check failed and the composer could not be restored, so staged text may remain | Take a screenshot. If the text is there, show the user and ask them to clear it; never send it |
| 8 | `--html` only: the user kept typing for 20 s, so nothing was pasted | Retry later |
| 64 | Usage error, or a raw `<@…>`/`<#…>`/`<!here>` token | Fix the arguments; use `@handle` |

## Behaviour notes

- Plain text is set directly; Slack turns `:emoji:` into images and straight quotes into curly ones. The comparison ignores those, plus pasted list bullets and whitespace.
- `--html` saves the clipboard, puts HTML and plain text on it, pastes through Slack's Edit > Paste menu, and restores the clipboard. Slack has no tables; put tabular data in a `<pre>` block.
- Focus: the script switches conversations by pressing the sidebar row through Accessibility, which leaves Slack in the background, and skips the switch when the conversation is already open. It uses the `slack://` deep link only when the conversation has no sidebar row; Slack then jumps forward, and the script returns focus to the app that was in front just before, within about 0.2 s. Edit > Paste works only while Slack is active, so `--html` waits for a 1 s pause in typing, then brings Slack forward for under half a second. The clipboard is replaced only after that pause, and a draft that appears during the wait is left alone (exit 4). If keys go down while staging and the text doesn't match, the script exits 6, because Enter may have sent it. Focus is handed back only after the script's own activations, including late ones up to 5 s after. A switch to a third app, or a click after the script's own activation, cancels a pending hand-back, and a user already in Slack stays there. Cmd-Tab into Slack within those 5 s after a deep link can't be told apart from Slack's own late jump, so it may be undone once. If the script can't tell which app is in front, it won't bring Slack forward (exit 3). A `focus:` line reports any hand-back.
- The Send button is "Send message" when the composer is empty and "Send now" once it has text. The script presses only the button in the composer's own container, so an open thread's Send is never used.
- To fix a posted message, edit it in place rather than posting a second copy: open the message's context menu, choose **Edit message**, replace the full text with the approved correction and save. Confirm the message timestamp is unchanged and the text matches, and confirm by screenshot that Slack shows `(edited)`. If editing isn't possible, stop and tell the user rather than posting a duplicate.
- If something reaches the wrong channel, stop, tell the user, and delete only that exact message once they agree.
- Thread replies are not supported yet.
