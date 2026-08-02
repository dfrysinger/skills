# Attribution — Hermes Agent self-learning port

The **self-learning skill system** in this repository is a port of the
autonomous skill machinery from
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
pinned at commit
[`e618cbe`](https://github.com/NousResearch/hermes-agent/tree/e618cbee4418cce53a9de63d6fdc8a7b4885666d).
Hermes Agent is MIT-licensed; its permission and copyright notice is reproduced
below per the license terms.

## What was ported

| This repo | Upstream Hermes source | Relationship |
|-----------|------------------------|--------------|
| [`skill-review`](../SKILL.md) | [`agent/background_review.py`](https://github.com/NousResearch/hermes-agent/blob/main/agent/background_review.py) (`_SKILL_REVIEW_PROMPT`) | Selection criteria lifted **verbatim** (see [`references/review-prompt.md`](./review-prompt.md)); the autonomous create/patch loop is reimplemented as a Copilot CLI end-of-task dispatch + daily sweep because Copilot CLI has no code-enforced post-turn fork. |
| [`skill-curator`](../../skill-curator/SKILL.md) | [`agent/curator.py`](https://github.com/NousResearch/hermes-agent/blob/main/agent/curator.py) | Curator prompt + consolidation/prune logic adapted (see [`../skill-curator/references/curator-prompt.md`](../../skill-curator/references/curator-prompt.md) and [`../skill-curator/references/hermes-curator-config.md`](../../skill-curator/references/hermes-curator-config.md)). |
| [`skill-create`](../../skill-create/SKILL.md), [`skill-manage`](../../skill-manage/SKILL.md) | Hermes `skill_manage` / `skill_view` / `skills_list` tools | Copilot-native re-expression of Hermes's skill-management tool surface as skills (Copilot CLI has no equivalent built-in tool). |

### Copilot CLI adaptations

Hermes's autonomous creation runs as a tool-restricted forked agent fired after
~10 tool iterations per turn. Copilot CLI exposes no end-of-turn hook, so the
port substitutes two triggers gated by a durable ledger (so they never
double-create):

- **End-of-task dispatch** (primary) — the main agent dispatches a
  `skill-review` subagent right after a qualifying heavy task. This is the
  Hermes-faithful real-time analog.
- **Daily scheduled sweep** (backstop) — a `manage_schedule` job runs
  `/skill-review sweep` to catch sessions the in-session dispatch missed.

The verbatim Hermes selection criteria are wrapped in a binding **Copilot
execution contract** (allowed write paths, prompt-injection guard, provenance
marking, diff-scope guard, no-confirm) defined in
[`references/review-prompt.md`](./review-prompt.md). A feature
request to add a native post-turn background-review hook to Copilot CLI is
tracked in [`docs/rfcs/0001-post-turn-background-review-hook.md`](../../../../docs/rfcs/0001-post-turn-background-review-hook.md).

## Upstream license

```
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
