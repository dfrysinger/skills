# Channel book (example)

Copy this file to `~/.config/slack-desktop-post/CHANNELS.md` and fill it in.
Keep the real one on your machine only: it holds workspace IDs, channel IDs and
coworkers' handles.

## Workspace

| Field | Value | Where to find it |
| --- | --- | --- |
| `--team` | `T0123456789` | The `team=` value of any `slack://` link, or the workspace ID in a Slack MCP response |
| `--workspace` | `Acme` | The workspace name in the Slack window title: `<channel> (Channel) - <workspace> - Slack` |

## Channels

`--name` is the channel name without `#`, or a DM person's display name. A DM needs both the person's user ID and the DM's conversation ID (`D…`); display names are not unique.

| Channel | ID | What gets posted there |
| --- | --- | --- |
| #team-chat | `C0123456789` | Team questions, review and approval asks, design-doc shares |
| #team-ops | `C0123456780` | Chatops commands |
| Self-DM | user `U0123456789`, DM `D0123456789` | Safe test target |

## People

Mention as plain `@handle`.

| Handle | Person | Notes |
| --- | --- | --- |
| `@reviewer` | A frequent reviewer | Usual approver for deploy stamps |

## Team style

Copy real messages from the channel so drafts match how the team writes.

**Approval for a test deploy:**

```
Can I get a staging :stamp: on this? https://github.com/octo-org/app/pull/123
```

**Review request:**

```
:review: https://github.com/octo-org/app/pull/124 fixes https://github.com/octo-org/app/issues/120
```

**Sharing a design doc or results:** what it is, a "Short version:" line with
the takeaway, caveats, what is still open, a link to the full data, then
"Feedback welcome."

## Chatops

Commands go to the ops channel as the whole message. Every command starts
ungranted. Change a row to "Yes" only after the user grants it for unattended
use, and note when they did.

| Channel | Command | Granted unattended? |
| --- | --- | --- |
| #team-ops | `.wcid app` (who is deployed where) | No |
| #team-ops | `.deploy https://github.com/octo-org/app/pull/<N> to staging` | No |
| #team-ops | `.unlock app in staging` (only a lock your own deploy took) | No |
| #team-ops | `.deploy ... to production` | Never: ask each time |
